# docs/CLAUDE.md — Documentation

## Structure

```
docs/
├── DATASETS.md                        # Dataset registry and relationships
├── research/                          # Research findings and paper summaries
│   ├── RESEARCH.md                    # Research memory bank (index)
│   ├── RESEARCH_SUMMARY_2026-03-28.md # Exa + Gemini findings (41 papers)
│   ├── RESEARCH_POSE_TOOLS_2026-03-31.md  # Pose estimation tool comparison
│   ├── RESEARCH_POSE_MODEL_SKATING_2026-04-12.md  # CIGPose, DINO detection analysis
│   ├── RESEARCH_POSE_PARADIGMS_2026-04-25.md      # SimCC vs RLE paradigm research
│   ├── RESEARCH_AQA_FIGURE_SKATING_2026-04-12.md  # Action quality assessment
│   ├── RESEARCH_CHOREOGRAPHY_PLANNING_2026-04-12.md  # Gemini choreography research
│   ├── RESEARCH_SKELETON_ACTION_RECOGNITION_2026-04-12.md  # SkelFormer, HI-GCN
│   ├── RESEARCH_TEMPORAL_ACTION_SEGMENTATION_2026-04-12.md  # BIOES-tagging
│   ├── RESEARCH_VIFSS_2026-04-12.md   # View-invariant pose representation
│   ├── RESEARCH_80PCT_PATH_2026-04-12.md  # Path to 90%+ accuracy
│   ├── PIPELINE_PROFILING_2026-04-18.md   # ONNX op-level, DeepSORT profiling
│   ├── ATHLETEPOSE3D_INTEGRATION.md   # AthletePose3D dataset integration
│   └── ...                            # IMU, segmentation, Re-ID, spatial reference
├── specs/                             # Technical specifications (design docs)
│   ├── 2026-04-11-i18n-design.md
│   ├── 2026-04-11-s3-only-storage-design.md
│   ├── 2026-04-11-saas-auth-db-profiles-design.md
│   ├── 2026-04-11-strava-fs-design.md
│   ├── 2026-04-11-nike-design-system.md
│   ├── 2026-04-11-vifss-embeddings.md
│   ├── 2026-04-12-choreography-planner-design.md
│   ├── 2026-04-17-parallelization-design.md
│   ├── 2026-04-19-choreography-parallelism-design.md
│   ├── 2026-04-19-parallelism-async-audit-design.md
│   ├── 2026-04-29-api-design-fixes.md
│   └── ...
└── plans/                             # Implementation plans (from writing-plans skill)
    ├── 2026-04-02-rtmpose-finetune-dataset.md
    ├── 2026-04-11-i18n.md
    ├── 2026-04-11-s3-only-storage.md
    ├── 2026-04-11-saas-auth-db-profiles.md
    ├── 2026-04-11-strava-fs-mvp.md
    ├── 2026-04-12-choreography-planner.md
    ├── 2026-04-29-test-coverage-improvement.md
    └── ...
```

## Subdirectories

| Directory | Purpose | Naming Convention |
|-----------|---------|-------------------|
| `research/` | Paper summaries, Exa/Gemini findings, integration notes | `RESEARCH_*.md`, `*_RESEARCH.md`, `PIPELINE_PROFILING_*.md` |
| `specs/` | Design documents from brainstorming skill | `YYYY-MM-DD-<topic>-design.md` |
| `plans/` | Implementation plans with bite-sized tasks | `YYYY-MM-DD-<feature>.md` |

## Key References

- `research/RESEARCH_SUMMARY_2026-03-28.md` — comprehensive summary of 41 papers across 5 themes
- `research/RESEARCH_POSE_TOOLS_2026-03-31.md` — YOLO, RTMPose, Pose3DM comparison
- `research/RESEARCH_POSE_MODEL_SKATING_2026-04-12.md` — CIGPose, DINO detection, path to 90%+
- `research/RESEARCH_POSE_PARADIGMS_2026-04-25.md` — SimCC vs RLE (8.5pp gap analysis)
- `research/PIPELINE_PROFILING_2026-04-18.md` — ONNX op-level profiling, DeepSORT internals
- `research/RESEARCH_CHOREOGRAPHY_PLANNING_2026-04-12.md` — Gemini deep research on choreography planning
- `../data/DATASETS.md` — dataset registry with download links and relationships
- `@CLAUDE.md` — project overview and architecture reference
