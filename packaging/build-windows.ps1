# Build FFConverter for Windows (64-bit).
#
# Produces:
#   dist/FFConverter-<version>-windows-x86_64.exe   (single-file, FFmpeg inside)
#   dist/FFConverter-<version>-windows-x86_64.zip   (portable folder + FFmpeg)
#
# Usage (from the repository root, in PowerShell):
#   .\packaging\build-windows.ps1
#   .\packaging\build-windows.ps1 -FfmpegDir C:\ffmpeg\bin
#
# FFmpeg/FFprobe are downloaded from BtbN's GPL builds unless -FfmpegDir is
# supplied. The application itself is GPL-3.0-or-later.

param(
    [string]$FfmpegDir = "",
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$versionMatch = Select-String -Path (Join-Path $Root "ffc.py") `
    -Pattern '^__version__ = "([^"]+)"' | Select-Object -First 1
if (-not $versionMatch) {
    throw "cannot read version from ffc.py"
}
$Version = $versionMatch.Matches[0].Groups[1].Value

if ([IO.Path]::IsPathRooted($OutputDir)) {
    $Out = $OutputDir
} else {
    $Out = Join-Path $Root $OutputDir
}
New-Item -ItemType Directory -Path $Out -Force | Out-Null

$Build = Join-Path $Root "build\windows"
if (Test-Path $Build) {
    Remove-Item -Recurse -Force $Build
}
New-Item -ItemType Directory -Path $Build -Force | Out-Null

function Invoke-Python {
    param([string]$Python, [string[]]$Arguments)
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "command failed: $Python $($Arguments -join ' ')"
    }
}

Write-Host "==> Creating Python environment"
$Venv = Join-Path $Build "venv"
Invoke-Python "python" @("-m", "venv", $Venv)
$Py = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Py)) {
    throw "Python venv was not created at $Venv"
}

Write-Host "==> Installing Python dependencies"
$Wheels = Join-Path $Root "pip-wheels"
Invoke-Python $Py @(
    "-m", "pip", "install", "--no-index", "--find-links", $Wheels,
    "--disable-pip-version-check",
    "customtkinter==5.2.2", "darkdetect==0.8.0", "packaging==26.2",
    "send2trash==2.1.0", "tkinterdnd2==0.4.3"
)
Invoke-Python $Py @(
    "-m", "pip", "install", "--disable-pip-version-check",
    "pyinstaller==6.11.1"
)

if (-not $FfmpegDir) {
    Write-Host "==> Downloading FFmpeg (BtbN GPL build, ~200 MB)"
    $ffmpegZip = Join-Path $Build "ffmpeg.zip"
    $ffmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    Invoke-WebRequest -Uri $ffmpegUrl -OutFile $ffmpegZip
    $ffmpegRoot = Join-Path $Build "ffmpeg"
    Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegRoot -Force

    $ffmpegExe = Get-ChildItem $ffmpegRoot -Recurse -Filter "ffmpeg.exe" |
        Select-Object -First 1
    if (-not $ffmpegExe) {
        throw "ffmpeg.exe was not found in the downloaded archive"
    }
    $FfmpegDir = $ffmpegExe.DirectoryName
}

$FfmpegDir = (Resolve-Path $FfmpegDir).Path
$ffmpeg = Join-Path $FfmpegDir "ffmpeg.exe"
$ffprobe = Join-Path $FfmpegDir "ffprobe.exe"
if (-not (Test-Path $ffmpeg) -or -not (Test-Path $ffprobe)) {
    throw "ffmpeg.exe and ffprobe.exe must exist in $FfmpegDir"
}

$CommonArgs = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean",
    "--name", "FFConverter",
    "--windowed",
    "--icon", (Join-Path $Root "resources\icon.ico"),
    "--add-data", "$Root\resources;resources",
    "--add-data", "$Root\ffconverter.png;.",
    "--collect-all", "customtkinter",
    "--collect-all", "tkinterdnd2"
)
$Script = Join-Path $Root "ffc.py"

Write-Host "==> Building single-file EXE"
$OneDist = Join-Path $Build "onefile-dist"
$OneWork = Join-Path $Build "onefile-work"
$OneSpec = Join-Path $Build "onefile-spec"
New-Item -ItemType Directory -Path $OneSpec -Force | Out-Null
$OneArgs = $CommonArgs + @(
    "--onefile",
    "--add-binary", "$ffmpeg;.",
    "--add-binary", "$ffprobe;.",
    "--distpath", $OneDist,
    "--workpath", $OneWork,
    "--specpath", $OneSpec,
    $Script
)
Invoke-Python $Py $OneArgs

$OneExe = Join-Path $OneDist "FFConverter.exe"
if (-not (Test-Path $OneExe)) {
    throw "single-file build did not produce FFConverter.exe"
}
$OneTarget = Join-Path $Out "FFConverter-$Version-windows-x86_64.exe"
Copy-Item $OneExe $OneTarget -Force

Write-Host "==> Building portable folder"
$DirDist = Join-Path $Build "onedir-dist"
$DirWork = Join-Path $Build "onedir-work"
$DirSpec = Join-Path $Build "onedir-spec"
New-Item -ItemType Directory -Path $DirSpec -Force | Out-Null
$DirArgs = $CommonArgs + @(
    "--onedir",
    "--distpath", $DirDist,
    "--workpath", $DirWork,
    "--specpath", $DirSpec,
    $Script
)
Invoke-Python $Py $DirArgs

$AppDir = Join-Path $DirDist "FFConverter"
if (-not (Test-Path (Join-Path $AppDir "FFConverter.exe"))) {
    throw "portable build did not produce FFConverter.exe"
}
Copy-Item $ffmpeg $AppDir -Force
Copy-Item $ffprobe $AppDir -Force
Copy-Item (Join-Path $Root "LICENSE") $AppDir -Force
Copy-Item (Join-Path $Root "THIRD_PARTY_NOTICES.md") $AppDir -Force
Copy-Item (Join-Path $Root "packaging\README-windows.txt") `
    (Join-Path $AppDir "README.txt") -Force

# Keep FFmpeg's license and a record of the exact build/source URL.
$ffmpegParent = Split-Path -Parent $FfmpegDir
Get-ChildItem $ffmpegParent -Filter "LICENSE*" -File -ErrorAction SilentlyContinue |
    ForEach-Object { Copy-Item $_.FullName $AppDir -Force }
& $ffmpeg -version | Out-File (Join-Path $AppDir "FFMPEG-BUILD.txt") -Encoding utf8
Add-Content (Join-Path $AppDir "FFMPEG-BUILD.txt") `
    "Source: https://github.com/BtbN/FFmpeg-Builds/releases/tag/latest"

$ZipTarget = Join-Path $Out "FFConverter-$Version-windows-x86_64.zip"
Compress-Archive -Path $AppDir -DestinationPath $ZipTarget -CompressionLevel Optimal -Force

Write-Host "==> Smoke-testing executables"
foreach ($exe in @($OneTarget, (Join-Path $AppDir "FFConverter.exe"))) {
    $process = Start-Process -FilePath $exe -ArgumentList "--version" `
        -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -ne 0) {
        throw "smoke test failed for $exe (exit code $($process.ExitCode))"
    }
}

foreach ($file in @($OneTarget, $ZipTarget)) {
    $hash = (Get-FileHash -Path $file -Algorithm SHA256).Hash.ToLower()
    $name = Split-Path -Leaf $file
    "$hash  $name" | Set-Content "$file.sha256" -Encoding ascii
    Write-Host ("built {0} ({1:N1} MB)" -f $name, ((Get-Item $file).Length / 1MB))
}
