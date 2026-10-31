# Run on licensed Windows x64 (no upload of third-party binaries).
# powershell -ExecutionPolicy Bypass -File bridge\cadimport\verify_windows.ps1 -Resources "D:\RoBAS_Resources" -CadImportDll "D:\licensed\CADImport.dll"
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Resources,
  [Parameter(Mandatory=$true)][string]$CadImportDll,
  [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$resourcesDir = (Resolve-Path $Resources).Path
$dllFile = (Resolve-Path $CadImportDll).Path
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$msbuild = Get-Command msbuild -ErrorAction Stop
$exe = Join-Path $PSScriptRoot "bin\Release\CadImportBridge.exe"
$out = Join-Path $repoRoot "artifacts\cadimport-real-dwg-check"
if (-not [Environment]::Is64BitOperatingSystem) { throw "Windows x64 required" }
if (-not (Test-Path (Join-Path $resourcesDir "Data\DGBData.db"))) {
  throw "Resources must contain Data and Resource subdirectories"
}
Write-Host "[1/4] Building isolated CADImport bridge..."
& $msbuild.Source (Join-Path $PSScriptRoot "CadImportBridge.csproj") "/p:Configuration=Release" "/p:Platform=x64" "/p:CadImportDllPath=$dllFile" "/verbosity:minimal"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $exe)) {
  throw "CADImport bridge compilation failed"
}
Write-Host "[2/4] Verifying real RoBAS resources..."
& $Python (Join-Path $PSScriptRoot "preflight.py") --resources $resourcesDir
if ($LASTEXITCODE -ne 0) { throw "RoBAS template/SQLite preflight failed" }
Write-Host "[3/4] Enumerating actual DWG TEXT..."
$dwg = Join-Path $resourcesDir "Resource\哑图\深沟球DWG\0_00KS.DWG"
$raw = & $exe inspect $dwg
if ($LASTEXITCODE -ne 0) { throw "CADImport DWG inspect failed" }
$inspection = ($raw | Out-String) | ConvertFrom-Json
$key = @("model", "d", "Dd", "B_", "Dw", "Z") | Where-Object { $inspection.texts -ccontains $_ } | Select-Object -First 1
if ([string]::IsNullOrEmpty($key)) {
  throw "No familiar CADText variable found. Review inspect output before attempting conversion."
}
Write-Host "[4/4] Exporting genuine new DXF..."
if (Test-Path $out) { throw "Move prior output folder first: $out" }
New-Item -ItemType Directory -Path $out | Out-Null
& $Python (Join-Path $PSScriptRoot "preflight.py") --resources $resourcesDir --bridge $exe --sample-key $key --sample-value "CADIMPORT-PROBE-2026" --outdir $out | Set-Content -Path (Join-Path $out "report.json") -Encoding UTF8
if ($LASTEXITCODE -ne 0) { throw "CADImport DWG -> DXF export failed" }
Write-Host "Result: $(Join-Path $out 'real_template_probe.dxf')"
Write-Host "Compare in a real CAD viewer with temp/深沟球轴承总图.dxf. Licensing and dimensions need human signoff."
