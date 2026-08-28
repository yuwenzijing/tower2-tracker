$ErrorActionPreference = 'Stop'
$CollectorRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = if ($env:BUYALI_BUILD_PYTHON) { $env:BUYALI_BUILD_PYTHON } elseif (Test-Path 'C:\tmp\buyali-python\python.exe') { 'C:\tmp\buyali-python\python.exe' } else { 'python.exe' }
$ReleaseRoot = Join-Path $CollectorRoot 'release'
$Version = '1.3.4.1'
$PackageRoot = Join-Path $ReleaseRoot "BuyaliCollector-v$Version"
if (Test-Path $PackageRoot) { Remove-Item -LiteralPath $PackageRoot -Recurse -Force }
New-Item -ItemType Directory -Path $PackageRoot -Force | Out-Null
& $PythonExe "$CollectorRoot\extract_class_icons.py"
& $PythonExe -m PyInstaller --noconfirm --clean --windowed --name 'BuyaliCollector' --icon "$CollectorRoot\assets\icons\buyali-collector.ico" --distpath $ReleaseRoot --workpath "$CollectorRoot\build" --specpath "$CollectorRoot" --exclude-module pandas --collect-all rapidocr_onnxruntime --add-data "$CollectorRoot\assets;assets" "$CollectorRoot\main.py"
$BuiltRoot = Join-Path $ReleaseRoot 'BuyaliCollector'
Move-Item -LiteralPath (Join-Path $BuiltRoot 'BuyaliCollector.exe') -Destination (Join-Path $PackageRoot 'BuyaliCollector.exe')
Move-Item -LiteralPath (Join-Path $BuiltRoot '_internal') -Destination (Join-Path $PackageRoot '_internal')
Remove-Item -LiteralPath $BuiltRoot -Force
$ReadmeName = (-join ((0x4F7F, 0x7528, 0x8BF4, 0x660E) | ForEach-Object { [char]$_ })) + '.txt'
Copy-Item -LiteralPath "$CollectorRoot\README.md" -Destination (Join-Path $PackageRoot $ReadmeName) -Force
$ZipPath = Join-Path $ReleaseRoot "BuyaliCollector-v$Version.zip"
if (Test-Path $ZipPath) { Remove-Item -LiteralPath $ZipPath -Force }
Compress-Archive -LiteralPath $PackageRoot -DestinationPath $ZipPath -CompressionLevel Optimal
