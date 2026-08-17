"""Shared Earth Engine helpers for the offline pipeline.

Centralises the EUDR reference-layer definition that phases 1, 2 and 4 all
depend on, so the deforestation mask is defined exactly once.

Importing this module does not contact Earth Engine; call :func:`init` first.
"""

import ee

from src.config import (
    BATCH_SIZE,
    EE_PROJECT,
    HANSEN_GFC,
    JRC_GFC2020,
    LOSSYEAR_MIN,
    SCALE,
)

__all__ = ["init", "deforestation_mask", "defo_area_bands", "iter_batches",
           "BATCH_SIZE", "SCALE"]


def init() -> None:
    """Initialise Earth Engine with the configured Cloud project."""
    ee.Initialize(project=EE_PROJECT)


def deforestation_mask() -> ee.Image:
    """Post-2020 deforestation under the EUDR definition.

    A pixel counts as deforested when Hansen GFC records loss in 2021 or later
    (``lossyear >= 21``) **and** JRC GFC2020 classified it as forest at the
    31 December 2020 cutoff date.
    """
    forest2020 = ee.Image(JRC_GFC2020).select("Map")
    lossyear = ee.Image(HANSEN_GFC).select("lossyear")
    return lossyear.gte(LOSSYEAR_MIN).And(forest2020.eq(1)).rename("defo")


def defo_area_bands() -> ee.Image:
    """Two-band image of deforested and total area, in m², for sum reducers."""
    pixel_area = ee.Image.pixelArea()
    return (deforestation_mask().multiply(pixel_area).rename("defo_m2")
            .addBands(pixel_area.rename("total_m2")))


def iter_batches(gdf, batch_size: int = BATCH_SIZE):
    """Yield ``(start, chunk)`` slices of a GeoDataFrame.

    Earth Engine's interactive endpoints cap payloads at 10 MB, so parcels are
    processed in batches rather than as one 4,170-feature collection.
    """
    for start in range(0, len(gdf), batch_size):
        yield start, gdf.iloc[start:start + batch_size]
