# Back up the scientific record (processed + raw). Usage: scripts\backup.ps1 [-Data .\data] [-Dest .\backups]
param([string]$Data = ".\data", [string]$Dest = ".\backups")
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
New-Item -ItemType Directory -Force $Dest | Out-Null
$out = Join-Path $Dest "globalclimatelens_$stamp.zip"
Compress-Archive -Path (Join-Path $Data "processed"), (Join-Path $Data "raw") -DestinationPath $out -Force
(Get-FileHash $out -Algorithm SHA256).Hash | Out-File "$out.sha256" -Encoding ascii
Write-Output "backup written: $out"
