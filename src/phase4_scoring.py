import ee, geemap, geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

ee.Initialize(project='eudr-forest-risk')
ENGINE_URL = "postgresql://eudr:eudr_dev_password@localhost:5432/eudr_risk"
engine = create_engine(ENGINE_URL)

# --- Step 1: compute neighborhood_defo_pct (200m ring around each parcel) ---
gdf = gpd.read_file('data/farms.geojson')

forest2020 = ee.Image('JRC/GFC2020/V3').select('Map')
hansen = ee.Image('UMD/hansen/global_forest_change_2025_v1_13')
lossyear = hansen.select('lossyear')
defo_post2020 = lossyear.gte(21).And(forest2020.eq(1)).rename('defo')
pixel_area = ee.Image.pixelArea()
combined = (defo_post2020.multiply(pixel_area).rename('defo_m2')
            .addBands(ee.Image.pixelArea().rename('total_m2')))

BUFFER_M = 200
BATCH_SIZE = 200
results = []

for start in range(0, len(gdf), BATCH_SIZE):
    chunk = gdf.iloc[start:start + BATCH_SIZE]
    farms_chunk = geemap.geopandas_to_ee(chunk)

    # Ring = buffer(200m) minus the parcel itself
    rings = farms_chunk.map(lambda f: f.setGeometry(
        f.geometry().buffer(BUFFER_M).difference(f.geometry())))

    stats = combined.reduceRegions(
        collection=rings, reducer=ee.Reducer.sum(), scale=10, tileScale=4)
    stats_no_geom = stats.map(lambda f: ee.Feature(None, f.toDictionary()))
    results.append(geemap.ee_to_df(stats_no_geom))
    print(f'Neighborhood stats: {min(start + BATCH_SIZE, len(gdf))}/{len(gdf)}')

neighborhood = pd.concat(results, ignore_index=True)
neighborhood['neighborhood_defo_pct'] = (
    neighborhood['defo_m2'] / neighborhood['total_m2'] * 100).round(3)
neighborhood = neighborhood[['farm_id', 'neighborhood_defo_pct']]
neighborhood.to_csv('data/farms_neighborhood.csv', index=False)
print(neighborhood['neighborhood_defo_pct'].describe())

# --- Step 2: build dataset (label from OWN defo_pct, feature from neighborhood) ---
own = pd.read_sql("""
    SELECT f.farm_id, f.area_ha, a.defo_pct
    FROM farms f JOIN assessments a ON f.farm_id = a.farm_id
""", engine)

df = own.merge(neighborhood, on='farm_id')

DEFO_MEDIAN_AFFECTED = 5.3755
def classify(pct):
    if pct == 0:
        return "LOW"
    elif pct <= DEFO_MEDIAN_AFFECTED:
        return "MEDIUM"
    else:
        return "HIGH"

df['risk_class'] = df['defo_pct'].apply(classify)

# --- Step 3: train model WITHOUT the parcel's own defo_pct as a feature ---
X = df[['area_ha', 'neighborhood_defo_pct']]
y = df['risk_class']

Xtr, Xte, ytr, yte = train_test_split(
    X, y, stratify=y, test_size=0.25, random_state=42)

clf = RandomForestClassifier(
    n_estimators=300, class_weight='balanced', random_state=42)
clf.fit(Xtr, ytr)

print(classification_report(yte, clf.predict(Xte)))
print(confusion_matrix(yte, clf.predict(Xte)))

# --- Step 4: risk_score = P(HIGH) for ALL 4,170 parcels ---
proba = clf.predict_proba(X)
high_idx = list(clf.classes_).index('HIGH')
df['risk_score'] = proba[:, high_idx].round(4)

# The actual deliverable: LOW parcels with elevated risk_score
# (currently "clean" but surrounded by recent deforestation)
early_warning = df[df['risk_class'] == 'LOW'].sort_values(
    'risk_score', ascending=False).head(10)
print("\nTop 10 early-warning candidates (LOW today, elevated risk_score):")
print(early_warning[['farm_id', 'area_ha', 'neighborhood_defo_pct', 'risk_score']])

# --- Step 5: update assessments table ---
with engine.begin() as conn:
    for _, row in df.iterrows():
        conn.execute(text("""
            UPDATE assessments
            SET risk_score = :score, risk_class = :cls
            WHERE farm_id = :fid
        """), {"score": float(row["risk_score"]),
               "cls": row["risk_class"], "fid": int(row["farm_id"])})

print("Assessments with neighborhood-based risk_score.")