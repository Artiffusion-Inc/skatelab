"""Tests for shared Pydantic schemas."""

from __future__ import annotations

import pytest
from app.schemas import ErrorResponse, PaginatedResponse, ValidationErrorDetail
from pydantic import ValidationError


class TestErrorResponse:
    def test_minimal_error(self):
        e = ErrorResponse(error="NotFound", message="User not found")
        assert e.error == "NotFound"
        assert e.message == "User not found"
        assert e.details is None
        assert e.path == ""

    def test_with_details_dict(self):
        e = ErrorResponse(
            error="ValidationError",
            message="Bad input",
            details={"field": "email"},
        )
        assert e.details == {"field": "email"}

    def test_with_details_list(self):
        e = ErrorResponse(
            error="ValidationError",
            message="Bad input",
            details=[
                ValidationErrorDetail(field="email", message="Invalid", value="bad"),
            ],
        )
        assert len(e.details) == 1  # type: ignore[arg-type]
        assert e.details[0].field == "email"  # type: ignore[index]

    def test_model_dump(self):
        e = ErrorResponse(error="Test", message="Msg", path="/v1/users")
        d = e.model_dump()
        assert d["error"] == "Test"
        assert d["message"] == "Msg"
        assert d["path"] == "/v1/users"
        assert d["details"] is None


class TestPaginatedResponse:
    def test_defaults(self):
        p = PaginatedResponse(total=50)
        assert p.total == 50
        assert p.page == 1
        assert p.page_size == 20
        assert p.pages == 1
        assert not p.has_next
        assert not p.has_prev

    def test_has_next(self):
        p = PaginatedResponse(total=50, page=1, page_size=20, pages=3)
        assert p.has_next
        assert not p.has_prev

    def test_has_prev(self):
        p = PaginatedResponse(total=50, page=2, page_size=20, pages=3)
        assert p.has_next
        assert p.has_prev

    def test_last_page(self):
        p = PaginatedResponse(total=50, page=3, page_size=20, pages=3)
        assert not p.has_next
        assert p.has_prev
