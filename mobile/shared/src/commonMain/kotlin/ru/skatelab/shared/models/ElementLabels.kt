package ru.skatelab.shared.models

/**
 * Canonical ISU element codes shared with the backend contract
 * (see `backend/app/services/choreography/elements_db.py` — `ELEMENTS` dict,
 * Task 1 of the ISU element-vocabulary migration). The code itself (e.g.
 * `"3A"`, `"StSq4"`) is locale-agnostic and shown verbatim; the full localized
 * name lives in `strings.xml` (`element_<code-lowercased>_name`), resolved
 * per-locale — never inline the name as a literal (#331).
 *
 * This list is the single source of the picker catalog and ordering. Codes
 * are grouped by family (jumps by rotation within a family, then spins, step
 * sequences, choreo). UI rendering code (`elementLabel`, picker) consumes keys
 * unchanged — only the key set and the matching resources swapped (#333 seam).
 */
val elementTypes: List<String> = listOf(
    // Axel
    "1A", "2A", "3A", "4A",
    // Toe loop
    "1T", "2T", "3T", "4T",
    // Salchow
    "1S", "2S", "3S", "4S",
    // Loop (Риттбергер)
    "1Lo", "2Lo", "3Lo", "4Lo",
    // Flip
    "1F", "2F", "3F", "4F",
    // Lutz
    "1Lz", "2Lz", "3Lz", "4Lz",
    // Euler (half-loop)
    "1Eu",
    // Combination spins (change foot)
    "CSp1", "CSp2", "CSp3", "CSp4",
    // Step sequences
    "StSq1", "StSq2", "StSq3", "StSq4",
    // Choreographic sequence
    "ChSq1",
)