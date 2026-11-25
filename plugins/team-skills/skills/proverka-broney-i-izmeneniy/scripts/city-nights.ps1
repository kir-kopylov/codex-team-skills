# Вызывается из check-booking.ps1 внутри его читающей транзакции через Read-Query.
param([string]$City, $Cities, [datetime]$From, [datetime]$Until, [datetime]$DbTime, [int]$StartHour, [int]$EndHour)

function Get-PositiveId($value) {
    $id = 0
    if (-not [int]::TryParse([string]$value, [ref]$id) -or $id -le 0) {
        throw 'В настройке городского фонда ожидается положительный целый номер.'
    }
    return $id
}

function Get-UseKind($row) {
    if ($row.OTBOY -eq 'T') { return 'Ignored' }
    if ($row.OTBOY -ne 'F' -or -not $row.STATUS_NAME) { return 'Unknown' }
    $name = $row.STATUS_NAME.Trim()
    if ($name -like 'Уборка*') { return 'Cleaning' }
    if ($row.STATUS_TYPE -in 4,6 -or $name -match 'долгосроч.*владел') { return 'Blocked' }
    if ($name -in @('Заселение','Резерв','Подтверждена','-Подтверждена','Ожидает заселения',
        'Ожидает заселения СМС','Продление','Аренда на месяц(-ы)','Согласована ком.','Комиссия внесена')) {
        if ($row.CHANNEL -eq 'Сотрудник компании' -and $row.ZERO_CHARGE -eq 1) { return 'InternalStay' }
        return 'Guest'
    }
    if ($row.KV_STATUS -eq 0 -and $name -in 'Новая','Принята','Штрафная бронь','Догоняющий звонок') {
        return 'Ignored'
    }
    return 'Unknown'
}

if ($From -eq [datetime]::MinValue) { $From = $DbTime.Date.AddDays(-1) }
if ($Until -eq [datetime]::MinValue) { $Until = $From.AddDays(1) }
if ($From.TimeOfDay.Ticks -or $Until.TimeOfDay.Ticks -or ($Until - $From).Days -notin (1..90)) {
    throw 'From и Until задают от 1 до 90 ночей календарными датами. Последняя дата — утро после последней ночи.'
}
if ($Until.AddDays(-1).AddHours($StartHour) -gt $DbTime) {
    throw 'Запрошенная ночь ещё не началась по часам базы.'
}

$scope = if ($Cities) { $Cities.PSObject.Properties[$City] }
if (-not $scope) { throw 'Город отсутствует в Cities приватного профиля. Сверьте состав фонда по инструкции подключения.' }
$portfolio = $scope.Value
$params = @{branch = Get-PositiveId $portfolio.BranchId; owner = Get-PositiveId $portfolio.OwnerId}
$branch = @(Read-Query 'select NAME from SPR_CITY where ID=@branch' @{branch=$params.branch})
if ($branch.Count -ne 1) { throw 'Филиал из настройки города не найден в справочнике.' }
$predicate = "k.CITY=@branch and k.PIPLE=@owner and k.TYPE_KV=1 and k.VIS='T'"
$include = $portfolio.PSObject.Properties['ApartmentIds']
$exclude = $portfolio.PSObject.Properties['ExcludedApartmentIds']
if ($include -and $exclude) { throw 'Для одного города укажите либо ApartmentIds, либо ExcludedApartmentIds.' }
if (-not $include -and $branch[0].NAME.Trim() -ne $City) {
    throw 'Название филиала отличается от города. Укажите проверенные ApartmentIds этого города.'
}
$selection = if ($include) { $include } else { $exclude }
if ($selection) {
    if ($selection.Value -isnot [array] -or -not $selection.Value.Count) { throw 'Список квартир должен быть непустым массивом.' }
    $ids = @($selection.Value | ForEach-Object { Get-PositiveId $_ } | Sort-Object -Unique)
    $operator = if ($include) { 'in' } else { 'not in' }
    $joiner = if ($include) { ' or ' } else { ' and ' }
    # Firebird ограничивает число элементов одного IN. В SQL попадают только проверенные целые ID.
    $clauses = for ($offset=0; $offset -lt $ids.Count; $offset+=500) {
        $last = [Math]::Min($offset+499, $ids.Count-1)
        "k.ID $operator (" + ($ids[$offset..$last] -join ',') + ')'
    }
    $predicate += ' and (' + ($clauses -join $joiner) + ')'
}
$units = @(Read-Query "select k.ID,k.ADR from KV k where $predicate order by k.ID" $params)
if (-not $units.Count -or ($include -and $units.Count -ne $ids.Count)) {
    throw 'Городской фонд пуст или часть выбранных квартир не соответствует активному фонду филиала и владельца.'
}

