"""Reference data storage and retrieval.

This module provides a file-based storage system for reference skating elements,
organized by element type (three_turn, waltz_jump, etc.).
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# #803: separators that let element_type escape store_dir via path traversal.
_TRAVERSAL_MARKERS = ("/", "\\")

if TYPE_CHECKING:
    from .reference_builder import ReferenceBuilder  # type: ignore[import-untyped]
    from .types import ReferenceData  # type: ignore[import-untyped]


class ReferenceStore:
    """Storage for reference skating elements.

    References are stored as .npz files organized by element type:
        store_dir/
            three_turn/
                expert_01.npz
                expert_02.npz
            waltz_jump/
                expert_01.npz
                ...
    """

    def __init__(self, store_dir: Path) -> None:
        """Initialize reference store.

        Args:
            store_dir: Directory containing reference .npz files.
        """
        self._store_dir = store_dir
        self._builder: ReferenceBuilder | None = None

    def _element_dir(self, element_type: str) -> Path:
        """#803: store_dir / element_type with path-traversal rejection.

        element_type was passed verbatim from caller/upload metadata, so a
        value like ``../../etc/passwd`` escaped store_dir — save_reference
        mkdir(parents=True) created dirs OUTSIDE the store, and get globbed
        the escaped dir for arbitrary .npz reads. Reject any separator
        (string check is cheap and catches the obvious cases), then resolve
        and is_relative_to as defence-in-depth (catches symlink / ".." escape
        the string check misses). Returns the un-resolved joined path so the
        existing contract (paths relative to store_dir) holds.
        """
        if any(m in element_type for m in _TRAVERSAL_MARKERS) or element_type in (".", ".."):
            raise ValueError(f"invalid element_type: {element_type!r}")
        store_root = self._store_dir.resolve()
        resolved = (self._store_dir / element_type).resolve()
        if not resolved.is_relative_to(store_root):
            raise ValueError(f"element_type escapes store_dir: {element_type!r}")
        return self._store_dir / element_type

    def set_builder(self, builder: "ReferenceBuilder") -> None:  # type: ignore[valid-type]
        """Set reference builder for loading .npz files.

        Args:
            builder: ReferenceBuilder instance.
        """
        self._builder = builder

    def add(self, ref: "ReferenceData") -> Path:  # type: ignore[valid-type]
        """Add reference to store.

        Args:
            ref: ReferenceData to add.

        Returns:
            Path to saved .npz file.

        Raises:
            RuntimeError: If ReferenceBuilder not set.
        """
        if self._builder is None:
            raise RuntimeError("ReferenceBuilder not set. Use set_builder() first.")

        element_dir = self._element_dir(ref.element_type)
        return self._builder.save_reference(ref, element_dir)

    def get(self, element_type: str) -> list["ReferenceData"]:  # type: ignore[valid-type]
        """Get all references for an element type.

        Args:
            element_type: Element identifier (e.g., 'three_turn').

        Returns:
            List of ReferenceData. Empty list if element type not found.

        Raises:
            RuntimeError: If ReferenceBuilder not set.
        """
        if self._builder is None:
            raise RuntimeError("ReferenceBuilder not set. Use set_builder() first.")

        element_dir = self._element_dir(element_type)

        if not element_dir.exists():
            return []

        references: list[ReferenceData] = []  # type: ignore[valid-type]
        skipped: list[Path] = []

        # #804: sorted() so glob order is lexicographic, not filesystem readdir
        # order (inode order). get_best_match returns references[0] — the FIRST
        # glob result — so an unsorted glob makes the "best" reference (and the
        # DTW alignment / GOE proxy score downstream) filesystem-dependent and
        # non-reproducible across runs. Deterministic best-match is a
        # prerequisite for reproducible scores.
        for npz_file in sorted(element_dir.glob("*.npz")):
            try:
                ref = self._builder.load_reference(npz_file)
                references.append(ref)
            except Exception as e:  # noqa: BLE001
                # Skip invalid files, but track them so an all-corrupt element
                # dir does not look like "element type not found" (#805).
                logger.warning("Failed to load %s: %s", npz_file, e)
                skipped.append(npz_file)

        # #805: every .npz in the dir failed to load — surface the corruption
        # to the caller instead of returning [] (indistinguishable from a
        # missing element type). A truncated download / partial write / schema
        # drift was hiding behind a warning log nobody reads; the caller (DTW
        # alignment via get_best_match) saw "no references" and skipped
        # silently. Partial corruption (some valid, some bad) still returns
        # the valid ones — only the all-corrupt case raises.
        if not references and skipped:
            raise RuntimeError(
                f"All {len(skipped)} reference(s) corrupt in {element_dir} "
                f"(loaded 0, skipped {len(skipped)})"
            )

        return references

    def list_elements(self) -> list[str]:
        """List all element types in store.

        Returns:
            List of element type identifiers.
        """
        if not self._store_dir.exists():
            return []

        element_dirs = [d.name for d in self._store_dir.iterdir() if d.is_dir()]
        return sorted(element_dirs)

    def get_best_match(self, element_type: str) -> "ReferenceData | None":  # type: ignore[valid-type]
        """Get best reference match for an element type.

        Args:
            element_type: Element identifier.

        Returns:
            First available ReferenceData, or None if not found.

        Note:
            For MVP, returns the first reference. Future versions could
            implement more sophisticated matching (e.g., by athlete height).
        """
        references = self.get(element_type)

        if not references:
            return None

        # Return first reference (MVP: no sophisticated matching)
        return references[0]

    def ensure_store_dir(self) -> None:
        """Create store directory if it doesn't exist."""
        self._store_dir.mkdir(parents=True, exist_ok=True)
