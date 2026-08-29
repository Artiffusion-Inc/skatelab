# ML Experiments

Exploratory work only. Production code must not import `experiments/`.

## Rules

- State hypothesis, method, dataset/split, configuration, metrics, and conclusion.
- Use status `PENDING`, `CONFIRMED`, `REJECTED`, or `INCONCLUSIVE`.
- Record experiments in `experiments/README.md` with evidence links.
- Save large checkpoints/logs under ignored paths; never commit weights or datasets.
- Fix random seeds and capture environment/model versions where reproducibility matters.
- Promote code into `ml/src/` only after validation, tests, and explicit integration work.

Run scripts from repository root with `uv run python experiments/<script>.py`; GPU experiments require CUDA setup.
