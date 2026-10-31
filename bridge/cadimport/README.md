# PR-2D-00 | CADImport real DWG bridge spike

This is a **non-production** probe extracted from the exact RoBAS algorithm:
\`RoBAS/Frm/FrmMain.cs:1200-1230,1480-1498\`.

## Local licensed environment (Windows)

- Windows x64, .NET Framework 4.5.2 targeting pack, Visual Studio/MSBuild.
- A **legitimately licensed** original CADImport.dll, version 14.1.0.40930.
- A copy of RoBAS_Resources unpacked outside Git; it contains \`Data\` and \`Resource\` subdirectories.
- Do not commit the actual DLL, database, commercial template or font into this public repository.

Run in **Developer Command Prompt for Visual Studio**:

~~~powershell
cd bridge\cadimport
msbuild CadImportBridge.csproj /p:Configuration=Release /p:Platform=x64 /p:CadImportDllPath="C:\licensed\CADImport.dll"
python preflight.py --resources "D:\RoBAS_Resources" > resource_audit.json
.\bin\Release\CadImportBridge.exe inspect "D:\RoBAS_Resources\Resource\哑图\深沟球DWG\0_00KS.DWG" > dwg_inspect.json
~~~

Inspect \`dwg_inspect.json\` first. Choose a **literal** \`CADText\` key that exists in the source DWG. Then run:

~~~powershell
mkdir generated_probe
python preflight.py --resources "D:\RoBAS_Resources" --bridge ".\bin\Release\CadImportBridge.exe" --sample-key "ACTUAL_KEY_FROM_INSPECT" --sample-value "TEST-123" --outdir generated_probe > probe_report.json
~~~

The probe refuses to overwrite a source DWG or existing DXF, fails if the key was not an exact match, and uses RoBAS's original \`CADImage.CreateImageByExtension / LoadFromFile\`, \`CurrentLayout\` + \`EntityType.Text\`/ \`CADText.Text\`, and \`CADtoDXF.SaveToFile\`.

The Python test opens the **newly exported** DXF with ezdxf and runs an audit. Audit fixes or errors fail closed. Then an engineer must open the DXF in a GUI CAD viewer and compare it to RoBAS's reference DXF for geometry, fonts, layout and symbols.

## Current execution evidence

- Resource ZIP extracted and preflight run under Linux: 12 of 12 default DWG signatures present, three SQLite variable tables readable (118/265/321 rows).
- C# bridge was **not compiled or executed** in this environment: no Windows/.NET Framework/MSBuild. The actual CADImport licence/runtime and its export behaviour remain unverified.
- Reference \`temp/*.dxf\` files have been read with ezdxf, but **do not** count as proof of DWG conversion.
- \`inspect\` enumerates only current-layout TEXT, not block definitions, MTEXT or attributes, matching original RoBAS limitations.

### Required sign-off before PR-2D-01

1. Compile and run the bridge with licensed CADImport in Windows x64.
2. Real DWG load succeeds, key replacement count >0, genuine new DXF exported.
3. DXF opens in a GUI viewer; compare source template and reference outputs.
4. Record CLR/Windows/CADImport version, sample file checksums, geometry-layer-font differences, and licence restrictions.
5. Keep this PR **draft and unmerged** if any of those requirements are blocked.

If CADImport fails, do **not** fake an SVG/ezdxf sketch: record the blocker and evaluate an audited one-time DWG->DXF conversion as an explicit design change.
