# Requires PowerShell 7 and .NET 8 or later.
[CmdletBinding()]
param(
    [string]$Address,
    [string]$ConfigPath,
    [switch]$ValidateOnly,
    [ValidateRange(1,2147483647)][int]$BookingId,
    [switch]$IncludeHistory,
    [ValidateRange(1,90)][int]$HorizonDays = 14,
    [datetime]$From = [datetime]::MinValue,
    [datetime]$Until = [datetime]::MinValue
)
if (-not $ValidateOnly -and -not $Address -and -not $BookingId) { throw 'Укажите адрес или номер заявки.' }
if ($Address -and $BookingId) { throw 'Укажите либо адрес, либо номер заявки.' }
$watch = [Diagnostics.Stopwatch]::StartNew()
$ErrorActionPreference = 'Stop'
if (-not $ConfigPath) { $ConfigPath = $env:EHOUS_BOOKING_CONFIG }
if (-not $ConfigPath) { $ConfigPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex/ehous-booking.json' }
$profileFile = (Resolve-Path -LiteralPath $ConfigPath).Path
$profile = Get-Content -LiteralPath $profileFile -Raw | ConvertFrom-Json
foreach ($field in @('DataSource','Database','UserID','ClientDllPath','PasswordIniPath','PasswordIniSection','PasswordIniKey')) {
    if ($profile.$field -isnot [string] -or [string]::IsNullOrWhiteSpace($profile.$field)) { throw "Отсутствует строковое поле профиля: $field" }
}
function Resolve-ProfilePath([string]$value) {
    if ([IO.Path]::IsPathRooted($value)) { return $value }
    return Join-Path (Split-Path -Parent $profileFile) $value
}
Add-Type -Path (Resolve-ProfilePath $profile.ClientDllPath)
$section = ''
$values = @()
foreach ($line in (Get-Content -LiteralPath (Resolve-ProfilePath $profile.PasswordIniPath))) {
    if ($line -match '^\s*\[([^]]+)\]\s*$') { $section = $Matches[1].Trim(); continue }
    if ($section -eq $profile.PasswordIniSection -and $line -match '^\s*([^;#][^=]*?)\s*=(.*)$' -and $Matches[1].Trim() -eq $profile.PasswordIniKey) {
        $values += $Matches[2].Trim()
    }
}
if ($values.Count -ne 1 -or -not $values[0]) { throw 'В указанной секции настроек нет единственного непустого ключа доступа.' }
$dbCredential = $values[0]
$builder = [FirebirdSql.Data.FirebirdClient.FbConnectionStringBuilder]::new()
$builder.DataSource = $profile.DataSource
$builder.Port = if ($null -eq $profile.Port) { 3050 } else { [int]$profile.Port }
if ($builder.Port -lt 1 -or $builder.Port -gt 65535) { throw 'Порт должен быть в пределах 1–65535.' }
$builder.Database = $profile.Database
$builder.UserID = $profile.UserID
$builder.Password = $dbCredential
$builder.Charset = if ($profile.Charset) { $profile.Charset } else { 'WIN1251' }
$builder.Pooling = $false
$builder.ConnectionTimeout = 10
if ($ValidateOnly) {
    [pscustomobject]@{ProfileValid=$true; DatabaseChecked=$false} | ConvertTo-Json
    return
}
$connection = [FirebirdSql.Data.FirebirdClient.FbConnection]::new($builder.ConnectionString)
$transaction = $null
try {
    $connection.Open()
    $options = [FirebirdSql.Data.FirebirdClient.FbTransactionOptions]::new()
    $options.TransactionBehavior = [FirebirdSql.Data.FirebirdClient.FbTransactionBehavior]::Read -bor [FirebirdSql.Data.FirebirdClient.FbTransactionBehavior]::ReadCommitted -bor [FirebirdSql.Data.FirebirdClient.FbTransactionBehavior]::RecVersion -bor [FirebirdSql.Data.FirebirdClient.FbTransactionBehavior]::NoWait
    $transaction = $connection.BeginTransaction($options)
    function Read-Query([string] $sql, [hashtable] $parameters = @{}) {
        $command = $connection.CreateCommand()
        $command.Transaction = $transaction
        $command.CommandTimeout = 15
        $command.CommandText = $sql
        foreach ($key in $parameters.Keys) {
            $null = $command.Parameters.AddWithValue('@' + $key, $parameters[$key])
        }
        $reader = $command.ExecuteReader()
        try {
            while ($reader.Read()) {
                $row = [ordered]@{}
                for ($i = 0; $i -lt $reader.FieldCount; $i++) {
                    $value = $reader.GetValue($i)
                    if ($value -is [DBNull]) { $value = $null }
                    $row[$reader.GetName($i).Trim()] = $value
                }
                [pscustomobject]$row
            }
        } finally { $reader.Dispose(); $command.Dispose() }
    }
    $now = @(Read-Query 'select current_timestamp as DB_TIME from rdb$database')
    $dbTime = [datetime]$now[0].DB_TIME
    if ($From -eq [datetime]::MinValue) { $From = $dbTime.Date.AddDays(-1) }
    if ($Until -eq [datetime]::MinValue) { $Until = $dbTime.Date.AddDays($HorizonDays) }
    if ($Until -le $From) { throw 'Конец периода должен быть позже начала.' }
    $history = @()
    $historyId = $null
    $historyReason = 'Не запрошена'
    if ($BookingId) {
        $bookings = @(Read-Query @'
select first 1 z.ID as BOOKING_ID, k.ID as KV, k.ADR,
z.SOST, s.NAME as STATUS_NAME, s.OTBOY, s.KV_STATUS, z.IN_TM, z.OUT_TM
from ZAIVKA z
join KV k on k.ID=z.KV
left join ZAIVKA_STATUS s on s.ID=z.SOST
where z.ID=@booking
'@ @{booking=$BookingId})
        $apartments = @()
        if ($bookings.Count -eq 1) { $historyId = $BookingId }
        $historyReason = 'Указанная заявка'
    } else {
        $apartments = @(Read-Query "select first 21 ID, ADR, VIS, CITY from KV where VIS='T' and ADR containing @address order by ID" @{address=$Address})
        if ($apartments.Count -ge 21) { throw 'Слишком много квартир: уточните часть адреса.' }
        $bookings = @(Read-Query @'
select first 201 z.ID as BOOKING_ID, k.ID as KV, k.ADR,
z.SOST, s.NAME as STATUS_NAME, s.OTBOY, s.KV_STATUS, z.IN_TM, z.OUT_TM
from ZAIVKA z
join KV k on k.ID=z.KV
left join ZAIVKA_STATUS s on s.ID=z.SOST
where k.VIS='T' and k.ADR containing @address
and z.OUT_TM > @from_time and z.IN_TM < @until_time
order by z.IN_TM, z.ID
'@ @{address=$Address; from_time=$From; until_time=$Until})
        if ($bookings.Count -ge 201) { throw 'Достигнут предел заявок: сузьте период или адрес.' }
        if ($IncludeHistory) {
            $current = @($bookings | Where-Object {
                $_.OTBOY -ne 'T' -and $null -ne $_.KV_STATUS -and $_.KV_STATUS -ne 0 -and
                $_.IN_TM -le $dbTime -and $_.OUT_TM -gt $dbTime
            })
            if ($apartments.Count -eq 1 -and $current.Count -eq 1) {
                $historyId = $current[0].BOOKING_ID
                $historyReason = 'Единственное текущее проживание'
            } else { $historyReason = 'Нет единственного текущего проживания; выберите заявку по результатам' }
        }
    }
    if ($historyId) {
        $history = @(Read-Query @'
select first 101 h.ID as BOOKING_ID, h.TM as CHANGED_AT,
h.USR as USER_ID, u.NAME as USER_NAME, h.STATUS_OLD, h.STATUS_NEW,
h.TEXT as CHANGE_TEXT
from ZAIVKA_HIS h
left join USR u on u.ID=h.USR
where h.ID=@booking
order by h.TM desc
'@ @{booking=$historyId})
    }
    $watch.Stop()
    [pscustomobject]@{
        DB_TIME=$dbTime; WindowStart=$From; WindowEnd=$Until
        Apartments=$apartments; Bookings=$bookings
        HistoryBookingId=$historyId; HistorySelection=$historyReason
        History=$history; HistoryLimitReached=($history.Count -ge 101)
        QuerySeconds=[math]::Round($watch.Elapsed.TotalSeconds,3)
    } | ConvertTo-Json -Depth 6

} finally {
    if ($transaction) { $transaction.Rollback(); $transaction.Dispose() }
    if ($connection) { $connection.Close(); $connection.Dispose() }
    $dbCredential = $null
    $iniText = $null
}
