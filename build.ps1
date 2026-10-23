$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m pytest -q
if ($LASTEXITCODE) {throw 'Tests failed'}
& .\.venv\Scripts\python.exe collect_licenses.py
if ($LASTEXITCODE) {throw 'License collection failed'}
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name AmbientLink --add-data 'ambientlink/panel.html;ambientlink' --add-data 'LICENSE;.' --add-data 'THIRD_PARTY.md;.' --add-data 'build/third-party-licenses;third-party-licenses' --collect-submodules winrt --collect-all dxcam run.py
if ($LASTEXITCODE) {throw 'Packaging failed'}
Get-FileHash .\dist\AmbientLink.exe -Algorithm SHA256 | ForEach-Object { "$($_.Hash.ToLower())  AmbientLink.exe" } | Set-Content .\dist\SHA256SUMS.txt
Copy-Item README.md,LICENSE,THIRD_PARTY.md dist/
Copy-Item build/third-party-licenses dist/ -Recurse -Force
Compress-Archive -Path dist/AmbientLink.exe,dist/SHA256SUMS.txt,dist/README.md,dist/LICENSE,dist/THIRD_PARTY.md,dist/third-party-licenses -DestinationPath dist/AmbientLink-0.1.1-windows-x64.zip -Force
Get-FileHash .\dist\AmbientLink.exe,.\dist\AmbientLink-0.1.1-windows-x64.zip -Algorithm SHA256 | ForEach-Object { "$($_.Hash.ToLower())  $([System.IO.Path]::GetFileName($_.Path))" } | Set-Content .\dist\SHA256SUMS.txt
