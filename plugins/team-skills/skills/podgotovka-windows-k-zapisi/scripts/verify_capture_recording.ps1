[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$Path,

    [int]$ExpectedWidth = 0,
    [int]$ExpectedHeight = 0,
    [double]$ExpectedFps = 2,
    [double]$FpsTolerance = 0.05,
    [int]$MinimumAudioTracks = 3,
    [int]$AudioProbeSeconds = 90,
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"

function Get-RequiredTool {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command) { return $command.Source }

    $wingetPackages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path -LiteralPath $wingetPackages) {
        $match = Get-ChildItem -LiteralPath $wingetPackages -Recurse -Filter $Name -File -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match 'Gyan\.FFmpeg' } |
            Select-Object -First 1
        if ($match) { return $match.FullName }
    }

    throw "Не найден $Name. Установите FFmpeg и повторите проверку."
}

function Convert-RatioToDouble {
    param([string]$Ratio)
    if ([string]::IsNullOrWhiteSpace($Ratio)) { return 0.0 }
    if ($Ratio -notmatch '^(-?[0-9.]+)/(-?[0-9.]+)$') { return [double]$Ratio }
    $numerator = [double]$Matches[1]
    $denominator = [double]$Matches[2]
    if ($denominator -eq 0) { return 0.0 }
    return $numerator / $denominator
}

$ffprobe = Get-RequiredTool -Name "ffprobe.exe"
$ffmpeg = Get-RequiredTool -Name "ffmpeg.exe"
$fullPath = (Resolve-Path -LiteralPath $Path).Path

$probeJson = & $ffprobe -v error -show_entries "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate:stream_tags=title" -of json $fullPath
if ($LASTEXITCODE -ne 0) { throw "ffprobe не смог прочитать файл: $fullPath" }
$metadata = ($probeJson -join "`n") | ConvertFrom-Json

$videoStreams = @($metadata.streams | Where-Object { $_.codec_type -eq "video" })
$audioStreams = @($metadata.streams | Where-Object { $_.codec_type -eq "audio" })
$errors = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$audioResults = New-Object System.Collections.Generic.List[object]
$audioPreviewFiles = New-Object System.Collections.Generic.List[string]
$detectedFormat = [string]$metadata.format.format_name
$formatNames = @($detectedFormat.Split(",") | ForEach-Object { $_.Trim().ToLowerInvariant() })
$extension = [System.IO.Path]::GetExtension($fullPath)

if ($extension -ine ".mkv") {
    $errors.Add("Расширение файла '$extension', ожидалось '.mkv'.")
}
if ($formatNames -notcontains "matroska") {
    $errors.Add("Контейнер '$detectedFormat' не является Matroska (MKV).")
}

if ($videoStreams.Count -lt 1) {
    $errors.Add("В файле нет видеопотока.")
} else {
    $video = $videoStreams[0]
    $fps = Convert-RatioToDouble -Ratio $video.avg_frame_rate
    if ($fps -eq 0) { $fps = Convert-RatioToDouble -Ratio $video.r_frame_rate }
    if ($ExpectedWidth -gt 0 -and $video.width -ne $ExpectedWidth) {
        $errors.Add("Ширина $($video.width), ожидалось $ExpectedWidth.")
    }
    if ($ExpectedHeight -gt 0 -and $video.height -ne $ExpectedHeight) {
        $errors.Add("Высота $($video.height), ожидалось $ExpectedHeight.")
    }
    if ([math]::Abs($fps - $ExpectedFps) -gt $FpsTolerance) {
        $errors.Add("Частота кадров $([math]::Round($fps, 3)), ожидалось $ExpectedFps ± $FpsTolerance.")
    }
}

if ($audioStreams.Count -lt $MinimumAudioTracks) {
    $errors.Add("Аудиодорожек $($audioStreams.Count), требуется не менее $MinimumAudioTracks.")
}

