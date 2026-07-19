[CmdletBinding()]
param(
    [switch]$AsJson
)

$ErrorActionPreference = "Stop"

function Get-CommandPath {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command) { return $command.Source }

    if ($Name -in @("ffmpeg.exe", "ffprobe.exe")) {
        $wingetPackages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        if (Test-Path -LiteralPath $wingetPackages) {
            $match = Get-ChildItem -LiteralPath $wingetPackages -Recurse -Filter $Name -File -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match 'Gyan\.FFmpeg' } |
                Select-Object -First 1
            if ($match) { return $match.FullName }
        }
    }

    return $null
}

function Get-CimSafe {
    param(
        [Parameter(Mandatory = $true)][string]$ClassName,
        [string]$Filter
    )
    try {
        if ($Filter) { return @(Get-CimInstance -ClassName $ClassName -Filter $Filter -ErrorAction Stop) }
        return @(Get-CimInstance -ClassName $ClassName -ErrorAction Stop)
    } catch {
        return @()
    }
}

$os = @(Get-CimSafe -ClassName "Win32_OperatingSystem") | Select-Object -First 1
$cpu = @(Get-CimSafe -ClassName "Win32_Processor") | Select-Object -First 1
$computer = @(Get-CimSafe -ClassName "Win32_ComputerSystem") | Select-Object -First 1
$gpus = @(Get-CimSafe -ClassName "Win32_VideoController" | ForEach-Object {
    [pscustomobject]@{
        name = $_.Name
        driver_version = $_.DriverVersion
        adapter_ram_gb = if ($_.AdapterRAM) { [math]::Round($_.AdapterRAM / 1GB, 2) } else { $null }
    }
})

Add-Type -AssemblyName System.Windows.Forms
$screens = @([System.Windows.Forms.Screen]::AllScreens | Sort-Object { $_.Bounds.X } | ForEach-Object {
    [pscustomobject]@{
        device = $_.DeviceName
        primary = $_.Primary
        x = $_.Bounds.X
        y = $_.Bounds.Y
        width = $_.Bounds.Width
        height = $_.Bounds.Height
    }
})

$offset = 0
$recommendedSources = @($screens | ForEach-Object {
    $item = [pscustomobject]@{
        device = $_.device
        x = $offset
        y = 0
        width = $_.width
        height = $_.height
    }
    $offset += $_.width
    $item
})

$audioEndpoints = @()
if (Get-Command Get-PnpDevice -ErrorAction SilentlyContinue) {
    $audioEndpoints = @(Get-PnpDevice -Class AudioEndpoint -PresentOnly -ErrorAction SilentlyContinue | ForEach-Object {
        [pscustomobject]@{
            name = $_.FriendlyName
            status = $_.Status
            instance_id = $_.InstanceId
        }
    })
}
if ($audioEndpoints.Count -eq 0) {
    $audioEndpoints = @(Get-CimSafe -ClassName "Win32_SoundDevice" | ForEach-Object {
        [pscustomobject]@{
            name = $_.Name
            status = $_.Status
            instance_id = $_.DeviceID
        }
    })
}

$obsCandidates = @(
    (Get-CommandPath -Name "obs64.exe"),
    "$env:ProgramFiles\obs-studio\bin\64bit\obs64.exe",
    "${env:ProgramFiles(x86)}\obs-studio\bin\64bit\obs64.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$obsPath = $obsCandidates | Select-Object -First 1
$obsVersion = if ($obsPath) { (Get-Item -LiteralPath $obsPath).VersionInfo.FileVersion } else { $null }

$fixedDisks = @(Get-CimSafe -ClassName "Win32_LogicalDisk" -Filter "DriveType=3" | ForEach-Object {
    [pscustomobject]@{
        drive = $_.DeviceID
        free_gb = [math]::Round($_.FreeSpace / 1GB, 1)
        size_gb = [math]::Round($_.Size / 1GB, 1)
    }
})
if ($fixedDisks.Count -eq 0) {
    $fixedDisks = @(Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Root -match '^[A-Za-z]:\\$' } | ForEach-Object {
        [pscustomobject]@{
            drive = $_.Name + ":"
            free_gb = if ($null -ne $_.Free) { [math]::Round($_.Free / 1GB, 1) } else { $null }
            size_gb = if ($null -ne $_.Free -and $null -ne $_.Used) { [math]::Round(($_.Free + $_.Used) / 1GB, 1) } else { $null }
        }
    })
}

