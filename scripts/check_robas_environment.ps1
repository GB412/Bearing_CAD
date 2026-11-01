[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$ResourcesPath,
  [string]$CadImportDllPath,
  [string]$BridgePath,
  [string]$Python = "python",
  [string]$OutputPath = "artifacts/cadimport/environment_report.json"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resources = (Resolve-Path $ResourcesPath).Path
$reportPath = Join-Path $root $OutputPath
$reportDir = Split-Path -Parent $reportPath
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null

if (-not [Environment]::Is64BitOperatingSystem) { throw "Windows x64 required" }
$msbuild = (Get-Command msbuild -ErrorAction SilentlyContinue).Source
if (-not $msbuild) {
  $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
  if (Test-Path $vswhere) {
    $vsInstall = & $vswhere -latest -products * -requires Microsoft.Component.MSBuild -property installationPath
    if ($vsInstall) {
      $candidate = Join-Path $vsInstall "MSBuild\Current\Bin\MSBuild.exe"
      if (Test-Path $candidate) { $msbuild = $candidate }
    }
  }
}
$runtime = [ordered]@{
  os = [Environment]::OSVersion.VersionString
  powershell = $PSVersionTable.PSVersion.ToString()
  python = (& $Python --version 2>&1 | Out-String).Trim()
  dotnet = ((Get-Command dotnet -ErrorAction SilentlyContinue).Source)
  msbuild = $msbuild
  is_64_bit_os = [Environment]::Is64BitOperatingSystem
}
$dll = $null
if ($CadImportDllPath) {
  $dllPath = (Resolve-Path $CadImportDllPath).Path
  try {
    $assembly = [System.Reflection.AssemblyName]::GetAssemblyName($dllPath)
    $dll = [ordered]@{path=$dllPath;size_bytes=(Get-Item $dllPath).Length;sha256=(Get-FileHash $dllPath -Algorithm SHA256).Hash.ToLowerInvariant();assembly_full_name=$assembly.FullName;version=$assembly.Version.ToString();processor_architecture=$assembly.ProcessorArchitecture.ToString()}
  } catch {
    $dll = [ordered]@{path=$dllPath;error=$_.Exception.Message}
  }
}
$args = @((Join-Path $root "bridge/cadimport/preflight.py"), "--resources", $resources, "--out", $reportPath)
if ($BridgePath) { $args += @("--bridge", (Resolve-Path $BridgePath).Path) }
& $Python @args | Out-Null
# Windows PowerShell 5.1 uses the system ANSI code page for Get-Content by
# default. The Python preflight emits UTF-8 JSON with Chinese resource names,
# so read the file explicitly as UTF-8 before parsing it.
$resourceJson = [System.IO.File]::ReadAllText($reportPath, [System.Text.Encoding]::UTF8)
$resourceReport = $resourceJson | ConvertFrom-Json
$combined = [ordered]@{
  schema_version = "robas.environment.v1"
  status = $resourceReport.status
  resources = $resourceReport
  runtime = $runtime
  cadimport = $dll
  generated_at_utc = [DateTime]::UtcNow.ToString("o")
}
$combined | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Get-Content -LiteralPath $reportPath -Raw
if ($resourceReport.status -ne "READY_FOR_CADIMPORT") { exit 2 }
