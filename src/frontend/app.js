/* ============================================================
   EUDR Forest Risk Assessment: frontend logic (vanilla JS)
   ============================================================ */

// Set by config.js. Two modes:
//  - live API (default): window.API_BASE points at a running FastAPI
//    backend (falls back to localhost for local dev).
//  - static (window.API_STATIC = true): no backend at all. The GitHub Pages
//    deploy runs in this mode by default (see deploy-pages.yml), serving
//    the precomputed JSON files in data/ built by
//    scripts/build_static_data.py. The dashboard only ever reads farms in
//    bulk and filters client-side, so a snapshot is all it needs.
const API_BASE = (typeof window !== "undefined" && window.API_BASE)
  || "http://localhost:8000";
const API_STATIC = typeof window !== "undefined" && window.API_STATIC === true;
const STATIC_DATA_BASE =
  (typeof window !== "undefined" && window.STATIC_DATA_BASE) || "data";

// ============================================================
// i18n: UI strings in English and Spanish ({name} = placeholder)
// ============================================================
const I18N = {
  en: {
    "app.title": "EUDR Forest Risk Assessment",
    "lang.switch": "Cambiar a español",
    "intro.title": "Forest Risk Assessment",
    "intro.lead": "An interactive view of EUDR deforestation risk for " +
      "4,170 cocoa parcels. Each parcel is scored and classified by how " +
      "exposed it is to recent forest loss.",
    "intro.browse": "<b>Browse &amp; filter</b> parcels in the top-left " +
      "panel by compliance status: compliant, needs review, or non-compliant.",
    "intro.select": "<b>Select a parcel</b> on the map or in any list to " +
      "inspect its area, deforestation and risk score.",
    "intro.warning": "<b>Early warning</b> (bottom) flags compliant parcels " +
      "with elevated modeled risk, the priorities for review.",
    "intro.overview": "<b>Overview</b> (bottom-right) summarizes counts and " +
      "total area.",
    "intro.note": "The risk score is a prioritization aid based on spatial " +
      "deforestation pressure, not an EUDR compliance verdict.",
    "intro.cta": "Explore the map",
    "common.loading": "Loading…",
    "common.close": "Close",
    "parcels.title": "Parcels",
    "parcels.toggle": "Toggle list",
    "parcels.summary": "{count} parcels · {area} ha",
    "parcels.empty": "No parcels match these filters.",
    "parcels.apiError": "Could not reach the API on {url}. Is it running?",
    "parcel.name": "Parcel {id}",
    "filter.all": "All",
    "risk.LOW": "Compliant",
    "risk.MEDIUM": "Needs review",
    "risk.HIGH": "Non-compliant",
    "metric.area": "Area",
    "metric.deforested": "Deforested",
    "metric.score": "Risk score",
    "detail.note": "Risk score reflects proximity to recent forest loss and " +
      "surrounding deforestation pressure, not an EUDR compliance verdict.",
    "warning.title": "Early warning",
    "warning.subtitle": "Compliant parcels with elevated modeled risk, " +
      "prioritize for review.",
    "warning.toggle": "Collapse",
    "warning.colParcel": "Parcel",
    "warning.empty": "No early-warning parcels.",
    "stats.title": "Overview",
    "stats.totalArea": "Total area",
  },
  es: {
    "app.title": "Evaluación de riesgo forestal EUDR",
    "lang.switch": "Switch to English",
    "intro.title": "Evaluación de riesgo forestal",
    "intro.lead": "Una vista interactiva del riesgo de deforestación EUDR " +
      "para 4.170 parcelas de cacao. Cada parcela recibe una puntuación y se " +
      "clasifica según su exposición a la pérdida forestal reciente.",
    "intro.browse": "<b>Explora y filtra</b> las parcelas en el panel " +
      "superior izquierdo por estado de cumplimiento: conforme, requiere " +
      "revisión o no conforme.",
    "intro.select": "<b>Selecciona una parcela</b> en el mapa o en cualquier " +
      "lista para consultar su área, deforestación y puntuación de riesgo.",
    "intro.warning": "<b>Alerta temprana</b> (abajo) señala las parcelas " +
      "conformes con riesgo modelado elevado, las prioridades de revisión.",
    "intro.overview": "<b>Resumen</b> (abajo a la derecha) muestra los " +
      "conteos y el área total.",
    "intro.note": "La puntuación de riesgo es una ayuda para priorizar, " +
      "basada en la presión espacial de deforestación, no un veredicto de " +
      "cumplimiento EUDR.",
    "intro.cta": "Explorar el mapa",
    "common.loading": "Cargando…",
    "common.close": "Cerrar",
    "parcels.title": "Parcelas",
    "parcels.toggle": "Mostrar u ocultar lista",
    "parcels.summary": "{count} parcelas · {area} ha",
    "parcels.empty": "Ninguna parcela coincide con estos filtros.",
    "parcels.apiError": "No se pudo conectar con la API en {url}. " +
      "¿Está en ejecución?",
    "parcel.name": "Parcela {id}",
    "filter.all": "Todas",
    "risk.LOW": "Conforme",
    "risk.MEDIUM": "Requiere revisión",
    "risk.HIGH": "No conforme",
    "metric.area": "Área",
    "metric.deforested": "Deforestado",
    "metric.score": "Puntuación de riesgo",
    "detail.note": "La puntuación de riesgo refleja la proximidad a pérdida " +
      "forestal reciente y la presión de deforestación circundante, no un " +
      "veredicto de cumplimiento EUDR.",
    "warning.title": "Alerta temprana",
    "warning.subtitle": "Parcelas conformes con riesgo modelado elevado, " +
      "priorizar para revisión.",
    "warning.toggle": "Contraer",
    "warning.colParcel": "Parcela",
    "warning.empty": "No hay parcelas en alerta temprana.",
    "stats.title": "Resumen",
    "stats.totalArea": "Área total",
  },
};
const LOCALES = { en: "en-US", es: "es-CO" };
const LANG_KEY = "eudr-lang";

