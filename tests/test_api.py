"""API endpoint tests.

The database dependency is replaced by an in-memory fake (see conftest.py), so
these run anywhere — no PostGIS, no Earth Engine, no network.
"""

import json

from src.api.main import _row_to_feature


class TestRoot:
    def test_returns_api_metadata(self, client):
        body = client.get("/").json()
        assert "EUDR" in body["name"]
        assert body["docs"] == "/docs"
        assert "GET /early-warning" in body["endpoints"]

    def test_openapi_documents_every_endpoint(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert {"/", "/farms", "/farms/{farm_id}", "/stats",
                "/early-warning"} <= set(paths)


class TestRowToFeature:
    """The row -> GeoJSON adapter, tested directly as a unit."""

    def test_builds_feature_from_row(self):
        row = {"farm_id": 42, "area_ha": 1.5, "defo_pct": 0.0,
               "risk_score": 0.12, "risk_class": "LOW",
               "geometry": json.dumps({"type": "Polygon", "coordinates": []})}

        feature = _row_to_feature(row)

        assert feature.type == "Feature"
        assert feature.properties.farm_id == 42
        assert feature.geometry["type"] == "Polygon"

    def test_parses_geometry_json_string(self):
        # PostGIS ST_AsGeoJSON returns text; it must arrive as a dict.
        row = {"farm_id": 1, "area_ha": 1.0, "defo_pct": 0.0, "risk_score": 0.0,
               "risk_class": "LOW",
               "geometry": '{"type":"Point","coordinates":[-76.4,8.5]}'}

        assert _row_to_feature(row).geometry == {
            "type": "Point", "coordinates": [-76.4, 8.5]}


class TestListFarms:
    def test_returns_feature_collection(self, client):
        body = client.get("/farms").json()
        assert body["type"] == "FeatureCollection"
        assert len(body["features"]) == 4

    def test_every_feature_is_valid_geojson(self, client):
        for feature in client.get("/farms").json()["features"]:
            assert feature["type"] == "Feature"
            assert feature["geometry"]["type"] == "Polygon"
            assert "farm_id" in feature["properties"]

    def test_filters_by_risk_class(self, client):
        body = client.get("/farms", params={"risk_class": "HIGH"}).json()
        classes = {f["properties"]["risk_class"] for f in body["features"]}
        assert classes == {"HIGH"}

    def test_filters_by_min_risk_score(self, client):
        body = client.get("/farms", params={"min_risk_score": 0.5}).json()
        assert all(f["properties"]["risk_score"] >= 0.5
                   for f in body["features"])

    def test_rejects_invalid_risk_class(self, client):
        assert client.get("/farms", params={"risk_class": "NOPE"}).status_code == 422

    def test_rejects_out_of_range_score(self, client):
        assert client.get("/farms", params={"min_risk_score": 1.5}).status_code == 422

    def test_pagination_advances(self, client):
        page1 = client.get("/farms", params={"limit": 2, "offset": 0}).json()
        page2 = client.get("/farms", params={"limit": 2, "offset": 2}).json()

        ids1 = [f["properties"]["farm_id"] for f in page1["features"]]
        ids2 = [f["properties"]["farm_id"] for f in page2["features"]]

        assert len(ids1) == len(ids2) == 2
        assert not set(ids1) & set(ids2)

    def test_rejects_zero_limit(self, client):
        assert client.get("/farms", params={"limit": 0}).status_code == 422


class TestGetFarm:
    def test_returns_single_feature(self, client):
        body = client.get("/farms/3").json()
        assert body["type"] == "Feature"
        assert body["properties"]["farm_id"] == 3
        assert body["properties"]["risk_class"] == "MEDIUM"

    def test_unknown_farm_returns_404(self, client):
        response = client.get("/farms/999999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_non_integer_id_returns_422(self, client):
        assert client.get("/farms/abc").status_code == 422


class TestStats:
    def test_reports_totals(self, client):
        body = client.get("/stats").json()
        assert body["total_parcels"] == 4
        assert body["total_area_ha"] == 17.5

    def test_groups_every_risk_class(self, client):
        body = client.get("/stats").json()
        counts = {r["risk_class"]: r["count"] for r in body["by_risk_class"]}
        assert counts == {"LOW": 2, "MEDIUM": 1, "HIGH": 1}

    def test_scores_stay_within_unit_interval(self, client):
        for row in client.get("/stats").json()["by_risk_class"]:
            assert 0.0 <= row["min_risk_score"] <= row["max_risk_score"] <= 1.0


class TestEarlyWarning:
    def test_returns_only_low_parcels(self, client):
        body = client.get("/early-warning").json()
        assert {f["properties"]["risk_class"] for f in body["features"]} == {"LOW"}

    def test_orders_by_risk_score_descending(self, client):
        scores = [f["properties"]["risk_score"]
                  for f in client.get("/early-warning").json()["features"]]
        assert scores == sorted(scores, reverse=True)

    def test_highest_scoring_clean_parcel_comes_first(self, client):
        body = client.get("/early-warning").json()
        top = body["features"][0]["properties"]
        assert top["farm_id"] == 2          # 0.29, the highest LOW score
        assert top["defo_pct"] == 0.0       # clean today

    def test_respects_limit(self, client):
        body = client.get("/early-warning", params={"limit": 1}).json()
        assert len(body["features"]) == 1


class TestCors:
    def test_allows_cross_origin_frontend(self, client):
        # The dashboard is served from a different origin (:8080). Because the
        # middleware is configured with allow_credentials, Starlette echoes the
        # requesting origin back instead of a bare "*".
        origin = "http://localhost:8080"
        response = client.get("/stats", headers={"Origin": origin})
        assert response.headers["access-control-allow-origin"] == origin

    def test_preflight_is_answered(self, client):
        response = client.options("/farms", headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "GET",
        })
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
