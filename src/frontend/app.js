/* ============================================================
   EUDR Forest Risk Assessment — frontend logic (vanilla JS)
   ============================================================ */

// Set by config.js (window.API_BASE); falls back to localhost for local dev.
const API_BASE = (typeof window !== "undefined" && window.API_BASE)
  || "http://localhost:8000";

// Risk-class presentation config (color, human label, map stroke weight).
const RISK = {
  LOW:    { color: "#5DCAA5", label: "Compliant",     weight: 2 },
  MEDIUM: { color: "#F0997B", label: "Needs review",  weight: 3 },
  HIGH:   { color: "#E24B4A", label: "Non-compliant", weight: 3 },
};
const SELECTED_COLOR = "#7F77DD";
const AOI_CENTER = [8.52, -76.44];
const PAGE_SIZE = 50;

// ---- App state ----
let map;
let geoLayer;                       // L.geoJSON feature group on the map
const layersById = {};              // farm_id -> leaflet layer
let allFeatures = [];               // every parcel feature
let activeFilters = new Set(["LOW", "MEDIUM", "HIGH"]);
let selectedId = null;
let listCursor = 0;                 // how many filtered rows are rendered

// ---- Small helpers ----
const fmt = (n) => Number(n).toLocaleString("en-US");
const $ = (sel) => document.querySelector(sel);

async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

function riskCfg(rc) { return RISK[rc] || RISK.LOW; }

// ============================================================
// Map setup
// ============================================================
function initMap() {
  // Zoom control placed on the right edge so it never sits behind the
  // top-left Parcels panel (positioned vertically via CSS).
  map = L.map("map", { zoomControl: false, attributionControl: true })
    .setView(AOI_CENTER, 11);
  L.control.zoom({ position: "topright" }).addTo(map);

  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/" +
    "World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 19,
      attribution:
        "Imagery © Esri, Maxar, Earthstar Geographics — EUDR demo",
    }
  ).addTo(map);
}

function baseStyle(feature) {
  const cfg = riskCfg(feature.properties.risk_class);
  return {
    color: cfg.color,
    weight: cfg.weight,
    opacity: 0.9,
    fillColor: cfg.color,
    fillOpacity: 0.35,
  };
}

function selectedStyle() {
  return { color: SELECTED_COLOR, weight: 3, opacity: 1, fillOpacity: 0.45 };
}

// ============================================================
// Selection
// ============================================================
function selectParcel(farmId, { fly = true } = {}) {
  // Reset previously selected polygon.
  if (selectedId !== null && layersById[selectedId]) {
    geoLayer.resetStyle(layersById[selectedId]);
  }
  selectedId = farmId;

  const layer = layersById[farmId];
  if (layer) {
    layer.setStyle(selectedStyle());
    layer.bringToFront();
    if (fly) {
      map.flyToBounds(layer.getBounds(), { maxZoom: 16, padding: [60, 60] });
    }
  }

  const feature = allFeatures.find((f) => f.properties.farm_id === farmId);
  if (feature) openDetail(feature.properties);

  // Sync row highlight in both lists.
  document.querySelectorAll(".parcel-row, .warn-row").forEach((el) => {
    el.classList.toggle("is-selected", Number(el.dataset.id) === farmId);
  });
}

// ============================================================
// Detail panel
// ============================================================
function openDetail(p) {
  const cfg = riskCfg(p.risk_class);
  $("#detail-title").textContent = `Parcel ${p.farm_id}`;

  const badge = $("#detail-badge");
  badge.className = `badge ${p.risk_class}`;
  badge.innerHTML =
    `<span class="dot" style="--c:${cfg.color}"></span>${cfg.label}`;

  $("#detail-area").textContent = `${fmt((p.area_ha ?? 0).toFixed(2))} ha`;
  $("#detail-defo").textContent = `${(p.defo_pct ?? 0).toFixed(2)}%`;

  const score = p.risk_score ?? 0;
  $("#detail-score-val").textContent = score.toFixed(3);
  $("#detail-score-bar").style.width = `${Math.max(score * 100, 1.5)}%`;

  $("#panel-detail").classList.remove("hidden");
}

function closeDetail() {
  $("#panel-detail").classList.add("hidden");
  if (selectedId !== null && layersById[selectedId]) {
    geoLayer.resetStyle(layersById[selectedId]);
  }
  document.querySelectorAll(".is-selected")
    .forEach((el) => el.classList.remove("is-selected"));
  selectedId = null;
}

// ============================================================
// Parcels: load + render map layer + list
// ============================================================
async function loadFarms() {
  const fc = await getJSON("/farms?limit=10000");
  allFeatures = fc.features;

  geoLayer = L.geoJSON(fc, {
    style: baseStyle,
    onEachFeature: (feature, layer) => {
      const id = feature.properties.farm_id;
      layersById[id] = layer;
      layer.on("click", () => selectParcel(id, { fly: true }));
    },
  }).addTo(map);

  renderList(true);
}

function filteredFeatures() {
  return allFeatures
    .filter((f) => activeFilters.has(f.properties.risk_class))
    .sort((a, b) => a.properties.farm_id - b.properties.farm_id);
}

function rowHTML(p) {
  const cfg = riskCfg(p.risk_class);
  return `
    <div class="parcel-row${p.farm_id === selectedId ? " is-selected" : ""}"
         data-id="${p.farm_id}">
      <div>
        <div class="pid">Parcel ${p.farm_id}</div>
        <div class="pmeta">${(p.area_ha ?? 0).toFixed(2)} ha</div>
      </div>
      <span class="badge ${p.risk_class}">
        <span class="dot" style="--c:${cfg.color}"></span>${cfg.label}
      </span>
    </div>`;
}

