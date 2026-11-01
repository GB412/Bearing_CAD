[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$CadImportDllPath,
  [string]$Configuration = "Release",
  [string]$MsBuildPath
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$project = Join-Path $root "bridge/cadimport/CadImportBridge.csproj"
$dll = (Resolve-Path $CadImportDllPath).Path
if (-not [Environment]::Is64BitOperatingSystem) { throw "Windows x64 required" }
if (-not $MsBuildPath) { $MsBuildPath = (Get-Command msbuild -ErrorAction SilentlyContinue).Source }
if (-not $MsBuildPath) {
  $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
  if (Test-Path $vswhere) {
    $vsInstall = & $vswhere -latest -products * -requires Microsoft.Component.MSBuild -property installationPath
    if ($vsInstall) {
      $candidate = Join-Path $vsInstall "MSBuild\Current\Bin\MSBuild.exe"
      if (Test-Path $candidate) { $MsBuildPath = $candidate }
    }
  }
}
if (-not $MsBuildPath) { throw "MSBuild not found. Use a Visual Studio Developer PowerShell or pass -MsBuildPath." }
$targetingPack = Join-Path ${env:ProgramFiles(x86)} "Reference Assemblies\Microsoft\Framework\.NETFramework\v4.5.2\mscorlib.dll"
if (-not (Test-Path $targetingPack)) { throw ".NET Framework 4.5.2 targeting pack was not found: $targetingPack" }
& $MsBuildPath $project "/p:Configuration=$Configuration" "/p:Platform=x64" "/p:CadImportDllPath=$dll" "/verbosity:minimal"
if ($LASTEXITCODE -ne 0) { throw "CADImport bridge compilation failed" }
$exe = Join-Path $root "bridge/cadimport/bin/$Configuration/CadImportBridge.exe"
if (-not (Test-Path $exe)) { throw "Compiled bridge not found: $exe" }
& $exe doctor
if ($LASTEXITCODE -ne 0) { throw "CADImport bridge doctor failed" }
Write-Host "Bridge ready: $exe"
