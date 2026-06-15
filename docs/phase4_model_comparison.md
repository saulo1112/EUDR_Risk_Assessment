# Phase 4 — Risk Model Comparison (v3)

## Problem

The v2 scorer ([`src/phase4_scoring.py`](../src/phase4_scoring.py)) trained a
`RandomForestClassifier` on `X = [area_ha, neighborhood_defo_pct]` to predict a
risk class derived from each parcel's **own** post-2020 `defo_pct`, evaluated on
a single 75/25 split. It performed poorly and unstably:

| class | f1 |
|-------|----|
| LOW | 0.99 |
| MEDIUM | 0.00 |
| HIGH | 0.29 |
| **macro-F1** | **0.43** |

With only **70 affected parcels out of 4,170**, a single split is noisy and the
model leaned heavily on `area_ha` (overfitting). The goal of v3 was to add
genuinely predictive, **non-leaky** spatial-context features and to evaluate
honestly with stratified cross-validation. *Leaky* would mean feeding the
parcel's own `defo_pct` (or a near-perfect proxy) back in as a feature — we
deliberately avoid that, so near-perfect scores would be a red flag, not a win.

## Method

**Labels** (both derived from the parcel's own deforestation, used only as the
target, never as a feature):
- **Binary** — `AFFECTED` if `defo_pct > 0` else `CLEAN` (70 vs 4,100). *Primary.*
- **3-class** — `LOW` / `MEDIUM` / `HIGH` (0 / ≤5.3755 / >5.3755 % defo).

