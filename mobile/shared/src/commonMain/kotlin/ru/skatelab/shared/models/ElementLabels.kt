package ru.skatelab.shared.models

/**
 * Canonical, locale-agnostic element-type keys shared with the backend contract
 * (see `backend/app/metrics_registry.py` — `JUMP_ELEMENTS`, `SPIN_ELEMENTS`,
 * `three_turn`). UI display strings live in `strings.xml` (`element_<key>`),
 * resolved per-locale — never inline these as literals (#331).
 *
 * This list is the single source of the picker catalog and ordering. When the
 * contract migrates to ISU codes (2A, 3T, StSq, CoSp4, …), this is the seam:
 * swap the keys here and the matching `element_<key>` resources; UI rendering
 * code stays unchanged.
 */
val elementTypes: List<String> = listOf(
    "waltz_jump",
    "toe_loop",
    "flip",
    "lutz",
    "salchow",
    "loop",
    "axel",
    "three_turn",
    "spin",
)