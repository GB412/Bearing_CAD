"""Real OCCT regression for RoBAS-style stamped shell; verifies board thickness."""
import json
from pathlib import Path
import pytest
from bearing_cad.contracts import parse_request
from bearing_cad.deep_groove import build_deep_groove
from bearing_cad.geometry_checks import interference_volume

CASES = Path(__file__).parent / "fixtures" / "robas_3d_cases.json"

def test_stamped_shell_from_existing_reference():
    source = json.loads(CASES.read_text(encoding="utf-8"))
    request = next(c["request"] for c in source["cases"] if c["case_id"] == "dgb_stamped")
    model = build_deep_groove(parse_request(request))
    components = {part.component_id: part.shape for part in model.components}
    assert len(model.instances) == 26
    upper, lower = components["cage_upper"], components["cage_lower"]
    assert upper.val().isValid()
    assert lower.isValid()
    assert upper.val().Volume() == pytest.approx(lower.Volume(), rel=1e-7)
    assert upper.val().BoundingBox().zmin == pytest.approx(0, abs=1e-4)
    assert lower.BoundingBox().zmax == pytest.approx(0, abs=1e-4)
    assert interference_volume(upper,lower) < 1e-6

def test_board_thickness_controls_solid_volume():
    source = json.loads(CASES.read_text(encoding="utf-8"))
    data = next(c["request"] for c in source["cases"] if c["case_id"] == "dgb_stamped")
    a = build_deep_groove(parse_request(data))
    import copy
    larger = copy.deepcopy(data)
    larger["cage"]["board_thickness_mm"] = 0.85
    b = build_deep_groove(parse_request(larger))
    def vol(model):
        return next(part.shape.val().Volume() for part in model.components if part.component_id == "cage_upper")
    assert vol(b) > vol(a)