$duration = [double]$metadata.format.duration
$secondsToProbe = [math]::Min([math]::Max($duration, 1), $AudioProbeSeconds)
for ($i = 0; $i -lt $audioStreams.Count; $i++) {
    $previousErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $audioOutput = & $ffmpeg -hide_banner -v info -i $fullPath -map "0:a:$i" -t $secondsToProbe -af volumedetect -f null NUL 2>&1 | Out-String
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorPreference
    $title = $null
    if ($audioStreams[$i].tags -and $audioStreams[$i].tags.title) { $title = [string]$audioStreams[$i].tags.title }
    $meanVolume = $null
    if ($audioOutput -match 'mean_volume:\s*(-?[0-9.]+|-inf)\s*dB') { $meanVolume = $Matches[1] }

    if ($exitCode -ne 0) {
        $errors.Add("Не удалось проверить аудиодорожку $($i + 1).")
    } elseif ($null -eq $meanVolume -or $meanVolume -eq "-inf") {
        $errors.Add("На аудиодорожке $($i + 1) не найден слышимый сигнал.")
    }

    if ([string]::IsNullOrWhiteSpace($title)) {
        $warnings.Add("У аудиодорожки $($i + 1) нет названия; проверьте названия в OBS.")
    }

    $audioResults.Add([pscustomobject]@{
        track = $i + 1
        title = $title
        codec = $audioStreams[$i].codec_name
        mean_volume_db = $meanVolume
    })
}

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path (Split-Path -Parent $fullPath) ("capture-check-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$outputFullPath = (Resolve-Path -LiteralPath $OutputDirectory).Path

for ($i = 0; $i -lt $audioStreams.Count; $i++) {
    $audioPreviewPath = Join-Path $outputFullPath ("audio-track-{0}.m4a" -f ($i + 1))
    & $ffmpeg -hide_banner -loglevel error -y -i $fullPath -map "0:a:$i" -t $secondsToProbe -vn -c:a aac -b:a 128k $audioPreviewPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $audioPreviewPath)) {
        $errors.Add("Не удалось извлечь аудиодорожку $($i + 1) для прослушивания.")
    } else {
        $audioPreviewFiles.Add($audioPreviewPath)
    }
}

if ($duration -gt 0 -and $videoStreams.Count -gt 0) {
    $fractions = @(0.2, 0.5, 0.8)
    for ($i = 0; $i -lt $fractions.Count; $i++) {
        $time = [math]::Round($duration * $fractions[$i], 3)
        $framePath = Join-Path $outputFullPath ("frame-{0}.png" -f ($i + 1))
        & $ffmpeg -hide_banner -loglevel error -y -ss $time -i $fullPath -frames:v 1 $framePath
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $framePath)) {
            $errors.Add("Не удалось извлечь контрольный кадр $($i + 1).")
        }
    }
}

$fileSize = [double]$metadata.format.size
$estimatedTwoHoursGb = if ($duration -gt 0) {
    [math]::Round((($fileSize / $duration) * 7200 * 1.25) / 1GB, 2)
} else { $null }

$videoSummary = if ($videoStreams.Count -gt 0) {
    $v = $videoStreams[0]
    [pscustomobject]@{
        codec = $v.codec_name
        width = $v.width
        height = $v.height
        fps = [math]::Round((Convert-RatioToDouble -Ratio $v.avg_frame_rate), 3)
    }
} else { $null }

$report = [pscustomobject]@{
    status = if ($errors.Count -eq 0) { "AUTOMATIC_CHECK_PASSED" } else { "AUTOMATIC_CHECK_FAILED" }
    file = $fullPath
    format = $detectedFormat
    duration_seconds = [math]::Round($duration, 2)
    file_size_mb = [math]::Round($fileSize / 1MB, 2)
    estimated_two_hours_gb_with_25_percent_reserve = $estimatedTwoHoursGb
    video = $videoSummary
    audio_tracks = $audioResults
    audio_preview_files = @($audioPreviewFiles)
    control_frames_directory = $outputFullPath
    errors = @($errors)
    warnings = @($warnings)
}

$reportPath = Join-Path $outputFullPath "verification-report.json"
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding UTF8

Write-Host "Статус: $($report.status)"
Write-Host "Видео: $($videoSummary.width)x$($videoSummary.height), $($videoSummary.fps) кадр/с"
Write-Host "Аудиодорожек: $($audioStreams.Count)"
Write-Host "Оценка двух часов с запасом 25%: $estimatedTwoHoursGb GB"
Write-Host "Контрольные кадры, аудиофайлы и отчёт: $outputFullPath"
foreach ($warning in $warnings) { Write-Warning $warning }
foreach ($errorMessage in $errors) { Write-Error $errorMessage -ErrorAction Continue }

if ($errors.Count -gt 0) { exit 2 }
exit 0
