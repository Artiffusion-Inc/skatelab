"""Tests for ISU data loader."""

import json
from pathlib import Path

import pytest
from app.services.choreography.isu_loader import ISULoader, SOVEntry

DATA_DIR = Path(__file__).parent.parent.parent.parent.parent / "data" / "isu"


class TestISULoader:
    def test_load_sov(self):
        loader = ISULoader(data_dir=DATA_DIR, season="2025-26")
        sov = loader.load_sov()
        assert "3T" in sov
        assert sov["3T"].base_value == pytest.approx(4.20)
        assert sov["3T"].name == "Triple Toe Loop"
        assert sov["3T"].rotations == 3.0
        assert sov["3T"].has_toe_pick is True

    def test_sov_modifiers(self):
        loader = ISULoader(data_dir=DATA_DIR, season="2025-26")
        sov = loader.load_sov()
        # < = 80% BV
        assert sov["3T"].modifiers["<"] == pytest.approx(3.36)
        # << = downgraded BV (2T)
        assert sov["3T"].modifiers["<<"] == pytest.approx(1.30)
        # q = no BV reduction
        assert sov["3T"].modifiers["q"] == pytest.approx(4.20)
        # e and ! not applicable for toe loop
        assert sov["3T"].modifiers["e"] is None

    def test_sov_edge_modifiers(self):
        loader = ISULoader(data_dir=DATA_DIR, season="2025-26")
        sov = loader.load_sov()
        # Lutz has e and ! modifiers
        assert sov["3Lz"].modifiers["e"] == pytest.approx(5.90)
        assert sov["3Lz"].modifiers["!"] == pytest.approx(5.90)

    def test_load_goe_rules(self):
        loader = ISULoader(data_dir=DATA_DIR, season="2025-26")
        rules = loader.load_goe_rules()
        assert len(rules.goe_scale) == 11
        assert rules.goe_scale[0].grade == -5
        assert rules.goe_scale[0].percentage == -50
        assert len(rules.positive_bullets) == 6
        assert rules.rules["fall_forces_goe_minus5"] is True

    def test_load_deductions(self):
        loader = ISULoader(data_dir=DATA_DIR, season="2025-26")
        deductions = loader.load_deductions()
        assert len(deductions) >= 10
        fall = next(d for d in deductions if d.id == "fall")
        assert fall.penalty == pytest.approx(-1.0)
        assert fall.detectable is True

    def test_load_pcs_factors(self):
        loader = ISULoader(data_dir=DATA_DIR, season="2025-26")
        pcs = loader.load_pcs_factors()
        assert len(pcs.components) == 5
        assert pcs.factors["men_fs"] == pytest.approx(1.60)

    def test_season_not_found(self):
        loader = ISULoader(data_dir=DATA_DIR, season="2099-00")
        with pytest.raises(FileNotFoundError):
            loader.load_sov()

    def test_sov_all_jumps_present(self):
        loader = ISULoader(data_dir=DATA_DIR, season="2025-26")
        sov = loader.load_sov()
        expected_jumps = {
            "1T",
            "1S",
            "1Lo",
            "1F",
            "1Lz",
            "1A",
            "2T",
            "2S",
            "2Lo",
            "2F",
            "2Lz",
            "2A",
            "3T",
            "3S",
            "3Lo",
            "3F",
            "3Lz",
            "3A",
            "4T",
            "4S",
            "4Lo",
            "4F",
            "4Lz",
            "4A",
            "1Eu",
        }
        assert expected_jumps <= set(sov.keys())
