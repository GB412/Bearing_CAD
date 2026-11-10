[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$ResourcesPath,
  [Parameter(Mandatory=$true)][string]$CadImportBridgePath,
  [int]$Port = 8090,
  [string]$Python = "python",
  [string]$AnalysisProfilesPath
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resources = (Resolve-Path $ResourcesPath).Path
$bridge = (Resolve-Path $CadImportBridgePath).Path
if (-not (Test-Path (Join-Path $resources "Data\DGBData.db"))) { throw "RoBAS resources are missing Data\DGBData.db" }
if (-not (Test-Path $bridge)) { throw "CADImport bridge not found: $bridge" }
if (-not (Test-Path (Join-Path $root "dist\rolling.html"))) { throw "Vite production build is missing: run npm run build first" }
$apiArgs = @("-m", "bearing_cad.api", "--port", $Port, "--static", (Join-Path $root "dist"),
  "--robas-resources", $resources, "--cadimport-bridge", $bridge)
if (-not [string]::IsNullOrWhiteSpace($AnalysisProfilesPath)) {
  if (-not (Test-Path -LiteralPath $AnalysisProfilesPath -PathType Leaf)) {
    throw "RoBAS analysis profile manifest not found: $AnalysisProfilesPath"
  }
  $apiArgs += @("--robas-analysis-profiles", (Resolve-Path -LiteralPath $AnalysisProfilesPath).Path)
}
Push-Location $root
try {
  & $Python (Join-Path $root "bridge/cadimport/preflight.py") --resources $resources --bridge $bridge --out (Join-Path $root "artifacts/cadimport/environment_report.json")
  if ($LASTEXITCODE -ne 0) { throw "RoBAS resource preflight failed; inspect artifacts/cadimport/environment_report.json" }
  & $Python @apiArgs
  if ($LASTEXITCODE -ne 0) { throw "Bearing_CAD API exited with code $LASTEXITCODE" }
} finally { Pop-Location }
