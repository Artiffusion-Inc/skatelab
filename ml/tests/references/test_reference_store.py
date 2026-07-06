"""Tests for reference_store module."""

import logging
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.references.reference_store import ReferenceStore
from src.types import ElementPhase, ReferenceData, VideoMeta


@pytest.fixture
def sample_reference_data():
    """Create a sample ReferenceData for testing."""
    poses = np.linspace(0, 1, 340).reshape(10, 17, 2).astype(np.float32)
    phases = ElementPhase(
        name="waltz_jump",
        start=0,
        takeoff=3,
        peak=5,
        landing=7,
        end=9,
    )
    meta = VideoMeta(
        path=Path("test.mp4"),
        width=1920,
        height=1080,
        fps=30.0,
        num_frames=300,
    )
    return ReferenceData(
        element_type="waltz_jump",
        name="expert_waltz",
        poses=poses,
        phases=phases,
        fps=30.0,
        meta=meta,
        source="test.mp4",
    )


@pytest.fixture
def mock_builder():
    """Create a mock ReferenceBuilder."""
    builder = MagicMock()
    builder.save_reference.return_value = Path("/fake/path/ref.npz")
    return builder


class TestReferenceStoreInit:
    def test_init(self, tmp_path: Path):
        store_dir = tmp_path / "store"
        store = ReferenceStore(store_dir)
        assert store._store_dir == store_dir
        assert store._builder is None

    def test_set_builder(self, tmp_path: Path, mock_builder):
        store = ReferenceStore(tmp_path)
        store.set_builder(mock_builder)
        assert store._builder is mock_builder


class TestReferenceStoreAdd:
    def test_add_raises_without_builder(self, tmp_path: Path, sample_reference_data):
        store = ReferenceStore(tmp_path)
        with pytest.raises(RuntimeError, match="ReferenceBuilder not set"):
            store.add(sample_reference_data)

    def test_add_saves_reference(self, tmp_path: Path, mock_builder, sample_reference_data):
        store = ReferenceStore(tmp_path)
        store.set_builder(mock_builder)
        expected_path = tmp_path / "waltz_jump" / "expert_waltz.npz"
        mock_builder.save_reference.return_value = expected_path

        result = store.add(sample_reference_data)

        mock_builder.save_reference.assert_called_once()
        args, _kwargs = mock_builder.save_reference.call_args
        assert args[0] == sample_reference_data
        assert args[1] == tmp_path / "waltz_jump"
        assert result == expected_path


class TestReferenceStoreGet:
    def test_get_raises_without_builder(self, tmp_path: Path):
        store = ReferenceStore(tmp_path)
        with pytest.raises(RuntimeError, match="ReferenceBuilder not set"):
            store.get("waltz_jump")

    def test_get_returns_empty_for_missing_element(self, tmp_path: Path, mock_builder):
        store = ReferenceStore(tmp_path)
        store.set_builder(mock_builder)
        result = store.get("nonexistent")
        assert result == []
        mock_builder.load_reference.assert_not_called()

    def test_get_loads_references(self, tmp_path: Path, mock_builder, sample_reference_data):
        store = ReferenceStore(tmp_path)
        store.set_builder(mock_builder)

        element_dir = tmp_path / "waltz_jump"
        element_dir.mkdir()
        (element_dir / "ref1.npz").touch()
        (element_dir / "ref2.npz").touch()

        mock_builder.load_reference.side_effect = [sample_reference_data, sample_reference_data]

        result = store.get("waltz_jump")

        assert len(result) == 2
        assert mock_builder.load_reference.call_count == 2

    def test_get_skips_invalid_files(
        self, tmp_path: Path, mock_builder, sample_reference_data, caplog
    ):
        store = ReferenceStore(tmp_path)
        store.set_builder(mock_builder)

        element_dir = tmp_path / "waltz_jump"
        element_dir.mkdir()
        (element_dir / "valid.npz").touch()
        (element_dir / "invalid.npz").touch()

        mock_builder.load_reference.side_effect = [sample_reference_data, Exception("corrupted")]

        with caplog.at_level(logging.WARNING):
            result = store.get("waltz_jump")

        assert len(result) == 1
        assert "Failed to load" in caplog.text

    def test_get_all_corrupt_raises_not_silent_empty(self, tmp_path: Path, mock_builder, caplog):
        """#805: all-corrupt element dir must raise, NOT return [].

        Returning [] is indistinguishable from "element type not found" — a
        truncated download / partial write / schema drift hid behind a warning
        log. Surface the corruption so the caller (DTW via get_best_match) sees
        the real cause instead of a silent "no references" skip.
        """
        store = ReferenceStore(tmp_path)
        store.set_builder(mock_builder)

        element_dir = tmp_path / "waltz_jump"
        element_dir.mkdir()
        (element_dir / "a.npz").touch()
        (element_dir / "b.npz").touch()
        (element_dir / "c.npz").touch()

        # Every file corrupt
        mock_builder.load_reference.side_effect = [
            ValueError("corrupt a"),
            ValueError("corrupt b"),
            ValueError("corrupt c"),
        ]

        with caplog.at_level(logging.WARNING):
            with pytest.raises(RuntimeError, match=r"All 3 reference\(s\) corrupt"):
                store.get("waltz_jump")
        assert "Failed to load" in caplog.text


class TestReferenceStoreListElements:
    def test_list_elements_empty_store(self, tmp_path: Path):
        store = ReferenceStore(tmp_path)
        assert store.list_elements() == []

    def test_list_elements_nonexistent_store(self, tmp_path: Path):
        store = ReferenceStore(tmp_path / "does_not_exist")
        assert store.list_elements() == []

    def test_list_elements(self, tmp_path: Path):
        store = ReferenceStore(tmp_path)
        (tmp_path / "waltz_jump").mkdir()
        (tmp_path / "three_turn").mkdir()
        (tmp_path / "not_a_dir.npz").touch()

        result = store.list_elements()
        assert result == ["three_turn", "waltz_jump"]


class TestReferenceStoreGetBestMatch:
    def test_get_best_match_returns_first(
        self, tmp_path: Path, mock_builder, sample_reference_data
    ):
        store = ReferenceStore(tmp_path)
        store.set_builder(mock_builder)

        element_dir = tmp_path / "waltz_jump"
        element_dir.mkdir()
        (element_dir / "ref1.npz").touch()

        mock_builder.load_reference.return_value = sample_reference_data

        result = store.get_best_match("waltz_jump")
        assert result is sample_reference_data
        mock_builder.load_reference.assert_called_once()

    def test_get_best_match_returns_none(self, tmp_path: Path, mock_builder):
        store = ReferenceStore(tmp_path)
        store.set_builder(mock_builder)
        result = store.get_best_match("nonexistent")
        assert result is None


class TestReferenceStoreEnsureStoreDir:
    def test_ensure_store_dir(self, tmp_path: Path):
        store_dir = tmp_path / "nested" / "store"
        store = ReferenceStore(store_dir)
        assert not store_dir.exists()
        store.ensure_store_dir()
        assert store_dir.exists()
        assert store_dir.is_dir()

    def test_ensure_store_dir_idempotent(self, tmp_path: Path):
        store = ReferenceStore(tmp_path)
        store.ensure_store_dir()
        assert tmp_path.exists()
        store.ensure_store_dir()
        assert tmp_path.exists()
