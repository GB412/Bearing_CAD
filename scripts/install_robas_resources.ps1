# Prepare licensed local RoBAS runtime assets OUTSIDE the Git repository.
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\install_robas_resources.ps1 `
#     -ArchivePath "D:\Downloads\RoBAS_Resources.zip" `
#     -CadImportDllPath "D:\Downloads\CADImport.dll"
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ArchivePath,
    [string]$WorkspaceRoot = "",
    [string]$CadImportDllPath = "",
    [int]$Port = 8090
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
    $WorkspaceRoot = (Resolve-Path (Join-Path $repo "..")).Path
}
if (-not (Test-Path -LiteralPath $WorkspaceRoot -PathType Container)) {
    throw "Workspace root not found: $WorkspaceRoot"
}
$WorkspaceRoot = (Resolve-Path -LiteralPath $WorkspaceRoot).Path
$zip = (Resolve-Path -LiteralPath $ArchivePath).Path
$target = Join-Path $WorkspaceRoot "RoBAS_Resources"
if (Test-Path -LiteralPath $target) {
    throw "RoBAS_Resources already exists; refusing to overwrite: $target"
}
# The user-supplied ZIP contains one top-level RoBAS_Resources/ directory.
Expand-Archive -LiteralPath $zip -DestinationPath $WorkspaceRoot
foreach ($relative in @(
    "Data\DGBData.db", "Data\ACBData.db", "Data\CRBData.db",
    "Resource\BallDB.csv", "Resource\CylinderRollerDB.csv",
    "Resource\CylinderRollerDiameterDB.csv",
    "Resource\哑图\单列圆柱DWG\N-00.dwg",
    "Resource\哑图\单列圆柱DWG\NU-00.dwg",
    "Resource\哑图\单列圆柱DWG\NJ-00.dwg",
    "Resource\哑图\单列圆柱DWG\NF-00.dwg",
    "Resource\哑图\单列圆柱DWG\NUP-00.dwg",
    "Resource\哑图\单列圆柱DWG\NUP-12.dwg",
    "Resource\shx\hztxt.shx"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $target $relative) -PathType Leaf)) {
        throw "Required asset missing after extraction: $relative"
    }
}
# Licensed CADImport is NOT a public redistribution dependency.
$licensedDir = Join-Path $WorkspaceRoot "RoBAS_Licensed"
New-Item -ItemType Directory -Path $licensedDir -Force | Out-Null
$dll = Join-Path $licensedDir "CADImport.dll"
if (-not [string]::IsNullOrWhiteSpace($CadImportDllPath)) {
    $from = (Resolve-Path -LiteralPath $CadImportDllPath).Path
    if ((Resolve-Path -LiteralPath $dll -ErrorAction SilentlyContinue) -and $from -ne $dll) {
        throw "CADImport.dll already exists; refusing to overwrite: $dll"
    }
    if ($from -ne $dll) {
        Copy-Item -LiteralPath $from -Destination $dll
    }
}
$configFile = Join-Path $repo "config\robas.local.json"
if (Test-Path -LiteralPath $configFile) {
    throw "Local configuration exists; refusing to overwrite: $configFile"
}
@{
    resources_path = $target
    cadimport_dll_path = $dll
    python = "python"
    port = $Port
} | ConvertTo-Json | Set-Content -LiteralPath $configFile -Encoding UTF8
Write-Host "RoBAS resources:  $target"
Write-Host "CADImport runtime: $dll"
Write-Host "Local config:      $configFile"
Write-Host "AutoCAD SHX path:  $(Join-Path $target 'Resource\shx')"
if (-not (Test-Path -LiteralPath $dll -PathType Leaf)) {
    Write-Warning "Place your licensed CADImport.dll at $dll before starting the 2D bridge."
}
Write-Host "Next: activate conda, run 'npm ci', 'npm run build', then '.\scripts\run_bearing_cad_with_robas.ps1'"
