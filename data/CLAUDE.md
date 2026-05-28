# data/CLAUDE.md — Data Files

## Structure

```
data/
├── DATASETS.md                        # Dataset registry and relationships
├── datasets/                          # Downloaded ML datasets
│   ├── raw/                           # Original files (read-only)
│   │   ├── figure-skating-classification/  # FSC (pkl) + MMFS quality scores
│   │   ├── mcfs/                           # MCFS (segments.pkl)
│   │   ├── skatingverse/                   # SkatingVerse (mp4, 46GB)
│   │   ├── athletepose3d/                  # AthletePose3D (71GB, 12 sports)
│   │   └── finefs/                         # FineFS (quality scores)
│   └── unified/                       # Converted format (ready for training)
│       ├── fsc-64/                   # FSC 64 classes
│       ├── mcfs-129/                 # MCFS 129 classes
│       └── skatingverse-28/          # SkatingVerse (pending extraction)
├── data_tools/                        # Converters, validation, label ontology
├── models/                            # ML model weights
└── experiments/                       # Experiment logs
```

## Datasets

| Dataset | Content | Size | Status |
|---------|---------|------|--------|
| AthletePose3D | 1.3M frames, 12 sports, 3D poses | 71GB | Downloaded |
| Figure-Skating-Classification | 5168 sequences, 64 classes | 340MB | Downloaded |
| MCFS | 2668 segments, 129 classes | 103MB | Downloaded |
| SkatingVerse | 28K videos, 28 classes | 46GB | Downloaded |

**MMFS deleted (2026-04-12):** Data was redundant — FSC = MMFS (4915) + mocap (253). Quality scores merged into FSC (`train_scores.npy`, `test_scores.npy`).

See `DATASETS.md` for full registry, download links, and inter-dataset relationships.

## Notes

- `models/` contains ONNX model weights (not in git — upload via `ml/scripts/convert_and_upload_models.py`)
- Large files (videos, model weights) are in `.gitignore`
- Use `data/data_tools/` converters to create unified format from raw data