$result = [pscustomobject]@{
    collected_at = (Get-Date).ToString("o")
    windows = [pscustomobject]@{
        caption = if ($os) { $os.Caption } else { "Windows" }
        version = if ($os) { $os.Version } else { [Environment]::OSVersion.Version.ToString() }
        build = if ($os) { $os.BuildNumber } else { [Environment]::OSVersion.Version.Build }
        architecture = if ($os) { $os.OSArchitecture } elseif ([Environment]::Is64BitOperatingSystem) { "64-bit" } else { "32-bit" }
    }
    hardware = [pscustomobject]@{
        cpu = if ($cpu) { $cpu.Name } else { $env:PROCESSOR_IDENTIFIER }
        logical_processors = if ($computer) { $computer.NumberOfLogicalProcessors } else { [Environment]::ProcessorCount }
        memory_gb = if ($computer -and $computer.TotalPhysicalMemory) { [math]::Round($computer.TotalPhysicalMemory / 1GB, 1) } else { $null }
        gpu = $gpus
        fixed_disks = $fixedDisks
    }
    displays = $screens
    recommended_canvas = [pscustomobject]@{
        width = ($screens | Measure-Object -Property width -Sum).Sum
        height = ($screens | Measure-Object -Property height -Maximum).Maximum
        sources = $recommendedSources
    }
    audio_endpoints = $audioEndpoints
    tools = [pscustomobject]@{
        obs_path = $obsPath
        obs_version = $obsVersion
        ffmpeg_path = Get-CommandPath -Name "ffmpeg.exe"
        ffprobe_path = Get-CommandPath -Name "ffprobe.exe"
        winget_path = Get-CommandPath -Name "winget.exe"
    }
}

if ($AsJson) {
    $result | ConvertTo-Json -Depth 8
    exit 0
}

Write-Host "Windows: $($result.windows.caption), $($result.windows.architecture)"
$memoryText = if ($null -ne $result.hardware.memory_gb) { "$($result.hardware.memory_gb) GB" } else { "не удалось прочитать" }
Write-Host "CPU: $($result.hardware.cpu); RAM: $memoryText"
Write-Host "Мониторы: $($screens.Count); рекомендуемый холст: $($result.recommended_canvas.width)x$($result.recommended_canvas.height)"
foreach ($screen in $recommendedSources) {
    Write-Host "  $($screen.device): $($screen.width)x$($screen.height), позиция OBS X=$($screen.x), Y=0"
}
Write-Host "OBS: $(if ($obsPath) { $obsVersion } else { 'не найден' })"
Write-Host "FFmpeg/ffprobe: $(if ($result.tools.ffmpeg_path -and $result.tools.ffprobe_path) { 'найдены' } else { 'неполный комплект' })"
Write-Host "Аудиоустройства:"
foreach ($endpoint in $audioEndpoints) { Write-Host "  [$($endpoint.status)] $($endpoint.name)" }
if ($audioEndpoints.Count -eq 0) { Write-Host "  не удалось прочитать; проверьте список устройств в Windows и OBS" }
Write-Host "Свободное место:"
foreach ($disk in $fixedDisks) {
    $freeText = if ($null -ne $disk.free_gb) { "$($disk.free_gb) GB" } else { "не удалось прочитать" }
    $sizeText = if ($null -ne $disk.size_gb) { "$($disk.size_gb) GB" } else { "не удалось прочитать" }
    Write-Host "  $($disk.drive) $freeText из $sizeText"
}

if ($screens.Count -ne 2) {
    Write-Warning "Обнаружено $($screens.Count) мониторов. Профиль skill рассчитан на два; согласуйте адаптацию до настройки OBS."
}
