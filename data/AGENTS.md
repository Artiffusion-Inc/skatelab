# Data

- `DATASETS.md` is dataset registry and relationship source of truth.
- `datasets/raw/` contains immutable source data; never modify in place.
- `datasets/unified/` contains reproducible converted formats.
- `data_tools/` owns converters and validation.
- `models/` contains local model assets excluded from Git.

## Rules

- Never commit videos, checkpoints, model weights, personal data, or licensed datasets.
- Record provenance, license, checksum, split strategy, and conversion command for new datasets.
- Prevent train/validation/test identity leakage.
- Converters must be deterministic or record seeds and parameters.
- Validate output counts and schema before training.
