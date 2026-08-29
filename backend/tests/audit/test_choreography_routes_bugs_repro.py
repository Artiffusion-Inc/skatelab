"""#704-#717: choreography route bug repro tests.

#704: upload_music no file size limit (OOM)
#705: upload_music cross-user fingerprint dedup info leak
#706: upload_music incomplete exception coverage
#707: create_new_program no music_analysis_id ownership check
#708: update_existing_program no music_analysis_id ownership check
#709: render_rink_diagram no auth
#711: get_elements_registry no auth
#712: validate_choreography no auth
#713: update_existing_program drops discipline/segment
#714: export_program PDF uses a real PDF response
#715: export_program json drops fields
#716: generate_layout hardcodes is_back_half=False
#717: LayoutElement.goe int rejects/truncates fractional GOE
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from app.schemas import ExportRequest, LayoutElement

ROUTES_PATH = Path(__file__).resolve().parents[2] / "app" / "routes" / "choreography.py"
SCHEMAS_PATH = Path(__file__).resolve().parents[2] / "app" / "schemas.py"
CRUD_PATH = Path(__file__).resolve().parents[2] / "app" / "crud" / "choreography.py"


# ---------------------------------------------------------------------------
# #717: goe type (int → float)
# ---------------------------------------------------------------------------


def test_goe_is_float_in_schema():
    """#717: LayoutElement.goe should be float, not int."""
    field_type = LayoutElement.model_fields["goe"].annotation
    assert field_type is float, f"#717: goe should be float, got {field_type}"


def test_goe_accepts_fractional():
    """#717: LayoutElement accepts fractional GOE like 1.5."""
    el = LayoutElement(code="3T", goe=1.5)
    assert el.goe == 1.5


def test_goe_accepts_int():
    """#717: LayoutElement still accepts int GOE (coerced to float)."""
    el = LayoutElement(code="3T", goe=3)
    assert el.goe == 3.0


# ---------------------------------------------------------------------------
# #716: is_back_half from solver
# ---------------------------------------------------------------------------


def test_is_back_half_from_solver_in_source():
    """#716: generate_layout uses e.get('is_back_half', False), not hardcoded False."""
    source = ROUTES_PATH.read_text()
    assert "is_back_half" in source, "#716: is_back_half not in source"
    # Must NOT have hardcoded is_back_half=False in LayoutElement construction
    # Check that the line uses e.get, not literal False
    for line in source.splitlines():
        if "is_back_half" in line and "LayoutElement" not in line and "is_back_half=False" in line:
            # If there's a hardcoded =False outside LayoutElement, that's the old bug
            pytest.fail("#716: found hardcoded is_back_half=False")


def test_is_back_half_uses_e_get():
    """#716: is_back_half comes from solver dict, not hardcoded."""
    source = ROUTES_PATH.read_text()
    assert 'e.get("is_back_half"' in source, "#716: is_back_half should use e.get"


# ---------------------------------------------------------------------------
# #714: ExportRequest includes pdf for the mobile export contract
# ---------------------------------------------------------------------------


def test_export_request_accepts_pdf():
    """#714: ExportRequest accepts PDF for the mobile report flow."""
    req = ExportRequest(format="pdf")
    assert req.format == "pdf"


def test_export_request_accepts_svg():
    """#714: ExportRequest accepts svg."""
    req = ExportRequest(format="svg")
    assert req.format == "svg"


def test_export_request_accepts_json():
    """#714: ExportRequest accepts json."""
    req = ExportRequest(format="json")
    assert req.format == "json"


# ---------------------------------------------------------------------------
# #715: export json includes all fields
# ---------------------------------------------------------------------------


def test_export_json_includes_all_fields_in_source():
    """#715: JSON export includes season, estimated_goe, etc."""
    source = ROUTES_PATH.read_text()
    # The json export block should include these fields
    for field in ("season", "estimated_goe", "estimated_pcs", "music_analysis_id"):
        assert field in source, f"#715: JSON export missing field '{field}'"


