# Verify original licensed CADImport DWG -> TEXT -> DXF pipeline on Windows.
# From repo root: powershell -ExecutionPolicy Bypass -File .\bridge\cadimport\verify_windows.ps1 -Resources "D:\RoBAS_Resources" -CadImportDll "D:\CADImport.dll"
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Resources,
  [Parameter(Mandatory=$true)][string]$CadImportDll,
  [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
if (-not [Environment]::Is64BitOperatingSystem) { throw "Windows x64 is required." }
$resourcesDir = (Resolve-Path -LiteralPath $Resources -ErrorAction Stop).Path
$dllFile = (Resolve-Path -LiteralPath $CadImportDll -ErrorAction Stop).Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$exe = Join-Path $PSScriptRoot "bin\Release\CadImportBridge.exe"
$programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
if (-not $programFilesX86) { throw "ProgramFiles(x86) is unavailable; use Windows x64." }

# Find installed MSBuild even when it is not on the PowerShell PATH.
$msbuild = Get-Command msbuild.exe -ErrorAction SilentlyContinue
if ($msbuild) {
  $msbuildExe = $msbuild.Source
} else {
  $vswhere = Join-Path $programFilesX86 "Microsoft Visual Studio\Installer\vswhere.exe"
  $msbuildExe = $null
  if (Test-Path -LiteralPath $vswhere) {
    $candidates = @(& $vswhere -latest -products "*" -requires "Microsoft.Component.MSBuild" -find "MSBuild\**\Bin\MSBuild.exe")
    $msbuildExe = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
  }
  if (-not $msbuildExe) {
    throw "MSBuild not found. Install Visual Studio Build Tools with .NET desktop build tools and the .NET Framework 4.5.2 targeting pack."
  }
}
$targetPack = Join-Path $programFilesX86 "Reference Assemblies\Microsoft\Framework\.NETFramework\v4.5.2"
if (-not (Test-Path -LiteralPath $targetPack)) {
  throw ".NET Framework 4.5.2 targeting pack not found. Install the Developer Pack/targeting pack first."
}
if (-not (Test-Path -LiteralPath (Join-Path $resourcesDir "Data\DGBData.db"))) {
  throw "Resource root must contain Data\DGBData.db and Resource\哑图."
}
if (-not (Test-Path -LiteralPath (Join-Path $resourcesDir "Resource\哑图\深沟球DWG\0_00KS.DWG"))) {
  throw "Original RoBAS DWG templates not found under Resource\哑图."
}
if ([System.IO.Path]::GetExtension($dllFile).ToLowerInvariant() -ne ".dll") {
  throw "-CadImportDll must refer to the original licensed CADImport.dll."
}
Write-Host "[1/4] Checking original RoBAS resources..." -ForegroundColor Cyan
& $Python (Join-Path $PSScriptRoot "preflight.py") --resources $resourcesDir
if ($LASTEXITCODE -ne 0) { throw "RoBAS DWG/SQLite preflight failed." }

Write-Host "[2/4] Compiling the CADImport x64 bridge with local DLL..." -ForegroundColor Cyan
& $msbuildExe (Join-Path $PSScriptRoot "CadImportBridge.csproj") "/p:Configuration=Release" "/p:Platform=x64" "/p:CadImportDllPath=$dllFile" "/verbosity:minimal"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $exe)) {
  throw "C# bridge compilation failed. Copy the complete MSBuild error output."
}
Write-Host "[3/4] Inspecting actual CADText in the source DWG..." -ForegroundColor Cyan
$dwg = Join-Path $resourcesDir "Resource\哑图\深沟球DWG\0_00KS.DWG"
$raw = & $exe inspect $dwg
if ($LASTEXITCODE -ne 0) { throw "Licensed CADImport DWG inspect failed." }
$inspection = ($raw | Out-String) | ConvertFrom-Json
$key = @("model", "d", "Dd", "B_", "Dw", "Z") |
  Where-Object { $inspection.texts -ccontains $_ } | Select-Object -First 1
if ([string]::IsNullOrEmpty($key)) {
  throw "No known source CADText was found. Share the inspect output; do not guess a key."
}
Write-Host "[4/4] Exporting a new DXF from the original DWG..." -ForegroundColor Cyan
$runId = (Get-Date -Format "yyyyMMdd-HHmmss-fff")
$out = Join-Path $repoRoot ("artifacts\cadimport-real-dwg-check-" + $runId)
New-Item -ItemType Directory -Path $out -Force | Out-Null
& $Python (Join-Path $PSScriptRoot "preflight.py") --resources $resourcesDir --bridge $exe --sample-key $key --sample-value "CADIMPORT-PROBE-2026" --outdir $out |
  Set-Content -Path (Join-Path $out "report.json") -Encoding UTF8
if ($LASTEXITCODE -ne 0) {
  throw "CADImport DWG -> DXF failed. Inspect the terminal output; probe outputs were not approved."
}
$dxf = Join-Path $out "real_template_probe.dxf"
if (-not (Test-Path -LiteralPath $dxf)) {
  throw "The real DWG did not produce a DXF."
}
Write-Host "REAL CADIMPORT PROBE COMPLETED" -ForegroundColor Green
Write-Host "Bridge: $exe"
Write-Host "DXF: $dxf"
Write-Host "Report: $(Join-Path $out 'report.json')"
Write-Host "Open the DXF in AutoCAD or another CAD viewer. Verify the text changed and the template was not corrupted."
Write-Host "A successful single-template probe does NOT establish 12-sheet or all-formula parity."
