---
title: "Choreography Editor — MVP Design"
date: "2026-05-11"
status: draft
scope: MVP for manual figure skating program creation with ISU-compliant rink visualization
---

# Choreography Editor — MVP Design

## Executive Summary

MVP = manual drag-n-drop editor for figure skating programs. No AI generation. Coach uploads music → sees waveform with beat markers → drags jumps/spins/sequences onto timeline + rink diagram → gets real-time ISU validation + TES score → exports SVG.

**Key decision:** Rink diagram renders with real ISU ice rink dimensions (30m×61m), regulation lines (centre red, blue mid-lines, face-off circles), and numbered element markers. Skreate-inspired visual fidelity without Rust/WASM overhead.

**Out of MVP:** automatic program generation (CSP solver wizard), undo/redo, collaboration, PDF export.

---

## 1. User Workflow

1. **Upload music** → async analysis (BPM, duration, beat markers)
2. **Edit program** → drag elements from picker onto 3 timeline tracks (Jumps, Spins, Sequences)
3. **Position on rink** → drag markers on ISU rink diagram or auto-layout
4. **Validate** → real-time ISU rule checking (combo limits, spin diversity, Zayak)
5. **Score** → live TES calculation with BV + GOE + back-half bonus
6. **Save/Export** → persist program, export rink as SVG

---

## 2. Architecture

```
backend/app/services/choreography/
├── elements_db.py               # ISU element registry (static + parsed)
├── pdf_parser.py                # SoV PDF → structured element data
├── rules_engine.py              # ISU rules validation
├── score_calculator.py          # TES + GOE + PCS calculation
├── music_analyzer.py            # madmom + MSAF wrapper
├── csp_solver.py                # Random search (v1.2: OR-Tools)
├── rink_renderer.py             # Server-side SVG generation
└── fingerprint.py               # Audio deduplication

frontend/src/components/choreography/
├── editor/
│   ├── store.ts                 # Zustand state (elements, playback, timeline)
│   ├── waveform-view.tsx        # WaveSurfer.js with beat markers
│   ├── track-row.tsx            # Timeline track with grid, ruler, element chips
│   ├── track-element.tsx        # Draggable element chip
│   ├── element-picker.tsx       # Element palette (jumps, spins, sequences)
│   └── element-editor.tsx       # GOE/duration/position popover
├── rink-diagram.tsx             # ISU-compliant SVG rink (drag-n-drop markers)
├── rink-renderer.ts             # Static SVG string renderer (server export)
├── score-bar.tsx                # TES/element count/validation status
└── music-uploader.tsx           # Upload + analysis status
```

---

## 3. Rink Diagram (ISU-Compliant)

### Dimensions
- ViewBox: `0 0 30 61` (width=30m, height=61m) — portrait orientation, long axis vertical
- Origin: top-left corner of ice surface
- Units: meters

### Ice Surface Lines (all required)

