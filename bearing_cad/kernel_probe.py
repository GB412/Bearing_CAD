"""Real OCCT STEP smoke check. This is NOT a bearing builder."""
from pathlib import Path
import tempfile


def run_probe() -> dict[str, object]:
    import cadquery as cq  # Imported only at the CAD-kernel boundary.
    from OCP.BRepCheck import BRepCheck_Analyzer

    solid = cq.Workplane("XY").box(4.0, 3.0, 2.0)
    shape = solid.val()
    if not shape.isValid() or not BRepCheck_Analyzer(shape.wrapped).IsValid():
        raise RuntimeError("Probe source B-Rep invalid")
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "probe.step"
        cq.exporters.export(solid, str(path), exportType="STEP")
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("Empty STEP export")
        imported = cq.importers.importStep(str(path)).solids().vals()
        if len(imported) != 1 or not imported[0].isValid():
            raise RuntimeError("STEP import failed or topology invalid")
        volume = imported[0].Volume()
        bbox = imported[0].BoundingBox()
        if abs(volume - 24.0) > 1e-5 or any(abs(x-y)>1e-5 for x,y in
              zip((bbox.xlen,bbox.ylen,bbox.zlen),(4.,3.,2.))):
            raise RuntimeError("STEP roundtrip changed dimensions")
    return {"cadquery_version": cq.__version__, "volume_mm3": volume,
            "dimensions_mm": (bbox.xlen, bbox.ylen, bbox.zlen), "step_roundtrip": True}
