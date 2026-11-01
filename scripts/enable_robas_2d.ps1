# One-command licensed RoBAS DWG setup/verification and local Bearing_CAD start.
# Example:
# powershell -ExecutionPolicy Bypass -File .\scripts\enable_robas_2d.ps1 -Resources "D:\RoBAS_Resources" -CadImportDll "D:\CADImport.dll"
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Resources,
  [Parameter(Mandatory=$true)][string]$CadImportDll,
  [string]$Python = "python",
  [int]$Port = 8090,
  [switch]$VerifyOnly
)
$ErrorActionPreference = "Stop"
if ($Port -lt 1 -or $Port -gt 65535) { throw "Port must be within 1..65535." }

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$res = (Resolve-Path -LiteralPath $Resources -ErrorAction Stop).Path
$dll = (Resolve-Path -LiteralPath $CadImportDll -ErrorAction Stop).Path
$bridge = Join-Path $repo "bridge\cadimport\bin\Release\CadImportBridge.exe"
$verify = Join-Path $repo "bridge\cadimport\verify_windows.ps1"

Write-Host "Checking original RoBAS resources, local CADImport.dll, and the Windows bridge..." -ForegroundColor Cyan
& $verify -Resources $res -CadImportDll $dll -Python $Python
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "CADImport verifier did not finish successfully." }
if (-not (Test-Path -LiteralPath $bridge)) { throw "CADImportBridge.exe was not compiled." }
if ($VerifyOnly) {
  Write-Host "Verified one original DWG -> DXF probe. This is not yet the 12-sheet acceptance test." -ForegroundColor Green
  exit 0
}
if (-not (Test-Path -LiteralPath (Join-Path $repo "dist\rolling.html"))) {
  throw "The workbench is not built. In the repository root run: npm ci ; npm run build"
}
Push-Location $repo
try {
  Write-Host "Starting Bearing_CAD at http://127.0.0.1:$Port/rolling.html" -ForegroundColor Green
  Write-Host "Keep this PowerShell window open while using the CAD workbench."
  & $Python -m bearing_cad.api --port $Port --static dist --robas-resources $res --cadimport-bridge $bridge
  if ($LASTEXITCODE -ne 0) { throw "Bearing_CAD server returned exit code $LASTEXITCODE" }
} finally {
  Pop-Location
}
