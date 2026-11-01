[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$ResourcesPath,
  [Parameter(Mandatory=$true)][string]$CadImportBridgePath,
  [int]$Port = 8090,
  [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resources = (Resolve-Path $ResourcesPath).Path
$bridge = (Resolve-Path $CadImportBridgePath).Path
if (-not (Test-Path (Join-Path $resources "Data\DGBData.db"))) { throw "RoBAS resources are missing Data\DGBData.db" }
if (-not (Test-Path $bridge)) { throw "CADImport bridge not found: $bridge" }
if (-not (Test-Path (Join-Path $root "dist\rolling.html"))) { throw "Vite production build is missing: run npm run build first" }
Push-Location $root
try {
  & $Python (Join-Path $root "bridge/cadimport/preflight.py") --resources $resources --bridge $bridge --out (Join-Path $root "artifacts/cadimport/environment_report.json")
  if ($LASTEXITCODE -ne 0) { throw "RoBAS resource preflight failed; inspect artifacts/cadimport/environment_report.json" }
  & $Python -m bearing_cad.api --port $Port --static (Join-Path $root "dist") --robas-resources $resources --cadimport-bridge $bridge
} finally { Pop-Location }
