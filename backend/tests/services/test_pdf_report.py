from __future__ import annotations

from app.services.pdf_report import generate_program_pdf


def test_generate_program_pdf_returns_valid_pdf_with_program_summary() -> None:
    pdf = generate_program_pdf(
        {
            "title": "Autumn program",
            "discipline": "mens_singles",
            "segment": "free_skate",
            "season": "2025-26",
            "elements": [
                {"code": "3A", "x": 10.0, "y": 5.0},
                {"code": "3Lz+2T", "x": 30.0, "y": 12.0},
            ],
            "estimated_total": 135.5,
        }
    )

    assert pdf.startswith(b"%PDF-1.4\n")
    assert b"Autumn program" in pdf
    assert b"mens_singles" in pdf
    assert b"3A" in pdf
    assert b"3Lz+2T" in pdf
    assert pdf.rstrip().endswith(b"%%EOF")
