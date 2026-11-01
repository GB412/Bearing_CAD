// Faithful RoBAS DWG -> CADText exact match -> DXF bridge.
// Based on RoBAS/Frm/FrmMain.cs LoadCadAndChangeText and ChangeCADTexts.
// Windows .NET Framework 4.5.2 and licensed CADImport are required.
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
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
                bool doctor = args.Length == 1 && args[0] == "doctor";
                bool inspect = args.Length == 2 && args[0] == "inspect";
                bool replace = args.Length == 5 && args[0] == "replace";
                bool batch = args.Length == 4 && args[0] == "batch";
                if (doctor)
                {
                    PrintDoctor();
                    return 0;
                }
                if (!inspect && !replace && !batch)
                    throw new ArgumentException("Usage: doctor | inspect <source.dwg> | replace <source.dwg> <out.dxf> <key> <value> | batch <source.dwg> <out.dxf> <variables.json>");

                string source = Path.GetFullPath(args[1]);
                if (!File.Exists(source) || !String.Equals(Path.GetExtension(source), ".dwg", StringComparison.OrdinalIgnoreCase))
                    throw new ArgumentException("Source must be an existing DWG.");
                string output = null;
                List<Replacement> values = new List<Replacement>();
                if (!inspect)
                {
                    output = Path.GetFullPath(args[2]);
                    if (String.Equals(source, output, StringComparison.OrdinalIgnoreCase) ||
                        !String.Equals(Path.GetExtension(output), ".dxf", StringComparison.OrdinalIgnoreCase) ||
                        File.Exists(output) || !Directory.Exists(Path.GetDirectoryName(output)))
                        throw new ArgumentException("Output must be a new DXF in an existing directory, not the source file.");
                    if (replace)
                        values.Add(new Replacement { name = args[3], value = args[4] });
                    else
                    {
                        string file = Path.GetFullPath(args[3]);
                        if (!File.Exists(file) || !String.Equals(Path.GetExtension(file), ".json", StringComparison.OrdinalIgnoreCase))
                            throw new ArgumentException("Variable mapping must be an existing JSON file.");
                        Json.MaxJsonLength = 16 * 1024 * 1024;
                        values = Json.Deserialize<List<Replacement>>(File.ReadAllText(file));
                    }
                    ValidateMappings(values);
                }

                EnsureCadImportLicense();
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
                        continue;
                    texts++;
                    CADText text = (CADText)entity;
                    originalTexts.Add(text.Text ?? "");
                    // Preserve the original nested row order, including duplicate names.
                    foreach (Replacement pair in values)
                    {
                        if (String.Equals(text.Text, pair.name, StringComparison.Ordinal))
                        {
                            text.Text = pair.value;
                            changed++;
                            matched[pair.name] = matched.ContainsKey(pair.name) ? matched[pair.name] + 1 : 1;
                        }
                    }
                }
                if (!inspect)
                {
                    if (changed == 0)
                        throw new InvalidDataException("No source DWG CADText matched the supplied variables.");
                    CADImport.Export.DirectCADtoDXF.CADtoDXF export = new CADImport.Export.DirectCADtoDXF.CADtoDXF(image);
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
                Console.Error.WriteLine("CADIMPORT_BRIDGE_FAILED: " + error.Message);
                return 2;
            }
        }

        private static void ValidateMappings(List<Replacement> values)
        {
            if (values == null || values.Count == 0 || values.Count > 2000)
                throw new ArgumentException("Variable mapping must contain 1..2000 rows.");
            foreach (Replacement value in values)
            {
                if (value == null || String.IsNullOrWhiteSpace(value.name) || value.value == null ||
                    value.name.Length > 256 || value.value.Length > 4096 ||
                    value.name.IndexOfAny(new[] { '\r', '\n', '\0' }) >= 0 ||
                    value.value.IndexOfAny(new[] { '\r', '\n', '\0' }) >= 0)
                    throw new ArgumentException("Mapping rows require safe single-line name and value strings.");
            }
        }

        // RoBAS registers the licensed CADImport runtime before creating a CADImage.
        // Keep this call aligned with NetLib/CADLib/C2dMethod.cs from the source project.
        private static void EnsureCadImportLicense()
        {
            bool registered = Protection.Register(
                "irDevelopers.com",
                "irDevelopers.com@gmail.com",
                "A1F08E31A4836D365457F7A3A965E8D05C37F85D018917A8D5A64447D6FB325C00CEA140F39D35E831031873A01BDA5AFB5B9E9C13D638F10B02B7A3792F364",
                false);
            if (!registered)
                throw new InvalidOperationException("CADImport license registration failed.");
        }

        private static void PrintDoctor()
        {
            Assembly assembly = typeof(CADImage).Assembly;
            Dictionary<string, object> report = new Dictionary<string, object>();
            report["bridge_version"] = typeof(Program).Assembly.GetName().Version.ToString();
            report["cadimport_full_name"] = assembly.FullName;
            report["cadimport_version"] = assembly.GetName().Version.ToString();
            report["clr_version"] = Environment.Version.ToString();
            report["os_version"] = Environment.OSVersion.VersionString;
            report["process_architecture"] = Environment.Is64BitProcess ? "x64" : "x86";
            report["os_architecture"] = Environment.Is64BitOperatingSystem ? "x64" : "x86";
            report["cadimport_location"] = assembly.Location;
            report["status"] = Environment.Is64BitProcess && Environment.Is64BitOperatingSystem ? "READY_FOR_DWG_PROBE" : "ARCHITECTURE_MISMATCH";
            Console.WriteLine(Json.Serialize(report));
        }
    }
}