# Предыдущая ночь нужна, чтобы определить переход даже для запроса об одной ночи.
$params.since = $From.AddDays(-1).AddHours($StartHour)
$params.until_time = $Until.AddHours($EndHour)
$byUnit = @{}
foreach ($unit in $units) { $byUnit[$unit.ID] = [Collections.Generic.List[object]]::new() }
foreach ($source in 'ZAIVKA','ARH_ZAIVKA') {
    $distinct = if ($source -eq 'ARH_ZAIVKA') { 'and not exists (select 1 from ZAIVKA live where live.ID=z.ID)' } else { '' }
    $sql = @"
select z.ID as BOOKING_ID,z.KV,s.NAME as STATUS_NAME,s.T as STATUS_TYPE,s.OTBOY,s.KV_STATUS,
       z.IN_TM,z.OUT_TM,z.D_REG as REGISTERED_DATE,r.NAME as CHANNEL,
       case when z.S=0 and z.SM=0 then 1 else 0 end as ZERO_CHARGE
from $source z join KV k on k.ID=z.KV
left join ZAIVKA_STATUS s on s.ID=z.SOST
left join REKLAMA r on r.ID=z.REKLAMA
where $predicate $distinct and (
    ((z.IN_TM is null or z.IN_TM < @until_time) and (z.OUT_TM is null or z.OUT_TM > @since))
    or (z.OUT_TM <= z.IN_TM and z.OUT_TM < @until_time and z.IN_TM >= @since)
)
order by z.KV,z.IN_TM,z.ID
"@
    foreach ($row in (Read-Query $sql $params)) {
        $kind = Get-UseKind $row
        if ($kind -eq 'Ignored') { continue }
        if ($null -eq $row.IN_TM -or $null -eq $row.OUT_TM -or $row.OUT_TM -le $row.IN_TM) {
            $kind = 'Unknown'
        }
        $row | Add-Member -NotePropertyName Kind -NotePropertyValue $kind
        $byUnit[$row.KV].Add($row)
    }
}

$nights = [Collections.Generic.List[object]]::new()
$previous = @{}
$reserveByBooking = @{}
for ($day=$From.AddDays(-1); $day -lt $Until; $day=$day.AddDays(1)) {
    $start = $day.AddHours($StartHour)
    $end = $day.AddDays(1).AddHours($EndHour)
    $counts = [ordered]@{Free=0; Guest=0; InternalStay=0; Blocked=0; Cleaning=0; Unknown=0}
    $apartments = foreach ($unit in $units) {
        $overlaps = @($byUnit[$unit.ID] | Where-Object {
            if ($null -ne $_.IN_TM -and $null -ne $_.OUT_TM -and $_.OUT_TM -le $_.IN_TM) {
                # При перепутанных или равных датах обе указанные точки относятся к периоду неопределённости.
                $_.OUT_TM -lt $end -and $_.IN_TM -ge $start
            } else {
                ($null -eq $_.IN_TM -or $_.IN_TM -lt $end) -and ($null -eq $_.OUT_TM -or $_.OUT_TM -gt $start)
            }
        })
        $kind = 'Free'
        foreach ($category in 'Guest','InternalStay','Blocked','Cleaning','Unknown') {
            if ($category -in $overlaps.Kind) { $kind=$category; break }
        }
        $counts[$kind]++
        $newBookings = @()
        if ($previous[$unit.ID] -eq 'Free' -and $kind -eq 'Guest') {
            $newBookings = @($overlaps | Where-Object Kind -eq 'Guest')
            foreach ($row in $newBookings) { $reserveByBooking[$row.BOOKING_ID] = $null }
        }
        $previous[$unit.ID] = $kind
        [pscustomobject]@{ID=$unit.ID; Address=$unit.ADR; State=$kind; Requests=$overlaps; ClosedByBookings=$newBookings}
    }
    if ($day -ge $From) {
        $nights.Add([pscustomobject]@{
            NightOf=$day.ToString('yyyy-MM-dd'); WindowStart=$start; WindowEnd=$end
            IsPartial=($DbTime -lt $end); Counts=$counts; Apartments=@($apartments)
        })
    }
}

# Запрашиваем время именно первого резерва. Дата регистрации в карточке имеет отдельное поле.
$bookingIds = @($reserveByBooking.Keys)
for ($offset=0; $offset -lt $bookingIds.Count; $offset+=500) {
    $last = [Math]::Min($offset+499, $bookingIds.Count-1)
    $batch = $bookingIds[$offset..$last] -join ','
    foreach ($history in 'ZAIVKA_HIS','ARH_ZAIVKA_HIS') {
        $sql = "select h.ID,min(h.TM) as FIRST_RESERVE_AT from $history h join ZAIVKA_STATUS s on s.ID=h.STATUS_NEW where h.ID in ($batch) and upper(trim(s.NAME))='РЕЗЕРВ' group by h.ID"
        foreach ($event in (Read-Query $sql)) {
            $prior = $reserveByBooking[$event.ID]
            if ($null -eq $prior -or $event.FIRST_RESERVE_AT -lt $prior) { $reserveByBooking[$event.ID] = $event.FIRST_RESERVE_AT }
        }
    }
}
foreach ($night in $nights) {
    foreach ($unit in $night.Apartments) {
        foreach ($row in $unit.ClosedByBookings) {
            $row | Add-Member -Force -NotePropertyName FirstReserveAt -NotePropertyValue $reserveByBooking[$row.BOOKING_ID]
        }
    }
}
[pscustomobject]@{City=$City; DB_TIME=$DbTime; ApartmentCount=$units.Count; Nights=$nights.ToArray()}
