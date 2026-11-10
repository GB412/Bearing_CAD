[CmdletBinding()]
param(
  [string]$ConfigPath = "config/robas.local.json",
  [string]$Configuration = "Release",
  [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$configFile = if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $root $ConfigPath }
if (-not (Test-Path -LiteralPath $configFile)) {
  throw "Local config not found: $configFile. Copy config/robas.local.example.json first."
}
$config = [System.IO.File]::ReadAllText($configFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
foreach ($name in @("resources_path", "cadimport_dll_path")) {
  if ([string]::IsNullOrWhiteSpace($config.$name)) { throw "Missing config property: $name" }
}
$resources = (Resolve-Path $config.resources_path).Path
$dll = (Resolve-Path $config.cadimport_dll_path).Path
$bridge = Join-Path $root "bridge\cadimport\bin\$Configuration\CadImportBridge.exe"
$python = if ([string]::IsNullOrWhiteSpace($config.python)) { "python" } else { [string]$config.python }
$port = if ($config.port) { [int]$config.port } else { 8090 }
$startArgs = @{ ResourcesPath = $resources; CadImportBridgePath = $bridge; Port = $port; Python = $python }
if (-not [string]::IsNullOrWhiteSpace($config.analysis_profiles_path)) {
  $profiles = [string]$config.analysis_profiles_path
  if (-not [System.IO.Path]::IsPathRooted($profiles)) {
    $profiles = Join-Path (Split-Path -Parent $configFile) $profiles
  }
  $startArgs.AnalysisProfilesPath = $profiles
}

Push-Location $root
try {
  & (Join-Path $root "scripts\check_robas_environment.ps1") `
    -ResourcesPath $resources -CadImportDllPath $dll
  if ($LASTEXITCODE -ne 0) { throw "RoBAS resource preflight failed" }
  if (-not $SkipBuild) {
    & (Join-Path $root "scripts\build_cadimport_bridge.ps1") `
      -CadImportDllPath $dll -Configuration $Configuration
    if ($LASTEXITCODE -ne 0) { throw "CADImport bridge build failed" }
  }
  & (Join-Path $root "scripts\start_bearing_cad_with_robas.ps1") @startArgs
} finally {
  Pop-Location
}