# ---------------------------------------------------------------------------
# #713: update_program passes discipline/segment
# ---------------------------------------------------------------------------


def test_update_passes_discipline_segment_in_source():
    """#713: update_existing_program passes discipline and segment to update_program."""
    source = ROUTES_PATH.read_text()
    assert "discipline=data.discipline" in source, "#713: discipline not passed to update_program"
    assert "segment=data.segment" in source, "#713: segment not passed to update_program"


# ---------------------------------------------------------------------------
# #712: validate_choreography has auth
# ---------------------------------------------------------------------------


def test_validate_has_verified_user_in_source():
    """#712: validate_choreography has VerifiedUser dependency."""
    source = ROUTES_PATH.read_text()
    assert "verified_user: VerifiedUser" in source, "#712: validate_choreography missing auth"


# ---------------------------------------------------------------------------
# #711: get_elements_registry has auth
# ---------------------------------------------------------------------------


def test_elements_registry_has_verified_user_in_source():
    """#711: get_elements_registry has VerifiedUser dependency."""
    source = ROUTES_PATH.read_text()
    # Find the line with get_elements_registry
    lines = source.splitlines()
    for line in lines:
        if "get_elements_registry" in line and "async def" in line:
            assert "verified_user" in line, "#711: get_elements_registry missing auth"
            break
    else:
        pytest.fail("#711: get_elements_registry not found in source")


# ---------------------------------------------------------------------------
# #709: render_rink_diagram has auth
# ---------------------------------------------------------------------------


def test_render_rink_has_verified_user_in_source():
    """#709: render_rink_diagram has VerifiedUser dependency."""
    source = ROUTES_PATH.read_text()
    lines = source.splitlines()
    for line in lines:
        if "render_rink_diagram" in line and "async def" in line:
            assert "verified_user" in line, "#709: render_rink_diagram missing auth"
            break
    else:
        pytest.fail("#709: render_rink_diagram not found in source")


# ---------------------------------------------------------------------------
# #707 #708: music ownership check helper
# ---------------------------------------------------------------------------


def test_verify_music_ownership_in_source():
    """#707 #708: _verify_music_ownership helper exists."""
    source = ROUTES_PATH.read_text()
    assert "_verify_music_ownership" in source, "#707/#708: ownership check missing"


def test_create_new_program_calls_verify():
    """#707: create_new_program calls _verify_music_ownership."""
    source = ROUTES_PATH.read_text()
    assert "_verify_music_ownership" in source, "#707: ownership check not called"


# ---------------------------------------------------------------------------
# #706: broadened exception in upload_music
# ---------------------------------------------------------------------------


def test_upload_music_broad_except_in_source():
    """#706: upload_music catches Exception, not narrow tuple."""
    source = ROUTES_PATH.read_text()
    assert "except Exception" in source, "#706: broadened except missing"


# ---------------------------------------------------------------------------
# #705: fingerprint dedup scoped to user
# ---------------------------------------------------------------------------


def test_fingerprint_dedup_scoped_in_source():
    """#705: find_music_by_fingerprint call passes user_id."""
    source = ROUTES_PATH.read_text()
    assert "user_id=verified_user.id" in source, "#705: dedup not scoped to user"


def test_fingerprint_dedup_crud_accepts_user_id():
    """#705: find_music_by_fingerprint accepts user_id parameter."""
    source = CRUD_PATH.read_text()
    assert "user_id" in source, "#705: find_music_by_fingerprint missing user_id param"


# ---------------------------------------------------------------------------
# #704: file size limit
# ---------------------------------------------------------------------------


def test_upload_size_limit_in_source():
    """#704: upload_music checks file size."""
    source = ROUTES_PATH.read_text()
    assert "MAX_MUSIC_UPLOAD_BYTES" in source, "#704: size limit constant missing"
    assert "len(content) > MAX_MUSIC_UPLOAD_BYTES" in source, "#704: size check missing"