function renderList(reset) {
  const list = $("#parcel-list");
  const feats = filteredFeatures();

  if (reset) {
    list.innerHTML = "";
    listCursor = 0;
  }
  if (feats.length === 0) {
    list.innerHTML = '<div class="empty">No parcels match these filters.</div>';
    return;
  }

  const slice = feats.slice(listCursor, listCursor + PAGE_SIZE);
  list.insertAdjacentHTML(
    "beforeend",
    slice.map((f) => rowHTML(f.properties)).join("")
  );
  listCursor += slice.length;

  // Wire freshly added rows.
  list.querySelectorAll(".parcel-row:not([data-wired])").forEach((row) => {
    row.dataset.wired = "1";
    row.addEventListener("click", () =>
      selectParcel(Number(row.dataset.id), { fly: true })
    );
  });
}

// Infinite scroll: load the next page near the bottom.
function onListScroll(e) {
  const el = e.target;
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
    if (listCursor < filteredFeatures().length) renderList(false);
  }
}

// ============================================================
// Filters
// ============================================================
function applyFilters() {
  for (const f of allFeatures) {
    const layer = layersById[f.properties.farm_id];
    if (!layer) continue;
    const show = activeFilters.has(f.properties.risk_class);
    if (show && !geoLayer.hasLayer(layer)) geoLayer.addLayer(layer);
    if (!show && geoLayer.hasLayer(layer)) geoLayer.removeLayer(layer);
  }
  renderList(true);
}

function initFilterChips() {
  const chips = document.querySelectorAll("#filter-chips .chip");
  const classChips = ["LOW", "MEDIUM", "HIGH"];

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const filter = chip.dataset.filter;

      if (filter === "ALL") {
        activeFilters = new Set(classChips);
        chips.forEach((c) => c.classList.add("is-active"));
      } else {
        chip.classList.toggle("is-active");
        if (chip.classList.contains("is-active")) activeFilters.add(filter);
        else activeFilters.delete(filter);

        // "All" is active only when every class is on.
        const allOn = classChips.every((c) => activeFilters.has(c));
        document.querySelector('[data-filter="ALL"]')
          .classList.toggle("is-active", allOn);
      }
      applyFilters();
    });
  });
}

// ============================================================
// Stats panel
// ============================================================
async function loadStats() {
  const s = await getJSON("/stats");

  // Parcels-panel header summary.
  $("#parcels-summary").classList.remove("skeleton-text");
  $("#parcels-summary").textContent =
    `${fmt(s.total_parcels)} parcels · ${fmt(Math.round(s.total_area_ha))} ha`;

  // Order tiles HIGH → MEDIUM → LOW for visual priority.
  const order = ["HIGH", "MEDIUM", "LOW"];
  const byClass = Object.fromEntries(
    s.by_risk_class.map((r) => [r.risk_class, r])
  );

  $("#stats-tiles").innerHTML = order
    .filter((rc) => byClass[rc])
    .map((rc) => {
      const cfg = riskCfg(rc);
      return `
        <div class="tile">
          <span class="dot" style="--c:${cfg.color}"></span>
          <span class="tnum">${fmt(byClass[rc].count)}</span>
          <span class="tlabel">${cfg.label}</span>
        </div>`;
    })
    .join("");

  $("#stats-area").textContent = `${fmt(Math.round(s.total_area_ha))} ha`;
}

// ============================================================
// Early-warning panel
// ============================================================
async function loadEarlyWarning() {
  const fc = await getJSON("/early-warning?limit=15");
  const list = $("#warning-list");

  if (!fc.features.length) {
    list.innerHTML = '<div class="empty">No early-warning parcels.</div>';
    return;
  }

  const header =
    `<div class="warn-head"><span>Parcel</span><span>Area</span>` +
    `<span>Risk score</span><span></span></div>`;

  const rows = fc.features
    .map((f) => {
      const p = f.properties;
      const score = p.risk_score ?? 0;
      return `
        <div class="warn-row${p.farm_id === selectedId ? " is-selected" : ""}"
             data-id="${p.farm_id}">
          <span class="pid">Parcel ${p.farm_id}</span>
          <span class="wmeta">${(p.area_ha ?? 0).toFixed(2)} ha</span>
          <span class="bar"><span class="bar-fill"
            style="width:${Math.max(score * 100, 2)}%"></span></span>
          <span class="wscore">${score.toFixed(3)}</span>
        </div>`;
    })
    .join("");

  list.innerHTML = header + rows;
  list.querySelectorAll(".warn-row").forEach((row) => {
    row.addEventListener("click", () =>
      selectParcel(Number(row.dataset.id), { fly: true })
    );
  });
}

// ============================================================
// Wiring + boot
// ============================================================
function initUI() {
  $("#detail-close").addEventListener("click", closeDetail);
  $("#parcel-list").addEventListener("scroll", onListScroll);
  $("#warning-toggle").addEventListener("click", () =>
    $("#panel-warning").classList.toggle("collapsed")
  );
  $("#parcels-toggle").addEventListener("click", () =>
    $("#panel-parcels").classList.toggle("collapsed")
  );
  // Dismiss the intro modal; the app returns to its normal look.
  $("#intro-close").addEventListener("click", () =>
    $("#intro").classList.add("hidden")
  );
  initFilterChips();
}

async function boot() {
  initMap();
  initUI();
  // Fire requests in parallel; render each panel as its data arrives.
  loadStats().catch((e) => console.error(e));
  loadEarlyWarning().catch((e) => console.error(e));
  try {
    await loadFarms();
  } catch (e) {
    console.error(e);
    $("#parcel-list").innerHTML =
      '<div class="empty">Could not reach the API on ' +
      `${API_BASE}. Is it running?</div>`;
  }
}

document.addEventListener("DOMContentLoaded", boot);
