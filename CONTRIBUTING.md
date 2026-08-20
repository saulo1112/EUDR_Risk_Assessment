# Contributing

## Development setup

```bash
uv sync                                        # installs runtime + dev deps
docker compose -f docker/docker-compose.yml up -d db   # PostGIS for integration tests
```

## Checks before opening a PR

```bash
uv run ruff check .          # lint
uv run pytest                # unit + API tests (no infrastructure needed)
uv run pytest -m integration # integration tests (needs the db container)
```

Both are enforced by CI (`.github/workflows/ci.yml`).

## Conventions

- **Language**: code, comments and docstrings in English.
- **Configuration**: never hardcode connection strings, project ids or model
  constants. Add them to [`src/config.py`](src/config.py) and read from there.
- **Pipeline scripts** must stay importable: put the work inside `main()` behind
  an `if __name__ == "__main__":` guard, so importing a module never opens a
  database connection or contacts Earth Engine. The pure, testable logic belongs
  in [`src/pipeline/scoring.py`](src/pipeline/scoring.py).
- **Run scripts as modules** so absolute imports resolve:
  `uv run python -m src.pipeline.phase2_deforestation`.
- **Line length** 90 (ruff-enforced).

## Model changes

The risk model must never consume a parcel's own `defo_pct` (or anything derived
from it) as a feature. That is the label, and using it produces the target
leakage documented in [`docs/phase4_model_comparison.md`](docs/phase4_model_comparison.md).
`tests/test_scoring.py::TestFeatureSets::test_no_variant_leaks_the_label`
guards this.

When changing features or thresholds, re-run the comparison and update both
`docs/phase4_model_comparison.md` and the metrics quoted in the README.
