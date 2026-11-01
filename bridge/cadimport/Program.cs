// Minimal faithful RoBAS DWG -> CADText exact match -> DXF bridge.
// Source: RoBAS/Frm/FrmMain.cs LoadCadAndChangeText, ChangeCADTexts.
// Windows .NET Framework 4.5.2, licensed CADImport 14.1.0.40930 required.
using System;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;
using CADImport;

namespace BearingCad.CadImportBridge
{
    internal static class Program
    {
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

        public sealed class Replacement
        {
            public string name { get; set; }
            public string value { get; set; }
        }

        private static int Main(string[] args)
        {
            try
            {
                bool inspect = args.Length == 2 && args[0] == "inspect";
                bool replace = args.Length == 5 && args[0] == "replace";
                bool batch = args.Length == 4 && args[0] == "batch";
                if (!inspect && !replace && !batch)
                    throw new ArgumentException(
                        "Usage: inspect <source.dwg> | replace <source.dwg> <out.dxf> <key> <value> | batch <source.dwg> <out.dxf> <variables.json>");

                string source = Path.GetFullPath(args[1]);
                if (!File.Exists(source) ||
                    !String.Equals(Path.GetExtension(source), ".dwg", StringComparison.OrdinalIgnoreCase))
                    throw new ArgumentException("Source must be an existing DWG.");
                string output = null;
                List<Replacement> values = new List<Replacement>();
                if (!inspect)
                {
                    output = Path.GetFullPath(args[2]);
                    if (String.Equals(source, output, StringComparison.OrdinalIgnoreCase) ||
                        !String.Equals(Path.GetExtension(output), ".dxf", StringComparison.OrdinalIgnoreCase) ||
                        File.Exists(output) || !Directory.Exists(Path.GetDirectoryName(output)))
                        throw new ArgumentException("Output must be a new DXF beside an existing directory, not the source file.");
                    if (replace)
                        values.Add(new Replacement { name = args[3], value = args[4] });
                    else
                    {
                        string file = Path.GetFullPath(args[3]);
                        if (!File.Exists(file) ||
                            !String.Equals(Path.GetExtension(file), ".json", StringComparison.OrdinalIgnoreCase))
                            throw new ArgumentException("Variable mapping must be an existing JSON file.");
                        Json.MaxJsonLength = 16 * 1024 * 1024;
                        values = Json.Deserialize<List<Replacement>>(File.ReadAllText(file));
                    }
                    if (values == null || values.Count == 0 || values.Count > 2000)
                        throw new ArgumentException("Variable mapping must contain 1..2000 rows.");
                    foreach (Replacement value in values)
                    {
                        if (value == null || String.IsNullOrWhiteSpace(value.name) ||
                            value.value == null || value.name.Length > 256 || value.value.Length > 4096 ||
                            value.name.IndexOfAny(new [] { '\r', '\n', '\0' }) >= 0 ||
                            value.value.IndexOfAny(new [] { '\r', '\n', '\0' }) >= 0)
                            throw new ArgumentException("Mapping rows require a safe name and a single-line value.");
                        // Important: RoBAS DataTable may contain duplicate names.
                        // Do not deduplicate or reject them: the nested original
                        // TEXT loop compares each row in its original order.
                        // Empty replacement is valid (DBNull.ToString() == "").
                    }
                }

                CADImage image = CADImage.CreateImageByExtension(source);
                image.LoadFromFile(source);
                if (image.CurrentLayout == null)
                    throw new InvalidDataException("CADImport returned no CurrentLayout.");

                int count = image.CurrentLayout.Count;
                int texts = 0;
                int changed = 0;
                List<string> originalTexts = new List<string>();
                Dictionary<string, int> matched = new Dictionary<string, int>(StringComparer.Ordinal);
                for (int i = 0; i < count; i++)
                {
                    var entity = image.CurrentLayout.Entities[i];
                    if (entity.EntType != EntityType.Text)
                        continue; // Deliberately keep exact RoBAS scope (no MTEXT/attributes).
                    texts++;
                    CADText t = (CADText)entity;
                    originalTexts.Add(t.Text ?? "");
                    // Original RoBAS rechecks the text after each assignment.
                    foreach (Replacement pair in values)
                    {
                        if (String.Equals(t.Text, pair.name, StringComparison.Ordinal))
                        {
                            t.Text = pair.value;
                            changed++;
                            matched[pair.name] = matched.ContainsKey(pair.name) ? matched[pair.name] + 1 : 1;
                        }
                    }
                }
                if (!inspect)
                {
                    if (changed == 0)
                        throw new InvalidDataException("No source DWG CADText matched the supplied variables.");
                    CADImport.Export.DirectCADtoDXF.CADtoDXF export =
                        new CADImport.Export.DirectCADtoDXF.CADtoDXF(image);
                    export.SaveToFile(output);
                    if (!File.Exists(output) || new FileInfo(output).Length == 0)
                        throw new InvalidDataException("CADImport failed to produce a nonempty DXF.");
                }
                Dictionary<string, object> report = new Dictionary<string, object>();
                report["mode"] = inspect ? "inspect" : (replace ? "replace" : "batch");
                report["source"] = source;
                report["output"] = output;
                report["layout_entity_count"] = count;
                report["text_entity_count"] = texts;
                report["non_text_entity_count"] = count - texts;
                report["exact_match_count"] = changed;
                report["target_key"] = replace ? args[3] : null;
                report["matched_keys"] = matched;
                report["texts"] = originalTexts;
                report["status"] = "CADIMPORT_COMPLETED_NOT_YET_DXF_AUDITED";
                Console.WriteLine(Json.Serialize(report));
                return 0;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine("CADIMPORT_SPIKE_FAILED: " + error);
                return 2;
            }
        }
    }
}