// Saved choice first, then the browser language; English otherwise.
function detectLang() {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved in I18N) return saved;
  } catch (e) { /* storage blocked: fall through */ }
  const nav = (navigator.languages || [navigator.language || ""])[0] || "";
  return nav.toLowerCase().startsWith("es") ? "es" : "en";
}

let lang = detectLang();

function t(key, vars = {}) {
  const str = I18N[lang][key] ?? I18N.en[key] ?? key;
  return str.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
}

// Risk-class presentation config (color, label key, map stroke weight).
const RISK = {
  LOW:    { color: "#5DCAA5", key: "risk.LOW",    weight: 2 },
  MEDIUM: { color: "#F0997B", key: "risk.MEDIUM", weight: 3 },
  HIGH:   { color: "#E24B4A", key: "risk.HIGH",   weight: 3 },
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
let statsData = null;               // last /stats payload (re-render on lang)
let warningData = null;             // last /early-warning payload
let farmsError = false;             // /farms failed: list shows the error

// ---- Small helpers ----
// Locale-aware number with a fixed number of decimals (default: integer).
const fmt = (n, digits = 0) => Number(n).toLocaleString(LOCALES[lang], {
  minimumFractionDigits: digits,
  maximumFractionDigits: digits,
});
const $ = (sel) => document.querySelector(sel);

// Maps a REST-style call (path + query string) used elsewhere in this file
// to the precomputed static file that serves the same data in static mode
// (see scripts/build_static_data.py). The three calls below are the only
// ones the dashboard ever makes.
function staticURL(path) {
  if (path.startsWith("/farms?")) return `${STATIC_DATA_BASE}/farms.json`;
  if (path.startsWith("/stats")) return `${STATIC_DATA_BASE}/stats.json`;
  if (path.startsWith("/early-warning")) {
    return `${STATIC_DATA_BASE}/early-warning.json`;
  }
  throw new Error(`No static file mapped for ${path}`);
}

async function getJSON(path) {
  const url = API_STATIC ? staticURL(path) : `${API_BASE}${path}`;
  const res = await fetch(url);
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
        "Imagery © Esri, Maxar, Earthstar Geographics (EUDR demo)",
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
  $("#detail-title").textContent = t("parcel.name", { id: p.farm_id });

  const badge = $("#detail-badge");
  badge.className = `badge ${p.risk_class}`;
  badge.innerHTML =
    `<span class="dot" style="--c:${cfg.color}"></span>${t(cfg.key)}`;

  $("#detail-area").textContent = `${fmt(p.area_ha ?? 0, 2)} ha`;
  $("#detail-defo").textContent = `${fmt(p.defo_pct ?? 0, 2)}%`;

  const score = p.risk_score ?? 0;
  $("#detail-score-val").textContent = fmt(score, 3);
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
        <div class="pid">${t("parcel.name", { id: p.farm_id })}</div>
        <div class="pmeta">${fmt(p.area_ha ?? 0, 2)} ha</div>
      </div>
      <span class="badge ${p.risk_class}">
        <span class="dot" style="--c:${cfg.color}"></span>${t(cfg.key)}
      </span>
    </div>`;
}

// `count` lets a re-render (e.g. language switch) keep every loaded page.
function renderList(reset, count = PAGE_SIZE) {
  const list = $("#parcel-list");
  const feats = filteredFeatures();

  if (reset) {
    list.innerHTML = "";
    listCursor = 0;
  }
  if (feats.length === 0) {
    list.innerHTML = `<div class="empty">${t("parcels.empty")}</div>`;
    return;
  }

  const slice = feats.slice(listCursor, listCursor + count);
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
  statsData = await getJSON("/stats");
  renderStats();
}

function renderStats() {
  const s = statsData;

  // Parcels-panel header summary (drop the static "Loading…" i18n key so a
  // language switch doesn't bring it back).
  const summary = $("#parcels-summary");
  summary.classList.remove("skeleton-text");
  summary.removeAttribute("data-i18n");
  summary.textContent = t("parcels.summary", {
    count: fmt(s.total_parcels),
    area: fmt(Math.round(s.total_area_ha)),
  });

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
          <span class="tlabel">${t(cfg.key)}</span>
        </div>`;
    })
    .join("");

  $("#stats-area").textContent = `${fmt(Math.round(s.total_area_ha))} ha`;
}

