$ErrorActionPreference = 'Stop'
$CollectorRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = if ($env:BUYALI_BUILD_PYTHON) { $env:BUYALI_BUILD_PYTHON } elseif (Test-Path 'C:\tmp\buyali-python\python.exe') { 'C:\tmp\buyali-python\python.exe' } else { 'python.exe' }
$ReleaseRoot = Join-Path $CollectorRoot 'release'
New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null
$OldSingleFile = Join-Path $ReleaseRoot 'BuyaliCollector.exe'
if (Test-Path $OldSingleFile) { Remove-Item -LiteralPath $OldSingleFile -Force }
$LegacyRuntime = Join-Path $ReleaseRoot 'runtime'
if (Test-Path $LegacyRuntime) { Remove-Item -LiteralPath $LegacyRuntime -Recurse -Force }
& $PythonExe -m PyInstaller --noconfirm --clean --windowed --name 'BuyaliCollector' --distpath $ReleaseRoot --workpath "$CollectorRoot\build" --specpath "$CollectorRoot" --exclude-module pandas --collect-all rapidocr_onnxruntime "$CollectorRoot\main.py"
Copy-Item -LiteralPath "$CollectorRoot\README.md" -Destination "$ReleaseRoot\使用说明.md" -Force