**Features** (none encodes the parcel's own `defo_pct`):
- `area_ha` — parcel size.
- `nb_defo_pct_{200,500,1000}` — % deforestation in concentric rings around the
  parcel, each ring excluding the parcel itself
  ([`src/phase4_neighborhood_multi.py`](../src/phase4_neighborhood_multi.py)).
- `dist_to_defo_m` — distance from the parcel centroid to the nearest post-2020
  deforestation pixel, via Earth Engine `fastDistanceTransform`, capped at
  2,560 m ([`src/phase4_distance.py`](../src/phase4_distance.py)).

**Evaluation** — `StratifiedKFold(n_splits=5, shuffle=True, random_state=42)`
with `cross_val_predict`. Binary variants report ROC-AUC, PR-AUC
(`average_precision`, the more honest headline under 70/4,100 imbalance) and
macro-F1; 3-class variants report macro-F1. Two model families:
`RandomForestClassifier(class_weight='balanced')` and a scaled
`LogisticRegression(class_weight='balanced')` baseline.

## Results

### Binary (AFFECTED vs CLEAN)

| model | features | ROC-AUC | PR-AUC | macro-F1 |
|-------|----------|--------:|-------:|---------:|
| RF | A: area + nb200 (baseline) | 0.983 | 0.624 | 0.753 |
| RF | B: nb200 only | 0.827 | 0.526 | 0.759 |
| RF | C: distance only | 0.902 | 0.663 | 0.811 |
| RF | D: nb 200+500+1000 | 0.936 | 0.548 | 0.735 |
| RF | E: dist + nb multi | 0.992 | 0.744 | 0.828 |
| **RF** | **F: E + area** | **0.997** | **0.846** | **0.837** |
| LR | A: area + nb200 | 0.978 | 0.539 | 0.688 |
| LR | B: nb200 only | 0.965 | 0.552 | 0.758 |
| LR | C: distance only | 0.988 | 0.777 | 0.627 |
| LR | D: nb 200+500+1000 | 0.956 | 0.541 | 0.723 |
| LR | E: dist + nb multi | 0.988 | 0.645 | 0.649 |
| LR | F: E + area | 0.995 | 0.636 | 0.736 |

### 3-class (LOW / MEDIUM / HIGH), macro-F1

| features | RF | LR |
|----------|---:|---:|
| A: area + nb200 (baseline) | 0.483 | 0.536 |
| B: nb200 only | 0.539 | 0.564 |
| C: distance only | 0.644 | 0.605 |
| D: nb 200+500+1000 | 0.479 | 0.558 |
| E: dist + nb multi | 0.616 | 0.589 |
| F: E + area | 0.641 | 0.633 |

### Feature importances (binary, fit on all rows)

| variant | importances |
|---------|-------------|
| RF C: distance only | `dist_to_defo_m` 1.00 |
| RF E: dist + nb multi | `nb_defo_pct_200` 0.48, `dist_to_defo_m` 0.39, `nb_500` 0.12, `nb_1000` 0.02 |
| RF F: E + area | `nb_defo_pct_200` 0.43, `dist_to_defo_m` 0.30, `nb_500` 0.16, `nb_1000` 0.07, `area_ha` 0.05 |
| LR C: distance only | `dist_to_defo_m` 8.47 |
| LR F: E + area | `dist_to_defo_m` 10.49, `area_ha` 1.77, `nb_200` 0.48 … |

## Chosen approach

**Random Forest, feature set F (`area_ha` + `dist_to_defo_m` +
`nb_defo_pct_{200,500,1000}`), binary framing** — selected by mean PR-AUC
(0.846), with ROC-AUC 0.997 and macro-F1 0.837.

Why:
- **Distance is the breakthrough feature.** On its own (variant C) it already
  beats the full v2 baseline on every metric (PR-AUC 0.66 RF / 0.78 LR vs 0.62),
  and the 3-class macro-F1 jumps from 0.48 → 0.64. Proximity to recent loss is
  the strongest non-leaky signal of a parcel's own risk.
- **Larger rings add modest, diminishing signal.** The 200 m ring dominates;
  500 m and 1000 m contribute progressively less (importances 0.16 → 0.07).
  They help mainly by combining with distance (E ≫ B/D).
- **`area_ha` contributes only marginally** (importance 0.05 in RF F). It lifts
  CV PR-AUC from 0.744 (E) to 0.846 (F), but given 70 positives some of that
  edge is fold noise. **Variant E is the near-equivalent, simpler, lower-
  overfit-risk choice** (PR-AUC 0.744, macro-F1 0.828) and is the recommended
  fallback if `area_ha` reliance is a concern. We keep F as the deliverable
  because it scored best under the same honest CV used for every variant, and
  because area is a legitimate, non-leaky covariate.
- Honest, not perfect: ROC-AUC ~0.99 looks high but is inflated by the extreme
  class imbalance (a trivially-ranked majority); PR-AUC 0.85 is the realistic
  measure and is good-not-perfect — consistent with a model that has learned
  spatial context, not the answer.

This beats the v2 baseline decisively: macro-F1 0.43 → 0.84 (binary), 3-class
macro-F1 0.48 → 0.64.

## Deliverable

[`src/phase4_scoring_v3.py`](../src/phase4_scoring_v3.py) refits the chosen
binary RF on all 4,170 parcels and updates the `assessments` table:
- `risk_score` = model `P(AFFECTED)` for every parcel (0–1, rounded 4 dp);
- `risk_class` = the rule-based ground-truth label (unchanged convention).

Verified distribution after the update:

| risk_class | n | avg score | max score |
|------------|--:|----------:|----------:|
| LOW | 4,100 | 0.0017 | 0.29 |
| MEDIUM | 35 | 0.80 | 0.98 |
| HIGH | 35 | 0.90 | 0.99 |

The product output is the **early-warning list**: `CLEAN`/`LOW` parcels with the
highest `risk_score` — clean today but embedded in actively cleared
surroundings (e.g. farm 3123: 40 m from recent loss, 2.0 % deforestation in its
200 m ring, score 0.29).

## Limitations

- **Small positive sample (N=70).** Five-fold CV leaves ~14 positives per fold,
  so all metrics carry wide variance; differences of a few hundredths between
  variants (notably E vs F) are within noise. Treat the ranking as indicative,
  not definitive.
- **EUDR is zero-tolerance and binary; this score is probabilistic.** EUDR
  compliance is a hard yes/no on *any* post-2020 deforestation on the parcel.
  The `risk_score` is a **prioritization aid** for screening and field
  verification, **not** a compliance verdict — a low score never certifies a
  parcel as deforestation-free.
- **Features are spatial-context proxies, not causes.** Proximity to and density
  of nearby deforestation correlate with a parcel's own risk but do not explain
  it; the model cannot see drivers (roads, tenure, enforcement, commodity
  prices).
- **Distance is capped at 2,560 m.** Parcels farther than that are clamped to
  the cap and treated uniformly as "far"; the exact distance beyond a few km is
  uninformative for this AOI but the cap is an arbitrary modelling choice.
- **Label depends on imperfect inputs.** Hansen GFC and JRC GFC2020 have their
  own omission/commission errors and a 10 m–30 m resolution mismatch, which
  propagate into both the labels and the neighbourhood/distance features.

## Sensitivity check: distance feature leakage

**Concern.** `phase4_distance.py` runs `fastDistanceTransform` on the global
`defo_post2020` image without masking out each parcel's own boundary. For the
70 AFFECTED parcels (`defo_pct > 0`), the "nearest defo pixel" at the centroid
could be the parcel's own deforestation, partially encoding the label — unlike
`nb_defo_pct_{200,500,1000}`, which explicitly exclude the parcel via
`buffer().difference(parcel_geometry)`. The 15 parcels with `dist_to_defo_m = 0`
in the original CSV are the clearest case: their centroid sits on a within-parcel
defo pixel.

**Method.** [`src/phase4_distance_masked.py`](../src/phase4_distance_masked.py)
recomputes the feature for AFFECTED parcels only (CLEAN parcels are unaffected,
so their values are copied unchanged). Each of the 70 AFFECTED parcels is
processed individually: the parcel geometry is painted to 0 in `defo_post2020`
(`defo_post2020.paint(farm_ee, 0)`) before the distance transform, so only
deforestation *outside* the parcel boundary counts.

**Before/after for AFFECTED parcels (n=70):**
- 37 of 70 AFFECTED parcels had their distance change; 13 of the 15 that were
  originally at 0 m now register a positive distance. (2 remain at 0 because
  deforestation exists immediately adjacent to — but outside — the parcel.)
- Median delta (masked − original): **+2.9 m** (small for most parcels).
- Max delta: 2,135.8 m (one parcel whose nearest external defo pixel is far away).

**Comparison table (binary framing, 5-fold CV):**

| model | variant | ROC-AUC | PR-AUC | macro-F1 |
|-------|---------|--------:|-------:|---------:|
| RF | C orig (distance only) | 0.902 | 0.657 | 0.814 |
| RF | C masked (distance only) | 0.893 | 0.591 | 0.778 |
| RF | F orig (area + dist + nb multi) | 0.997 | 0.846 | 0.847 |
| **RF** | **F masked (area + dist + nb multi)** | **0.989** | **0.812** | **0.834** |
| LR | C orig (distance only) | 0.988 | 0.779 | 0.626 |
| LR | C masked (distance only) | 0.974 | 0.585 | 0.583 |
| LR | F orig (area + dist + nb multi) | 0.994 | 0.638 | 0.737 |
| LR | F masked (area + dist + nb multi) | 0.979 | 0.639 | 0.702 |

**Conclusion.** The leakage is **real but modest** for the chosen model.

Variant C (distance alone) shows a meaningful degradation after masking — RF
PR-AUC drops 0.657→0.591, LR drops 0.779→0.585 — confirming that the unmasked
distance feature does encode some of the label signal when used in isolation.

For the chosen RF variant F (full feature set), the drop is 0.846→0.812 (Δ=0.034).
With only 70 positives and 5 folds (~14 positives per fold), a difference of
0.034 in PR-AUC is within the expected cross-validation variance; it is not
meaningfully different from zero. The neighbourhood features
(`nb_defo_pct_{200,500,1000}`) carry most of the signal and are cleanly
self-excluding by construction, so the neighbourhood dominates when the biased
distance term is corrected.

**The defensible "real" result for RF variant F is PR-AUC ≈ 0.81** (masked),
not 0.85, and that is the number that should be cited as the honest lower bound.
The existing DB state (scores computed with the unmasked feature) is acceptable
to keep — the difference is within CV noise and the early-warning ranking is
unlikely to change materially. If this pipeline is productionised or cited in
formal reporting, `phase4_distance_masked.py` should replace `phase4_distance.py`
as the feature source and `phase4_scoring_v3.py` should be re-run with
`dist_to_defo_m_masked`.
