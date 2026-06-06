"""Tests for ISU PDF parser."""

import pytest

from scripts.parse_isu_pdf import parse_goe_pdf, parse_sov_pdf


class TestSOVParser:
    def test_parse_sov_returns_dict(self):
        """Parser should return dict of element entries."""
        result = parse_sov_pdf(sample_sov_text="1T   0.40  0.40  0.32  0.40  -  -")
        assert "1T" in result
        assert result["1T"]["base_value"] == pytest.approx(0.40)
        assert result["1T"]["modifiers"]["<"] == pytest.approx(0.32)

    def test_parse_sov_with_downgrade(self):
        result = parse_sov_pdf(sample_sov_text="3T   4.20  4.20  3.36  1.30  -  -")
        assert result["3T"]["modifiers"]["<<"] == pytest.approx(1.30)

    def test_parse_sov_edge_modifiers(self):
        result = parse_sov_pdf(sample_sov_text="3Lz   5.90  5.90  4.72  2.10  5.90  5.90")
        assert result["3Lz"]["modifiers"]["e"] == pytest.approx(5.90)
        assert result["3Lz"]["modifiers"]["!"] == pytest.approx(5.90)


class TestGOEParser:
    def test_parse_goe_bullets(self):
        text = "1  Very good height and very good length  +  +  +  +  +"
        bullets = parse_goe_pdf(sample_text=text)
        assert len(bullets) >= 1
        assert bullets[0]["number"] == 1
