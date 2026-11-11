# PowerShell 7, .NET 8, FirebirdSql.Data.FirebirdClient 10.3.4.
[CmdletBinding()]
param(
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')][string]$From,
    [Parameter(Mandatory)][ValidatePattern('^\d{4}-\d{2}-\d{2}$')][string]$Through,
    [ValidateRange(1,2147483647)][ValidateCount(1,100)][int[]]$ApartmentId,
    [ValidateRange(1,2147483647)][ValidateCount(1,500)][int[]]$BookingId,
    [string]$ConfigPath
)
$ErrorActionPreference = 'Stop'
$invariant = [Globalization.CultureInfo]::InvariantCulture
$last = [datetime]::ParseExact($Through, 'yyyy-MM-dd', $invariant)
$start = if ($From) { [datetime]::ParseExact($From, 'yyyy-MM-dd', $invariant) } else { $null }
if ($start -and $last -lt $start) { throw 'Дата среза раньше начала периода.' }
if ($start -and -not $ApartmentId) { throw 'Для проверки периода укажите номера объектов.' }
if (-not $start -and -not $BookingId) { throw 'Без начала периода укажите номера заявок из отчёта.' }
$end = $last.AddDays(1)

if (-not $ConfigPath) { $ConfigPath = $env:EHOUS_BOOKING_CONFIG }
if (-not $ConfigPath) { $ConfigPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex/ehous-booking.json' }
$profileFile = (Resolve-Path -LiteralPath $ConfigPath).Path
$profile = Get-Content -LiteralPath $profileFile -Raw | ConvertFrom-Json
foreach ($key in 'DataSource','Database','UserID','ClientDllPath','PasswordIniPath','PasswordIniSection','PasswordIniKey') {
    if ($profile.$key -isnot [string] -or [string]::IsNullOrWhiteSpace($profile.$key)) {
        throw "Отсутствует строковое поле профиля $key."
    }
}
function Resolve-ProfilePath([string]$PathValue) {
    if ([IO.Path]::IsPathRooted($PathValue)) { return $PathValue }
    Join-Path (Split-Path -Parent $profileFile) $PathValue
}
$section = ''
$entries = @(foreach ($line in Get-Content -LiteralPath (Resolve-ProfilePath $profile.PasswordIniPath)) {
    if ($line -match '^\s*\[([^]]+)\]\s*$') { $section = $Matches[1].Trim(); continue }
    if ($section -eq $profile.PasswordIniSection -and $line -match '^\s*([^;#][^=]*?)\s*=(.*)$' -and $Matches[1].Trim() -eq $profile.PasswordIniKey) {
        $Matches[2].Trim()
    }
})
if ($entries.Count -ne 1 -or -not $entries[0]) { throw 'В секции настроек нужен единственный непустой ключ доступа.' }
$credential = $entries[0]
Add-Type -Path (Resolve-ProfilePath $profile.ClientDllPath)
$builder = [FirebirdSql.Data.FirebirdClient.FbConnectionStringBuilder]::new()
$builder.DataSource = $profile.DataSource
$builder.Database = $profile.Database
$builder.UserID = $profile.UserID
$builder.Port = if ($null -eq $profile.Port) { 3050 } else { [int]$profile.Port }
if ($builder.Port -lt 1 -or $builder.Port -gt 65535) { throw 'Порт должен быть в пределах 1–65535.' }
$builder.Charset = if ($profile.Charset) { $profile.Charset } else { 'WIN1251' }
$builder.Password = $credential
$builder.Pooling = $false
$builder.ConnectionTimeout = 10
$connection = [FirebirdSql.Data.FirebirdClient.FbConnection]::new($builder.ConnectionString)
$transaction = $null

function Add-IdParameters([hashtable]$Parameters, [string]$Prefix, [int[]]$Ids) {
    $names = @(for ($index = 0; $index -lt $Ids.Count; $index++) {
        $name = "$Prefix$index"
        $Parameters[$name] = $Ids[$index]
        "@$name"
    })
    $names -join ', '
}

function Read-Rows([string]$Sql, [hashtable]$Parameters = @{}) {
    $command = $connection.CreateCommand()
    try {
        $command.Transaction = $transaction
        $command.CommandTimeout = 15
        $command.CommandText = $Sql
        foreach ($key in $Parameters.Keys) {
            $null = $command.Parameters.AddWithValue('@' + $key, $Parameters[$key])
        }
        $reader = $command.ExecuteReader()
        try {
            while ($reader.Read()) {
                $row = [ordered]@{}
                for ($index = 0; $index -lt $reader.FieldCount; $index++) {
                    $value = $reader.GetValue($index)
                    $row[$reader.GetName($index).Trim().ToLowerInvariant()] = switch ($value) {
                        { $_ -is [DBNull] } { $null; break }
                        { $_ -is [decimal] } { $_.ToString($invariant); break }
                        default { $_ }
                    }
                }
                [pscustomobject]$row
            }
        } finally { $reader.Dispose() }
    } finally { $command.Dispose() }
}

try {
    $connection.Open()
    $options = [FirebirdSql.Data.FirebirdClient.FbTransactionOptions]::new()
    $options.TransactionBehavior = [FirebirdSql.Data.FirebirdClient.FbTransactionBehavior]::Read -bor [FirebirdSql.Data.FirebirdClient.FbTransactionBehavior]::Concurrency -bor [FirebirdSql.Data.FirebirdClient.FbTransactionBehavior]::NoWait
    $transaction = $connection.BeginTransaction($options)
    $clock = Read-Rows 'select current_timestamp as DB_TIME from rdb$database'
    $apartments = @($ApartmentId | Sort-Object -Unique)
    $requested = @($BookingId | Sort-Object -Unique)
    $objectFilter = @{}
    $objectParams = Add-IdParameters $objectFilter 'apt' $apartments
    $foundObjects = if ($apartments.Count) {
        Read-Rows "select ID as object_id, ADR as object_name from KV where ID in ($objectParams)" $objectFilter
    }
    $unknownObjects = @($apartments | Where-Object { $_ -notin $foundObjects.object_id })
    $filter = @{}
    $conditions = @(if ($start) {
        foreach ($key in $objectFilter.Keys) { $filter[$key] = $objectFilter[$key] }
        $filter.period_start = $start
        $filter.period_end = $end
        @"
(z.KV in ($objectParams) and (
 ((z.IN_D is null or z.IN_D < @period_end) and (z.OUT_D is null or z.OUT_D >= @period_start))
 or (z.OUT_D <= z.IN_D and z.OUT_D < @period_end and z.IN_D >= @period_start)
 or (z.IN_TM < @period_end and z.OUT_TM > @period_start)
))
"@
    }
    if ($requested.Count) {
        $bookingParams = Add-IdParameters $filter 'requested' $requested
        "z.ID in ($bookingParams)"
    })
    $where = $conditions -join ' or '
    $bookings = @(foreach ($table in 'ZAIVKA','ARH_ZAIVKA') {
        $part = @(Read-Rows @"
select first 501 z.ID as booking_id, z.KV as object_id, k.ADR as object_name,
 z.SOST as status_id, s.NAME as status_name, z.OTBOY as row_cancelled,
 s.OTBOY as status_cancelled, z.IN_D as arrival, z.OUT_D as departure,
 z.IN_TM as arrival_at, z.OUT_TM as departure_at, z.DC as recorded_nights,
 z.SM as raw_amount, z.S_DOP as raw_addition_in_amount, z.SM_RAS as raw_stored_commission,
 z.REKLAMA as channel_id, r.NAME as channel_name, r.PER as raw_channel_rate,
 r.SM as raw_channel_nightly_fee, r.D_USR as channel_edited_at,
 z.D_REG as registered_on, z.D_USR as edited_at, '$table' as origin
from $table z
left join KV k on k.ID=z.KV
left join ZAIVKA_STATUS s on s.ID=z.SOST
left join REKLAMA r on r.ID=z.REKLAMA
where $where
order by z.ID
"@ $filter)
        if ($part.Count -ge 501) { throw 'В выборке более 500 заявок. Разделите объекты или период и проверьте охват.' }
        $part
    })

    $extraComplete = $true
    $extras = @(foreach ($table in 'ZAIVKA_PLUS','ARH_ZAIVKA_PLUS') {
        $bookingTable = $table -replace '_PLUS$', ''
        $ids = @($bookings | Where-Object origin -eq $bookingTable | Select-Object -ExpandProperty booking_id -Unique)
        if (-not $ids.Count) { continue }
        $extraFilter = @{}
        $idParams = Add-IdParameters $extraFilter 'bid' $ids
        $part = @(Read-Rows @"
select first 1001 x.ID as charge_id, x.ZAIVKA as booking_id, x.PRICE_NAME as charge_type_id,
 p.NAME as charge_type, x.SM as raw_amount, x.D_USR as edited_at, '$table' as origin
from $table x left join PRICE_NAME p on p.ID=x.PRICE_NAME
where x.ZAIVKA in ($idParams)
order by x.ID
"@ $extraFilter)
        if ($part.Count -ge 1001) { $extraComplete = $false; continue }
        $part
    })

    [pscustomobject]@{
        source='eHous'; database_time=$clock.db_time
        period_start=if ($start) { $From } else { $null }
        period_through=$Through; inventory_queried=($null -ne $start)
        apartment_ids=$apartments; requested_booking_ids=$requested
        unknown_apartment_ids=$unknownObjects
        rows=$bookings; extra_charges=$extras; extra_charges_complete=$extraComplete
    } | ConvertTo-Json -Depth 5
} catch {
    throw $_.Exception.Message.Replace($credential, '<скрыто>')
} finally {
    try {
        if ($transaction) { try { $transaction.Rollback() } finally { $transaction.Dispose() } }
    } finally {
        $connection.Dispose()
        $builder.Clear()
        $credential = $null
        $entries = $null
    }
}
