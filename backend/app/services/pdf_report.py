"""Small dependency-free PDF export for program summaries.

The mobile export contract needs a real PDF response, while the backend image
and font stack is intentionally kept free of a heavyweight renderer. This
writer emits a conservative one-page PDF using the built-in Helvetica font.
Non-Latin text is replaced by ``?``; callers still receive the numeric/code
content that remains useful in the report.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

PAGE_WIDTH = 595
PAGE_HEIGHT = 842


def _pdf_text(value: object) -> str:
    """Escape text for a PDF literal string and keep the output Latin-1 safe."""
    text = str(value).encode("latin-1", errors="replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _lines(program: Mapping[str, Any]) -> list[str]:
    lines = [
        "SkateLab program report",
        f"Title: {program.get('title') or 'Untitled program'}",
        f"Discipline: {program.get('discipline') or '-'}",
        f"Segment: {program.get('segment') or '-'}",
        f"Season: {program.get('season') or '-'}",
    ]
    estimated_total = program.get("estimated_total")
    if estimated_total is not None:
        lines.append(f"Estimated total: {estimated_total}")

    lines.append("")
    lines.append("Elements:")
    elements = program.get("elements") or []
    if isinstance(elements, Sequence) and not isinstance(elements, (str, bytes)):
        for index, element in enumerate(elements, start=1):
            if isinstance(element, Mapping):
                code = element.get("code") or "-"
                x = element.get("x")
                y = element.get("y")
                position = f" ({x}, {y})" if x is not None and y is not None else ""
                lines.append(f"{index}. {code}{position}")
    if not elements:
        lines.append("No elements recorded")
    return lines


def generate_program_pdf(program: Mapping[str, Any]) -> bytes:
    """Return a valid one-page PDF containing a program summary."""
    content_lines = [
        "BT",
        "/F1 16 Tf",
        f"50 {PAGE_HEIGHT - 60} Td",
    ]
    for index, line in enumerate(_lines(program)):
        if index:
            content_lines.append("0 -24 Td")
        content_lines.append(f"({_pdf_text(line)}) Tj")
    content_lines.append("ET")
    stream = ("\n".join(content_lines) + "\n").encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ).encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"endstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)
