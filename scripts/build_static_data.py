"""Build the static JSON data files that back the GitHub Pages dashboard.

GitHub Pages only serves static files, so it cannot run the FastAPI + PostGIS
backend (that still requires Render or another host, and is entirely
optional). The dashboard's three read-only calls never take a farm-specific
filter from the UI (see src/frontend/app.js: it always requests the full
/farms collection and does its filtering client-side), so their responses
can be precomputed once and served as plain files.

This script reproduces exactly what those endpoints return by reading the
same two committed inputs the database is seeded from, with no database
required:

  - data/farms.geojson                  -> geometry + area_ha per farm
  - docker/init/20_eudr_risk.sql.gz      -> defo_pct / risk_score / risk_class
                                             per farm (the `assessments` table,
                                             parsed straight out of its COPY
                                             block; this is the exact seed
                                             loaded into the last live DB)

Output (consumed by app.js when window.API_STATIC is true):
  src/frontend/data/farms.json          -- GeoJSON FeatureCollection, all farms
  src/frontend/data/stats.json          -- same shape as GET /stats
  src/frontend/data/early-warning.json  -- same shape as GET /early-warning

Run with: python scripts/build_static_data.py
"""
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FARMS_GEOJSON = ROOT / "data" / "farms.geojson"
SEED_DUMP = ROOT / "docker" / "init" / "20_eudr_risk.sql.gz"
OUT_DIR = ROOT / "src" / "frontend" / "data"

# Matches the frontend's `/early-warning?limit=15` call, with headroom so a
# small future bump to that limit doesn't require regenerating this file.
EARLY_WARNING_CAP = 100


def parse_assessments(dump_path: Path) -> dict[int, dict]:
    """Parse the `assessments` table straight out of the pg_dump COPY block.

    Columns: id, farm_id, defo_m2, total_m2, defo_pct, risk_score,
    risk_class, assessed_at (tab-separated, one row per line).
    """
    assessments: dict[int, dict] = {}
    in_block = False
    with gzip.open(dump_path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("COPY public.assessments "):
                in_block = True
                continue
            if not in_block:
                continue
            if line.rstrip("\n") == "\\.":
                break
            cols = line.rstrip("\n").split("\t")
            (_id, farm_id, _defo_m2, _total_m2,
             defo_pct, risk_score, risk_class, _ts) = cols
            assessments[int(farm_id)] = {
                "defo_pct": float(defo_pct),
                "risk_score": float(risk_score),
                "risk_class": risk_class,
            }
    if not assessments:
        raise RuntimeError("No rows parsed from the assessments COPY block.")
    return assessments


def build_farms(geojson_path: Path, assessments: dict[int, dict]) -> list[dict]:
    """Merge farm geometry/area with its assessment, mirroring the API's
    `FarmProperties` shape (farm_id, area_ha, defo_pct, risk_score,
    risk_class only -- the geojson's extra `count`/`label` fields, used only
    internally by the pipeline, are dropped)."""
    raw = json.loads(geojson_path.read_text(encoding="utf-8"))
    features = []
    missing = []
    for feat in raw["features"]:
        farm_id = feat["properties"]["farm_id"]
        a = assessments.get(farm_id)
        if a is None:
            missing.append(farm_id)
            continue
        features.append({
            "type": "Feature",
            "geometry": feat["geometry"],
            "properties": {
                "farm_id": farm_id,
                "area_ha": feat["properties"]["area_ha"],
                "defo_pct": a["defo_pct"],
                "risk_score": a["risk_score"],
                "risk_class": a["risk_class"],
            },
        })
    if missing:
        print(f"warning: {len(missing)} farms have no assessment, skipped "
              f"(e.g. {missing[:5]})")
    features.sort(key=lambda f: f["properties"]["farm_id"])
    return features


def build_stats(features: list[dict]) -> dict:
    total_parcels = len(features)
    total_area_ha = round(sum(f["properties"]["area_ha"] or 0 for f in features), 2)

    by_class: dict[str, list[float]] = {}
    for f in features:
        p = f["properties"]
        by_class.setdefault(p["risk_class"], []).append(p["risk_score"])

    rows = []
    for risk_class, scores in by_class.items():
        rows.append({
            "risk_class": risk_class,
            "count": len(scores),
            "avg_risk_score": round(sum(scores) / len(scores), 4),
            "min_risk_score": min(scores),
            "max_risk_score": max(scores),
        })
    rows.sort(key=lambda r: r["avg_risk_score"], reverse=True)

    return {
        "total_parcels": total_parcels,
        "total_area_ha": total_area_ha,
        "by_risk_class": rows,
    }


def build_early_warning(features: list[dict], cap: int) -> dict:
    low = [f for f in features if f["properties"]["risk_class"] == "LOW"]
    low.sort(key=lambda f: f["properties"]["risk_score"], reverse=True)
    return {"type": "FeatureCollection", "features": low[:cap]}


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1_048_576:.1f} MiB)")


def main() -> None:
    assessments = parse_assessments(SEED_DUMP)
    features = build_farms(FARMS_GEOJSON, assessments)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(OUT_DIR / "farms.json",
               {"type": "FeatureCollection", "features": features})
    write_json(OUT_DIR / "stats.json", build_stats(features))
    write_json(OUT_DIR / "early-warning.json",
               build_early_warning(features, EARLY_WARNING_CAP))


if __name__ == "__main__":
    main()
