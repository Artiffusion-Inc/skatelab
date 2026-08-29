"""Contract tests for choreography report/PDF export."""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from app.routes.choreography import ChoreographyController
from app.schemas import ExportRequest
from litestar.exceptions import ClientException

controller = object.__new__(ChoreographyController)


def _bound(name: str):
    handler = getattr(controller, name)
    return handler.fn.__get__(controller, ChoreographyController)


def _user(user_id: str = "user_123") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def _program(user_id: str = "user_123") -> MagicMock:
    program = MagicMock()
    program.id = "program_123"
    program.user_id = user_id
    return program


@pytest.mark.asyncio
async def test_pdf_export_returns_pdf_without_svg_fallback() -> None:
    """PDF requests return real PDF bytes and do not call the SVG renderer."""
    program = _program()
    program.title = "Autumn program"
    program.discipline = "mens_singles"
    program.segment = "free_skate"
    program.season = "2025-26"
    program.layout = {"elements": [{"code": "3A", "x": 10.0, "y": 5.0}]}
    program.estimated_total = 135.5

    with (
        patch("app.routes.choreography.get_program_by_id", return_value=program),
        patch("app.routes.choreography.render_rink") as render_rink,
        patch("app.routes.choreography.export_ready", new_callable=AsyncMock) as notify,
    ):
        response = await _bound("export_program")(
            "program_123", ExportRequest(format="pdf"), _user(), AsyncMock()
        )

    assert response.media_type == "application/pdf"
    assert response.content.startswith(b"%PDF-1.4")
    assert b"Autumn program" in response.content
    render_rink.assert_not_called()
    notify.assert_awaited_once_with(ANY, user_id="user_123", export_id="program_123")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("program", "user", "status_code"),
    [(_program("user_123"), _user("user_456"), 403), (None, _user(), 404)],
)
async def test_pdf_export_keeps_program_ownership_checks(
    program: MagicMock | None, user: MagicMock, status_code: int
) -> None:
    """PDF generation must not bypass existing IDOR protection."""
    with patch("app.routes.choreography.get_program_by_id", return_value=program):
        with pytest.raises(ClientException) as exc_info:
            await _bound("export_program")(
                "program_123", ExportRequest(format="pdf"), user, AsyncMock()
            )

    assert exc_info.value.status_code == status_code
