// Minimal faithful RoBAS DWG -> CADText exact match -> DXF probe.
// Source: RoBAS/Frm/FrmMain.cs LoadCadAndChangeText, ChangeCADTexts.
// Requires licensed CADImport 14.1.0.40930 on Windows .NET Framework 4.5.2.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Web.Script.Serialization;
using CADImport;

namespace BearingCad.CadImportBridge
{
    internal static class Program
    {
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

        private static int Main(string[] args)
        {
            try
            {
                if (args.Length != 2 && args.Length != 5)
                    throw new ArgumentException(
                        "Usage: CadImportBridge.exe inspect <original.dwg> OR replace <original.dwg> <result.dxf> <key> <value>");

                bool replace = args[0] == "replace" && args.Length == 5;
                bool inspect = args[0] == "inspect" && args.Length == 2;
                if (!replace && !inspect)
                    throw new ArgumentException("Unsupported mode. Use inspect or replace.");

                string sourcePath = Path.GetFullPath(args[1]);
                if (!File.Exists(sourcePath) ||
                    !String.Equals(Path.GetExtension(sourcePath), ".dwg", StringComparison.OrdinalIgnoreCase))
                    throw new ArgumentException("Source must be an existing DWG template.");

                string destination = null;
                string key = null;
                string value = null;
                if (replace)
                {
                    destination = Path.GetFullPath(args[2]);
                    key = args[3];
                    value = args[4];
                    if (String.IsNullOrWhiteSpace(key) || String.IsNullOrEmpty(value) ||
                        key.Contains("\r") || key.Contains("\n") ||
                        value.Contains("\r") || value.Contains("\n"))
                        throw new ArgumentException("Key and replacement must be non-empty single-line text.");
                    if (String.Equals(sourcePath, destination, StringComparison.OrdinalIgnoreCase) ||
                        !String.Equals(Path.GetExtension(destination), ".dxf", StringComparison.OrdinalIgnoreCase) ||
                        File.Exists(destination) || !Directory.Exists(Path.GetDirectoryName(destination)))
                        throw new ArgumentException("Output must be a new .dxf in an existing directory, different from DWG.");
                }

                CADImage image = CADImage.CreateImageByExtension(sourcePath);
                image.LoadFromFile(sourcePath);
                if (image.CurrentLayout == null)
                    throw new InvalidDataException("CADImport returned no CurrentLayout.");

                int total = image.CurrentLayout.Count;
                int textEntities = 0;
                int replaced = 0;
                List<string> originalTexts = new List<string>();
                for (int i = 0; i < total; ++i)
                {
                    var entity = image.CurrentLayout.Entities[i];
                    if (entity.EntType != EntityType.Text)
                        continue; // Original RoBAS semantics: no MText, ATTRIB, block expansion.
                    ++textEntities;
                    CADText cadText = (CADText)entity;
                    string original = cadText.Text ?? "";
                    originalTexts.Add(original);
                    if (replace && String.Equals(original, key, StringComparison.Ordinal))
                    {
                        cadText.Text = value;
                        ++replaced;
                    }
                }

                if (replace)
                {
                    if (replaced == 0)
                        throw new InvalidDataException("No CADText exactly matched the requested key: " + key);
                    CADImport.Export.DirectCADtoDXF.CADtoDXF exporter =
                        new CADImport.Export.DirectCADtoDXF.CADtoDXF(image);
                    exporter.SaveToFile(destination);
                    if (!File.Exists(destination) || new FileInfo(destination).Length == 0)
                        throw new InvalidDataException("Exporter returned without creating a non-empty DXF.");
                }

                Dictionary<string, object> report = new Dictionary<string, object>();
                report["mode"] = inspect ? "inspect" : "replace";
                report["source"] = sourcePath;
                report["output"] = destination;
                report["layout_entity_count"] = total;
                report["text_entity_count"] = textEntities;
                report["non_text_entity_count"] = total - textEntities;
                report["exact_match_count"] = replaced;
                report["target_key"] = key;
                report["texts"] = originalTexts;
                report["status"] = "CADIMPORT_COMPLETED_NOT_YET_DXF_AUDITED";
                Console.WriteLine(Json.Serialize(report));
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("CADIMPORT_SPIKE_FAILED: " + ex);
                return 2;
            }
        }
    }
}