| Line | Color | Position | Stroke |
|------|-------|----------|--------|
| Boundary | Red (#dc2626) | Rounded rect 30×61, r=7.5 | 0.15 |
| Centre line | Red (#dc2626) | y=30.5, full width | 0.12 solid |
| Blue lines | Blue (#2563eb) | y=8.5, y=52.5, full width | 0.10 solid |
| End lines | Red (#dc2626) | y=4, y=57, full width | 0.10 solid |
| Centre circle | Red (#dc2626) | cx=15, cy=30.5, r=1.5 | 0.10 |
| Centre dot | Red (#dc2626) | cx=15, cy=30.5, r=0.12 | fill |
| Face-off circles (4) | Red (#dc2626) | (±6, ±11) from center, r=3 | 0.08 |
| Face-off dots (5) | Red (#dc2626) | center + 4 circles, r=0.15 | fill |
| Corner creases (4) | Red (#dc2626) | 180° arcs at corners, r=1.8 | 0.08 |

### Element Markers

Each element on rink gets:
- **Number badge** — white circle with red border, purple bold number (sequence order)
- **Code label** — below marker, small text
- **Type shape:**
  - Jumps: circle + entry/exit arc (like skreate jump traces)
  - Spins: larger circle with cross inside
  - Step sequences: dashed rectangle
  - Choreo sequences: diamond

### Drag Behavior
- Elements snap to 0.5m grid when `snapRink` enabled
- Additional snap targets: centre line (y=30.5), blue lines (y=8.5, 52.5), end lines (y=4, 57), face-off dots
- Clamp to `PAD..VW-PAD` (0.5m from boundary)

### Auto-Layout
- Serpentine pattern filling rink from one end to other
- Respect standard skating direction (counter-clockwise preference)
- Spacing ≥ 3m between adjacent elements

---

## 4. Timeline

### Tracks
3 fixed tracks: **Jumps**, **Spins**, **Sequences**

### Waveform
- WaveSurfer.js renders audio waveform
- Vertical beat markers overlay at `beatTimestamp * pixelsPerSecond`
- Phrase markers (taller, different color) at downbeats

### Element Chips
- Width = duration × pixelsPerSecond (min 50px)
- Color per track type (jumps=orange, spins=purple, sequences=green)
- Show: code, GOE badge (±x), back-half indicator

### Drag-n-Drop
- `onPointerDown` → `setPointerCapture` → `onPointerMove` updates timestamp
- Snap modes: `off` | `beats` | `phrases`
- `Shift+drag` for fine adjustment (0.1s)

### Ruler
- Time labels every 5s
- Current time playhead (red vertical line)

---

## 5. ISU Validation (Real-Time)

Backend `rules_engine.py` validates on every save. Frontend shows cached result.

### Checked Rules
- Max 7 jump passes (Free Skate)
- Max 3 jump combinations/sequences
- Max 1 three-jump combination
- Max 3 spins, all different types
- Exactly 1 step sequence
- Exactly 1 choreographic sequence
- Euler (1Eu) max once
- Zayak rule (no repeated jump in same ½ rotation except 2A)
- Back-half bonus: last 3 jumps after program midpoint get 1.1× BV

### UI Feedback
- Score bar shows: TES, element counts (x/y), validation status
- Red warning if rule violated
- Yellow warning if approaching limit (e.g. 6/7 jumps)

---

## 6. Score Calculation

### Frontend (live, approximate)
- `calculateClientSideTes(elements)` — sum BV × GOE_factor
- GOE factor: [-5,-3]=0.5, [-2,2]=0.7, [3,5]=1.0
- Back-half: 1.1× for qualifying jumps

### Backend (authoritative)
- `score_calculator.py` — same logic, authoritative for exports

---

## 7. Element Picker

### Jumps
All single jumps 1T–4T, 1S–4S, 1Lo–4Lo, 1F–4F, 1Lz–4Lz, 1A–3A
Plus combinations: `+2T`, `+2Lo`, `+2S`, `Eu` (Euler)

### Spins
USp, LSp, CSp, SSsp, FSp, CCoSp, FCSp, combo variants
Levels 1–4 (BV from ISU scale)

### Sequences
StSq1–StSq4, ChSq1–ChSq4

### Search
Filter by code prefix (type `3Lz` → shows 3Lz, 4Lz, 3Lz+2T)

---

## 8. Data Model

```typescript
interface Program {
  id: string
  title: string
  discipline: "mens" | "ladies"
  segment: "short" | "free"
  musicAnalysisId: string | null
  audioUrl: string | null
  duration: number // seconds
  elements: TimelineElement[]
  rinkPreset: "olympic" | "nhl" | "training"
  createdAt: string
  updatedAt: string
}

interface TimelineElement {
  id: string
  code: string
  trackType: "jumps" | "spins" | "sequences"
  timestamp: number // seconds from start
  duration: number
  goe: number // -5 to +5
  position: { x: number; y: number } | null // rink coords, meters
  notes?: string
}
```

---

## 9. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/choreography/music/upload` | Upload audio → enqueue analysis |
| GET | `/choreography/music/{id}/analysis` | Get BPM, duration, beat markers |
| GET | `/choreography/elements/registry` | ISU element DB (code, name, BV, type) |
| POST | `/choreography/validate` | Validate layout → errors/warnings |
| POST | `/choreography/programs` | Create new program |
| GET | `/choreography/programs/{id}` | Load program |
| PUT | `/choreography/programs/{id}` | Save program |
| POST | `/choreography/programs/{id}/export` | Export SVG/JSON |

---

## 10. Testing

### Frontend
- `store.test.ts`: initFromProgram, CRUD, getLayoutForSave, TES calc
- `rink-diagram.test.tsx`: drag coordinates, snap logic, marker positions
- `track-element.test.tsx`: drag timestamp, snap modes, delete

### Backend
- `test_rules_engine.py`: each rule in isolation
- `test_score_calculator.py`: TES with GOE, back-half bonus
- Integration: round-trip create → validate → export

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| ISU rules change annually | Rules engine as single file; update each season |
| Rink diagram performance (many SVG elements) | Virtualization or `will-change: transform` |
| WaveSurfer zoom sync with timeline | Recreate WaveSurfer instance on `pixelsPerSecond` change |
| Mobile touch drag conflicts | `touch-action: none` on SVG container |

---

## 12. ISU Element Data Pipeline

ISU публикует Scale of Values (SoV) ежегодно в PDF. Нет публичного API.

### SoV PDF Parser

Location: `backend/app/services/choreography/pdf_parser.py`

**Input:** ISU SoV PDF (URL или файл)  
**Output:** JSON массив `{ code, name, type, base_value, rotations, level, goe_range }`

**Parsing strategy:**
1. `pdfplumber` извлекает таблицы из PDF
2. Ищет таблицы с заголовками типа "Scale of Values", "Base Value"
3. Нормализует коды элементов: `3Lz` → `{ type: "jump", code: "3Lz", rotations: 3, name: "Lutz" }`
4. Сохраняет в `data/elements/isu_2026_27.json`

**CLI:**
```bash
uv run python -m backend.app.services.choreography.pdf_parser \
  --url "https://www.isu.org/documents/.../sov_2026_27.pdf" \
  --output data/elements/isu_2026_27.json
```

### Element Registry

`backend/app/services/choreography/elements_db.py` читает JSON при импорте:
```python
ELEMENTS = load_elements(Path(__file__).parent / "data" / "isu_2026_27.json")
```

**API endpoint:** `GET /choreography/elements/registry` возвращает текущий registry.

### Annual Update Process

1. ISU публикует новый SoV (обычно май–июнь)
2. Dev загружает PDF → запускает парсер → получает JSON
3. Ручная проверка JSON (diff с предыдущим сезоном)
4. Commit JSON + обновление `elements_db.py` если структура изменилась
5. Тег: `elements/2026-27`

### Risks

| Risk | Mitigation |
|------|------------|
| PDF формат меняется (таблица переезжает) | `pdfplumber` fallback на regex-извлечение |
| ISU вводит новые элементы (код неизвестен) | Парсер помечает unknown codes для ручной проверки |
| BV не распарсились как числа | Validation: все BV > 0 и < 30 |

---

## 13. Spec Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-05-11 | Assistant | Initial MVP spec |

---

*Spec status: draft. Pending user review before implementation plan.*
