# CADImport DWG bridge

This project preserves the RoBAS drawing path: `CADImage.CreateImageByExtension`, `LoadFromFile`, current-layout `EntityType.Text`/`CADText.Text` replacement, and `CADtoDXF.SaveToFile`. It does not redraw geometry and deliberately does not add MTEXT or block-attribute replacement.

Build only on licensed Windows x64 with .NET Framework 4.5.2 targeting tools and the licensed CADImport assembly:

```powershell
msbuild CadImportBridge.csproj /p:Configuration=Release /p:Platform=x64 /p:CadImportDllPath="C:\licensed\CADImport.dll"
.\bin\Release\CadImportBridge.exe doctor
```

The DLL, DWG templates, SQLite databases and fonts must stay outside Git. Run `scripts/check_robas_environment.ps1` before using the bridge. The bridge cannot be considered deployed until a real DWG inspect, replacement, DXF audit, and GUI CAD open have been recorded.