// ============================================================
// Early-warning panel
// ============================================================
const EARLY_WARNING_LIMIT = 15;

async function loadEarlyWarning() {
  const fc = await getJSON(`/early-warning?limit=${EARLY_WARNING_LIMIT}`);
  // In dynamic mode the API already applies the limit; in static mode the
  // precomputed file carries extra headroom (see build_static_data.py), so
  // trim it here to match.
  warningData = { ...fc, features: fc.features.slice(0, EARLY_WARNING_LIMIT) };
  renderEarlyWarning();
}

function renderEarlyWarning() {
  const fc = warningData;
  const list = $("#warning-list");

  if (!fc.features.length) {
    list.innerHTML = `<div class="empty">${t("warning.empty")}</div>`;
    return;
  }

  const header =
    `<div class="warn-head"><span>${t("warning.colParcel")}</span>` +
    `<span>${t("metric.area")}</span>` +
    `<span>${t("metric.score")}</span><span></span></div>`;

  const rows = fc.features
    .map((f) => {
      const p = f.properties;
      const score = p.risk_score ?? 0;
      return `
        <div class="warn-row${p.farm_id === selectedId ? " is-selected" : ""}"
             data-id="${p.farm_id}">
          <span class="pid">${t("parcel.name", { id: p.farm_id })}</span>
          <span class="wmeta">${fmt(p.area_ha ?? 0, 2)} ha</span>
          <span class="bar"><span class="bar-fill"
            style="width:${Math.max(score * 100, 2)}%"></span></span>
          <span class="wscore">${fmt(score, 3)}</span>
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
// Language switch
// ============================================================
function showFarmsError() {
  const url = API_STATIC ? staticURL("/farms?") : API_BASE;
  $("#parcel-list").innerHTML =
    `<div class="empty">${t("parcels.apiError", { url })}</div>`;
}

// Static markup carries data-i18n (text), data-i18n-html (trusted markup
// from I18N) and data-i18n-aria (aria-label) keys.
function applyStaticText() {
  document.documentElement.lang = lang;
  document.title = t("app.title");
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    el.innerHTML = t(el.dataset.i18nHtml);
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    el.setAttribute("aria-label", t(el.dataset.i18nAria));
  });

  const toggle = $("#lang-toggle");
  toggle.setAttribute("aria-label", t("lang.switch"));
  toggle.querySelectorAll(".lang-opt").forEach((opt) => {
    opt.classList.toggle("is-active", opt.dataset.lang === lang);
  });
}

function setLanguage(next) {
  lang = next;
  try { localStorage.setItem(LANG_KEY, lang); } catch (e) { /* ignore */ }
  applyStaticText();

  // Re-render the data-driven panels that have already loaded.
  if (statsData) renderStats();
  if (warningData) renderEarlyWarning();
  if (farmsError) {
    showFarmsError();
  } else if (allFeatures.length) {
    const list = $("#parcel-list");
    const { scrollTop } = list;
    renderList(true, Math.max(listCursor, PAGE_SIZE));
    list.scrollTop = scrollTop;
  }
  if (selectedId !== null) {
    const feature = allFeatures.find((f) => f.properties.farm_id === selectedId);
    if (feature) openDetail(feature.properties);
  }
}

// ============================================================
// Wiring + boot
// ============================================================
function initUI() {
  $("#lang-toggle").addEventListener("click", () =>
    setLanguage(lang === "en" ? "es" : "en")
  );
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
  applyStaticText();
  initMap();
  initUI();
  // Fire requests in parallel; render each panel as its data arrives.
  loadStats().catch((e) => console.error(e));
  loadEarlyWarning().catch((e) => console.error(e));
  try {
    await loadFarms();
  } catch (e) {
    console.error(e);
    farmsError = true;
    showFarmsError();
  }
}

document.addEventListener("DOMContentLoaded", boot);
