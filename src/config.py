"""Central configuration for the EUDR risk pipeline, API and scripts.

Single source of truth for connection settings, external project ids and the
model/feature constants that were previously duplicated across the phase
scripts. Everything is environment-overridable, with the local development
values as defaults so the repo works out of the box.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------- #
# Connections
# --------------------------------------------------------------------------- #
DEFAULT_DATABASE_URL = (
    "postgresql://eudr:eudr_dev_password@localhost:5432/eudr_risk"
)

#: PostGIS connection string. In Docker this points at the ``db`` service.
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

#: Google Earth Engine Cloud project used by the offline pipeline.
EE_PROJECT = os.getenv("EE_PROJECT", "eudr-forest-risk")


# --------------------------------------------------------------------------- #
# EUDR reference layers
# --------------------------------------------------------------------------- #
#: JRC Global Forest Cover 2020, the EUDR cutoff-date reference layer.
JRC_GFC2020 = "JRC/GFC2020/V3"

#: UMD/Hansen Global Forest Change, annual forest loss.
HANSEN_GFC = "UMD/hansen/global_forest_change_2025_v1_13"

#: Hansen ``lossyear`` encodes 2021 as 21, the first year after the EUDR
#: cutoff date of 31 December 2020.
LOSSYEAR_MIN = 21


# --------------------------------------------------------------------------- #
# Parcel derivation (phase 1)
# --------------------------------------------------------------------------- #
#: Cocoa-probability threshold used for both AOI clustering and vectorization.
COCOA_PROB_THRESHOLD = 0.3

#: Parcel size bounds in 10 m pixels: 50 px = 0.5 ha, 8500 px = 85 ha
#: (~99th percentile of the observed size distribution).
MIN_PARCEL_PIXELS = 50
MAX_PARCEL_PIXELS = 8500


# --------------------------------------------------------------------------- #
# Feature engineering (phase 4)
# --------------------------------------------------------------------------- #
#: Native resolution used for all reductions, in metres per pixel.
SCALE = 10

#: fastDistanceTransform search radius, in pixels. Doubles as the saturation
#: cap: parcels farther than NEIGHBORHOOD * SCALE metres are clamped.
NEIGHBORHOOD = 256

#: Distance-to-deforestation cap in metres (2,560 m).
DIST_CAP_M = NEIGHBORHOOD * SCALE

#: Neighbourhood ring radii in metres (each ring excludes the parcel itself).
BUFFERS_M = [200, 500, 1000]

#: Batch size for Earth Engine reduceRegions calls (keeps payloads under the
#: 10 MB interactive limit).
BATCH_SIZE = 200


# --------------------------------------------------------------------------- #
# Risk model (phase 4)
# --------------------------------------------------------------------------- #
#: Median ``defo_pct`` among affected parcels, the MEDIUM/HIGH boundary.
DEFO_MEDIAN_AFFECTED = 5.3755

#: Seed used for every model, split and shuffle in the pipeline.
RANDOM_STATE = 42

#: Number of folds for stratified cross-validation.
CV_FOLDS = 5
