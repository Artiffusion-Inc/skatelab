"""ISU rules engine — validates program layouts against ISU regulations.

Singles only (Men + Women), 2025/26 season.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.choreography.elements_db import (
    ElementType,
    get_element,
)


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def _is_jump(code: str) -> bool:
    el = get_element(code)
    return el is not None and el.type == ElementType.JUMP


def _is_spin(code: str) -> bool:
    el = get_element(code)
    return el is not None and el.type == ElementType.SPIN


def _is_step_sequence(code: str) -> bool:
    el = get_element(code)
    return el is not None and el.type == ElementType.STEP_SEQUENCE


def _is_choreo_sequence(code: str) -> bool:
    el = get_element(code)
    return el is not None and el.type == ElementType.CHOREO_SEQUENCE


def _is_axel(code: str) -> bool:
    return "A" in code and _is_jump(code)


def _get_jump_passes(elements: list[dict]) -> list[list[str]]:
    """Extract jump passes from flat element list.

    A jump pass is a sequence of consecutive jump codes.
    Non-jump elements break the sequence.
    Elements without jump_pass_index are combo parts, not separate passes.
    """
    passes: list[list[str]] = []
    current_pass: list[str] = []

    for el in elements:
        code = el["code"]
        if not _is_jump(code):
            if current_pass:
                passes.append(current_pass)
                current_pass = []
            continue
        # If it has jump_pass_index, it starts a new pass
        if "jump_pass_index" in el:
            if current_pass:
                passes.append(current_pass)
                current_pass = [code]
            else:
                current_pass = [code]
        else:
            # Combo part — append to current pass
            current_pass.append(code)

    if current_pass:
        passes.append(current_pass)

    return passes


def validate_layout(layout: dict) -> ValidationResult:
    """Validate a program layout against ISU rules.

    Args:
        layout: dict with keys:
            - discipline: "mens_singles" | "womens_singles"
            - segment: "short_program" | "free_skate"
            - elements: list of dicts with "code", "goe", "timestamp", optionally "jump_pass_index"

    Returns:
        ValidationResult with errors (blocking) and warnings (non-blocking).
    """
    result = ValidationResult()
    elements = layout.get("elements", [])
    segment = layout.get("segment", "free_skate")

    # ---- Count elements by type ----
    jump_passes = _get_jump_passes(elements)
    num_jump_passes = len(jump_passes)
    spin_codes = [el["code"] for el in elements if _is_spin(el["code"])]
    num_spins = len(spin_codes)
    has_step_seq = any(_is_step_sequence(el["code"]) for el in elements)
    has_choreo_seq = any(_is_choreo_sequence(el["code"]) for el in elements)

    # ---- C_capacity: max 7 jump passes ----
    max_jump_passes = 7
    if num_jump_passes > max_jump_passes:
        result.add_error(f"Too many jumping passes: {num_jump_passes} (max {max_jump_passes})")

    # ---- C_spins: max 3 spins ----
    if num_spins > 3:
        result.add_error(f"Too many spins: {num_spins} (max 3)")

    # ---- C_step_seq: exactly 1 step sequence ----
    if not has_step_seq:
        result.add_error("Missing step sequence (StSq)")

    # ---- C_choreo_seq: exactly 1 choreographic sequence ----
    if not has_choreo_seq:
        result.add_error("Missing choreographic sequence (ChSq)")

    # ---- C_combo_count: max 3 combinations/sequences ----
    combo_count = sum(1 for jp in jump_passes if len(jp) > 1)
    if combo_count > 3:
        result.add_error(f"Too many jump combinations/sequences: {combo_count} (max 3)")

    # ---- C_combo_triple: max 1 three-jump combination ----
    triple_combos = sum(1 for jp in jump_passes if len(jp) >= 3)
    if triple_combos > 1:
        result.add_error(f"Too many three-jump combinations: {triple_combos} (max 1)")

    # ---- C_euler: Euler (1Eu) max once ----
    euler_count = sum(1 for jp in jump_passes for code in jp if code == "1Eu")
    if euler_count > 1:
        result.add_error(f"Euler (1Eu) used {euler_count} times (max 1)")

    # ---- C_axel: at least 1 Axel-type jump ----
    all_jump_codes = [code for jp in jump_passes for code in jp]
    has_axel = any(_is_axel(c) for c in all_jump_codes)
    if not has_axel:
        result.add_warning("No Axel-type jump — ISU requires at least one")

    # ---- C_spin_types: all different spin families ----
    if segment == "free_skate" and num_spins > 0:
        spin_types: set[str] = set()
        for code in spin_codes:
            if "SpB" in code:
                spin_types.add("camel")
            elif code.startswith("CSp"):
                spin_types.add("combo")
            elif code.startswith("FSp"):
                spin_types.add("flying")
            elif code.startswith("LSp"):
                spin_types.add("layback")
            elif code.startswith("USp"):
                spin_types.add("upright")
            else:
                spin_types.add("other")
        if len(spin_types) < num_spins:
            result.add_warning(
                f"Duplicate spin types: {len(spin_types)} unique out of {num_spins} spins"
            )
    elif segment == "short_program" and num_spins > 2:
        result.add_error(f"Too many spins for Short Program: {num_spins} (max 2)")

    # ---- C_zayak: jumps with 3+ rotations max 2 attempts ----
    jump_counts: dict[str, int] = {}
    for code in all_jump_codes:
        el = get_element(code)
        if el and el.rotations >= 3.0 and code != "1Eu":
            jump_counts[code] = jump_counts.get(code, 0) + 1

    for code, count in jump_counts.items():
        if count > 2:
            result.add_error(f"Zayak rule violation: {code} attempted {count} times (max 2)")
        elif count == 2:
            # Check if at least one is in a combination
            in_combo = 0
            for jp in jump_passes:
                if code in jp and len(jp) > 1:
                    in_combo += 1
            if in_combo == 0:
                result.add_error(
                    f"Zayak rule: {code} attempted twice but not in any combination/sequence"
                )

    return result
