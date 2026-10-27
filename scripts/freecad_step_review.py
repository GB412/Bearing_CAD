# 3D-MIG-09B FreeCAD GUI inspection helper.
# Run from FreeCAD's Python console:
#   exec(open(r"D:\\BearingCAD\\scripts\\freecad_step_review.py", encoding="utf-8").read())
# Select a STEP from build/migration-07a/bundles/<artifact_key>/bearing_assembly.step
# This helper does not certify mechanical correctness or automate visual approval.
import json
import pathlib

import FreeCAD as App
import Part
import Import

try:
    from PySide2 import QtWidgets
except ImportError:
    from PySide import QtGui as QtWidgets


def run_review():
    filename, _ = QtWidgets.QFileDialog.getOpenFileName(
        None, "3D-MIG-09B · 选择 Bearing_CAD STEP",
        "", "STEP files (*.step *.stp)"
    )
    if not filename:
        print("3D-MIG-09B: no STEP selected")
        return
    step = pathlib.Path(filename)
    folder = step.parent
    manifest_file = folder / "artifact_manifest.json"
    design_file = folder / "design_snapshot.json"
    if not manifest_file.is_file() or not design_file.is_file():
        raise ValueError("Select STEP within a verified Bearing_CAD artifact directory")

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    design = json.loads(design_file.read_text(encoding="utf-8"))
    expected_instances = len(manifest["instances"])
    d = float(design["parameters"]["bore_d_mm"])
    D = float(design["parameters"]["outside_d_mm"])
    B = float(design["parameters"]["width_mm"])

    doc = App.newDocument("BearingCAD_Independent_STEP_Review")
    Import.insert(str(step), doc.Name)
    doc.recompute()
    imported_objects = []
    solids = []
    # STEP importers can represent an assembly with parent containers.
    # Count the *leaf* shape features only, not their aggregated parents.
    for obj in doc.Objects:
        if not hasattr(obj, "Shape"):
            continue
        if obj.TypeId in ("App::Part", "App::DocumentObjectGroup",
                          "App::DocumentObjectGroupPython"):
            continue
        shape = obj.Shape
        if shape.isNull():
            continue
        count = len(shape.Solids)
        if count:
            imported_objects.append({
                "object_name": obj.Name, "object_label": obj.Label,
                "solid_count": count
            })
            solids.extend(shape.Solids)

    if not solids:
        raise RuntimeError("FreeCAD imported no STEP solids")
    combined = Part.makeCompound(solids)
    box = combined.BoundBox
    extent = [box.XLength, box.YLength, box.ZLength]
    valid = all(s.isValid() for s in solids)
    tolerance = 0.02  # import sanity threshold, not mechanical tolerance
    errors = []
    if len(solids) != expected_instances:
        errors.append(f"STEP solid count {len(solids)} != manifest {expected_instances}")
    if not valid:
        errors.append("FreeCAD imported one or more invalid solids")
    if abs(max(extent[0], extent[1]) - D) > tolerance:
        errors.append("Outer envelope D differs from input")
    if abs(extent[2] - B) > tolerance:
        errors.append("Axial envelope B differs from input")

    report = {
        "review_method": "FREECAD_GUI_STEP_IMPORT",
        "status": "AUTOMATED_IMPORT_CHECK_ONLY_MANUAL_REVIEW_PENDING",
        "step_file": step.name,
        "artifact_key": manifest["artifact_key"],
        "bearing_type": design["bearing_type"],
        "freecad_version": App.Version(),
        "expected_instances": expected_instances,
        "freecad_imported_solid_count": len(solids),
        "freecad_shape_valid": valid,
        "source_expected_bore_d_mm": d,
        "source_expected_outside_d_mm": D,
        "source_expected_width_mm": B,
        "freecad_bbox_extents_mm": extent,
        "freecad_imported_total_volume_mm3": sum(s.Volume for s in solids),
        "imported_leaf_objects": imported_objects,
        "errors": errors,
        "manual_visual_review": {
            "ring_groove_and_shoulder": "PENDING",
            "rolling_elements_positions": "PENDING",
            "cage_and_separate_parts": "PENDING",
            "screenshots_recorded": False
        },
        "limitations": [
            "FreeCAD STEP import is an independent application check, not a separate kernel or RoBAS equivalence proof",
            "A successful script does not substitute manual visual review",
            "No manufacturing, tolerances, load or fatigue approval is implied"
        ]
    }
    out = folder / "freecad_import_review.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    print("FreeCAD STEP import inspection: " + ("CHECK_REQUIRED" if errors else "METRICS_COLLECTED"))
    print("Report:", out)
    for item in errors:
        print("  !", item)


run_review()
