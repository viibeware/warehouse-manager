/* UPS zone chart — interactive choropleth.
 * Data: /api/chart (parsed workbook) + static zip3/state geometry.
 * Zones 2–8 wear a single-hue blue ramp (light→dark = near→far; the anchor
 * flips in dark mode so "near" recedes toward the dark surface). Extended
 * zones (AK/HI/PR) wear orange; unavailable service is neutral. */

(async function () {
  "use strict";

  const RAMP = {
    light: ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
    dark:  ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
  };
  // ink that clears each ramp step, for zone chips and the stamp
  const RAMP_INK = {
    light: ["#0b2f5c", "#0b2f5c", "#0b2f5c", "#ffffff", "#ffffff", "#ffffff", "#ffffff"],
    dark:  ["#ffffff", "#ffffff", "#ffffff", "#ffffff", "#0b2f5c", "#0b2f5c", "#0b2f5c"],
  };
  const EXT_COLOR = { light: "#eb6834", dark: "#d95926" };
  const EXT_DAYS = { ground: "3–7 days", two_day: "2 days", nda: "1–2 days" };

  const [origins, chartResp, zip3, statesTopo] = await Promise.all([
    fetch("/api/zonechart/origins").then(r => r.json()),
    fetch("/api/zonechart/chart"),
    fetch("/static/zonechart/geo/zip3.geojson").then(r => r.json()),
    fetch("/static/zonechart/geo/states-10m.json").then(r => r.json()),
  ]);
  if (!chartResp.ok) {
    document.querySelector(".layout").innerHTML =
      `<div class="card" style="grid-column:1/-1;text-align:center;padding:48px 24px">
         <span class="eyebrow">No zone charts on file</span>
         <p style="max-width:46ch;margin:12px auto 0">Sign in to
         <a href="/zonechart/admin">the admin page</a> and run a refresh to download
         the UPS zone chart dataset.</p></div>`;
    return;
  }
  const firstChart = await chartResp.json();

  let chart = firstChart;
  let zones = chart.zones;
  let services = chart.services;
  let activeService = "ground";
  let pinned = null; // prefix currently pinned by click/search

  /* ---------- theme ---------- */
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  function themeName() {
    const forced = document.documentElement.dataset.theme;
    if (forced) return forced;
    return mq.matches ? "dark" : "light";
  }
  const saved = localStorage.getItem("theme");
  if (saved) document.documentElement.dataset.theme = saved;

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const next = themeName() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("theme", next);
    repaint();
  });
  mq.addEventListener("change", () => { if (!localStorage.getItem("theme")) repaint(); });

  /* ---------- geometry ---------- */
  const W = 975, H = 620;
  const svg = d3.select("#map").attr("viewBox", `0 0 ${W} ${H}`);
  const root = svg.append("g");

  const isPR = f => ["006", "007", "008", "009"].includes(f.properties.z);
  const conus = zip3.features.filter(f => !isPR(f));
  const pr = zip3.features.filter(isPR);

  const projection = d3.geoAlbersUsa().fitSize([W, H - 30], { type: "FeatureCollection", features: conus });
  const path = d3.geoPath(projection);

  // Puerto Rico inset, lower right
  const prProj = d3.geoConicEqualArea().parallels([17.8, 18.5]).rotate([66.4, 0])
    .fitExtent([[W - 150, H - 74], [W - 18, H - 14]], { type: "FeatureCollection", features: pr });
  const prPath = d3.geoPath(prProj);

  // nation underlay: ZCTA gaps (unpopulated land) read as neutral, not holes
  const nation = topojson.feature(statesTopo, statesTopo.objects.nation);
  root.append("path")
    .attr("d", path(nation))
    .attr("fill", "var(--nodata)");

  const regions = root.append("g");
  regions.selectAll("path")
    .data(zip3.features)
    .join("path")
    .attr("class", "zip3")
    .attr("d", f => (isPR(f) ? prPath(f) : path(f)))
    .on("pointerenter", onEnter)
    .on("pointermove", onMove)
    .on("pointerleave", onLeave)
    .on("click", onClick);

  const states = topojson.feature(statesTopo, statesTopo.objects.states);
  root.append("path")
    .attr("class", "state-line")
    .attr("d", path(topojson.mesh(statesTopo, statesTopo.objects.states, (a, b) => a !== b)));

  // PR inset frame + label
  root.append("rect").attr("class", "inset-frame")
    .attr("x", W - 155).attr("y", H - 79).attr("width", 142).attr("height", 70).attr("rx", 6);
  root.append("text").attr("class", "inset-label")
    .attr("x", W - 148).attr("y", H - 66).text("PUERTO RICO");

  // origin marker
  const marker = root.append("g").attr("class", "origin-marker");
  marker.append("circle").attr("r", 9).attr("fill", "none")
    .attr("stroke", "currentColor").attr("stroke-width", 1.2).attr("opacity", 0.55);
  marker.append("circle").attr("r", 3.4).attr("fill", "currentColor");
  marker.append("circle").attr("r", 5.6).attr("fill", "none")
    .attr("stroke", "var(--page)").attr("stroke-width", 1.4);

  function placeMarker() {
    const f = zip3.features.find(x => x.properties.z === chart.origin.prefix);
    const xy = f && !isPR(f) ? projection(d3.geoCentroid(f)) : null;
    marker.attr("display", xy ? null : "none");
    if (xy) marker.attr("transform", `translate(${xy[0]},${xy[1]})`);
  }

  /* ---------- zoom ---------- */
  const zoom = d3.zoom().scaleExtent([1, 9])
    .translateExtent([[0, 0], [W, H]])
    .on("zoom", ev => {
      root.attr("transform", ev.transform);
      hint.style.opacity = "0";
      resetBtn.hidden = ev.transform.k < 1.05;
    });
  svg.call(zoom);
  const hint = document.getElementById("map-hint");
  setTimeout(() => { hint.style.opacity = "0"; }, 6000);
  const resetBtn = document.getElementById("reset-view");
  resetBtn.addEventListener("click", () =>
    svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity));

  /* ---------- coloring ---------- */
  function fillFor(prefix, svcId, theme) {
    const entry = zones[prefix];
    if (!entry) return getComputedStyle(document.documentElement).getPropertyValue("--nodata").trim();
    const t = entry[svcId] && entry[svcId].tier;
    if (t === null || t === undefined)
      return getComputedStyle(document.documentElement).getPropertyValue("--nodata").trim();
    if (t === "ext") return EXT_COLOR[theme];
    return RAMP[theme][t - 2];
  }

  function repaint() {
    const theme = themeName();
    regions.selectAll("path")
      .attr("fill", f => fillFor(f.properties.z, activeService, theme));
    renderLegend();
    if (pinned) renderWaybill(pinned.prefix, pinned.zip5);
  }

  /* ---------- service tabs ---------- */
  const tabs = d3.select("#service-tabs");
  tabs.selectAll("button")
    .data(services)
    .join("button")
    .attr("class", "tab")
    .attr("role", "tab")
    .attr("aria-selected", d => String(d.id === activeService))
    .text(d => d.short)
    .on("click", (_, d) => {
      activeService = d.id;
      tabs.selectAll(".tab").attr("aria-selected", t => String(t.id === activeService));
      repaint();
    });

  /* ---------- legend ---------- */
  function etaFor(svcId, tier) {
    if (tier === null || tier === undefined) return null;
    const svc = services.find(s => s.id === svcId);
    if (tier === "ext") return EXT_DAYS[svcId] || svc.flat_days || "varies";
    if (svcId === "ground") return svc.days[tier];
    return svc.flat_days;
  }

  function renderLegend() {
    const theme = themeName();
    const svc = services.find(s => s.id === activeService);
    const items = [2, 3, 4, 5, 6, 7, 8].map(z => ({
      label: `Zone ${z}`,
      days: etaFor(activeService, z),
      color: RAMP[theme][z - 2],
    }));
    items.push({ label: "Extended", days: "AK · HI · PR", color: EXT_COLOR[theme] });
    if (activeService !== "ground")
      items.push({ label: "N/A", days: "not offered", color: "var(--nodata)" });

    d3.select("#legend").selectAll("div")
      .data(items)
      .join("div")
      .attr("class", "legend-item")
      .html(d => `<span class="swatch" style="background:${d.color}"></span>
                  <span class="lg-zone">${d.label}</span>
                  <span class="lg-days">${d.days ?? ""}</span>`);
  }

  /* ---------- tooltip ---------- */
  const tt = document.getElementById("tooltip");
  const stage = document.querySelector(".map-stage");

  function onEnter(ev, f) {
    d3.select(this).classed("hovered", true).raise();
    const prefix = f.properties.z;
    renderTooltip(prefix);
    tt.hidden = false;
    onMove(ev);
    if (!pinned) renderWaybill(prefix, null, true);
  }
  function onMove(ev) {
    const r = stage.getBoundingClientRect();
    const x = ev.clientX - r.left, y = ev.clientY - r.top;
    tt.style.left = Math.min(x + 14, r.width - tt.offsetWidth - 8) + "px";
    tt.style.top = Math.max(y - tt.offsetHeight - 10, 6) + "px";
  }
  function onLeave() {
    d3.select(this).classed("hovered", false);
    tt.hidden = true;
  }
  function onClick(ev, f) {
    const prefix = f.properties.z;
    setPinned(prefix, null);
  }

  function renderTooltip(prefix) {
    const entry = zones[prefix];
    const t = entry && entry[activeService] ? entry[activeService].tier : undefined;
    const svc = services.find(s => s.id === activeService);
    let zoneTxt, etaTxt;
    if (!entry) { zoneTxt = "No zone data"; etaTxt = ""; }
    else if (t === null || t === undefined) { zoneTxt = `${svc.short}: not offered`; etaTxt = ""; }
    else if (t === "ext") { zoneTxt = "Extended zone"; etaTxt = etaFor(activeService, t); }
    else { zoneTxt = `Zone ${t}`; etaTxt = etaFor(activeService, t); }
    tt.innerHTML = `<div class="tt-zip">${prefix}xx</div>
      <div class="tt-zone">${zoneTxt}${etaTxt ? " · ≈ " + etaTxt : ""}</div>`;
  }

  /* ---------- waybill ---------- */
  const wbZip = document.getElementById("wb-zip");
  const wbZone = document.getElementById("wb-zone");
  const wbStamp = document.getElementById("wb-stamp");
  const wbRoute = document.getElementById("wb-route");
  const wbList = document.getElementById("wb-services");
  const wbNote = document.getElementById("wb-note");

  function exceptionTiers(zip5) {
    // AK/HI 5-digit exceptions override ground/nda/two_day zone codes
    return chart.exceptions[zip5] || null;
  }

  function renderWaybill(prefix, zip5, transient) {
    const theme = themeName();
    const entry = zones[prefix];
    const exc = zip5 ? exceptionTiers(zip5) : null;

    wbZip.textContent = zip5 ? zip5 : `${prefix}xx`;
    wbRoute.textContent = `${chart.origin.prefix} → ${prefix}`;

    const t = entry && entry[activeService] ? entry[activeService].tier : undefined;
    if (t === undefined || t === null) {
      wbStamp.dataset.empty = "true";
      wbZone.textContent = "·";
      wbStamp.style.setProperty("--stamp", "var(--kraft)");
    } else {
      wbStamp.dataset.empty = "false";
      wbZone.textContent = t === "ext" ? (exc ? exc[activeService] ?? "EXT" : "EXT") : t;
      wbStamp.style.setProperty("--stamp",
        t === "ext" ? EXT_COLOR[theme] : RAMP[theme][t - 2]);
    }

    const rows = services.map(svc => {
      const st = entry && entry[svc.id] ? entry[svc.id].tier : undefined;
      let eta = etaFor(svc.id, st);
      let zoneChip = "";
      if (st !== null && st !== undefined) {
        const color = st === "ext" ? EXT_COLOR[theme] : RAMP[theme][st - 2];
        const ink = st === "ext" ? "#fff" : RAMP_INK[theme][st - 2];
        const zLabel = st === "ext" ? (exc && exc[svc.id] ? exc[svc.id] : "EXT") : st;
        zoneChip = `<span class="zn" style="background:${color};color:${ink}">${zLabel}</span>`;
      }
      const cls = svc.id === activeService ? "active" : "";
      const etaHtml = eta
        ? `<span class="eta">≈ ${eta}${zoneChip}</span>`
        : `<span class="eta na">Not available</span>`;
      return `<li class="${cls}"><span class="svc">${svc.name}</span>${etaHtml}</li>`;
    });
    wbList.innerHTML = rows.join("");

    wbNote.textContent = transient
      ? "Click the region to pin it."
      : (exc ? "Extended-zone ZIP — exact zones shown from the chart’s AK/HI table."
             : "Estimates are typical business days from pickup.");
  }

  function setPinned(prefix, zip5) {
    pinned = { prefix, zip5 };
    regions.selectAll("path").classed("pinned", f => f.properties.z === prefix);
    renderWaybill(prefix, zip5);
  }

  /* ---------- origin ---------- */
  const originZipEl = document.getElementById("origin-zip");
  const originPlaceEl = document.getElementById("origin-place");
  const originEditor = document.getElementById("origin-editor");
  const originEditBtn = document.getElementById("origin-edit");
  const originInput = document.getElementById("origin-input");
  const originMsg = document.getElementById("origin-msg");

  function updateOriginCard() {
    const o = chart.origin;
    originZipEl.textContent = o.zip5 || `${o.prefix}xx`;
    if (origins.locked) {
      originEditBtn.hidden = true;
      originEditor.hidden = true;
      originPlaceEl.textContent = `${o.state || "—"} · prefix ${o.prefix}`;
      return;
    }
    originEditBtn.hidden = false;
    const n = origins.available.length;
    originPlaceEl.textContent =
      `${o.state || "—"} · prefix ${o.prefix}` +
      (n > 1 ? ` · ${n} origins on file` : "");
  }

  function resetWaybill() {
    pinned = null;
    regions.selectAll("path").classed("pinned", false);
    wbZip.textContent = "—";
    wbRoute.textContent = `${chart.origin.prefix} → · · ·`;
    wbStamp.dataset.empty = "true";
    wbZone.textContent = "·";
    wbStamp.style.setProperty("--stamp", "var(--kraft)");
    wbList.innerHTML = "";
    wbNote.textContent = "Hover the map, or search a ZIP, to fill in this waybill.";
  }

  async function setOrigin(raw) {
    originMsg.classList.remove("error");
    if (!/^\d{3}(\d{2})?$/.test(raw)) {
      originMsg.textContent = "Enter a 3- or 5-digit ZIP code.";
      originMsg.classList.add("error");
      return;
    }
    const r = await fetch(`/api/zonechart/chart?origin=${raw}`);
    if (!r.ok) {
      originMsg.textContent = r.status === 404
        ? `No chart on file for prefix ${raw.slice(0, 3)} yet — run scripts/fetch_charts.py to download the full UPS set.`
        : "Could not load that origin's chart.";
      originMsg.classList.add("error");
      return;
    }
    chart = await r.json();
    zones = chart.zones;
    services = chart.services;
    originMsg.textContent = "";
    originEditor.hidden = true;
    originEditBtn.setAttribute("aria-expanded", "false");
    tableBuilt = false;
    if (!drawer.hidden) buildTable();
    resetWaybill();
    updateOriginCard();
    placeMarker();
    repaint();
  }

  originEditBtn.addEventListener("click", () => {
    originEditor.hidden = !originEditor.hidden;
    originEditBtn.setAttribute("aria-expanded", String(!originEditor.hidden));
    if (!originEditor.hidden) originInput.focus();
  });
  document.getElementById("origin-go").addEventListener("click", () => setOrigin(originInput.value.trim()));
  originInput.addEventListener("keydown", ev => { if (ev.key === "Enter") setOrigin(originInput.value.trim()); });

  /* ---------- search ---------- */
  const input = document.getElementById("zip-search");
  const msg = document.getElementById("search-msg");

  function doSearch() {
    const raw = input.value.trim();
    msg.classList.remove("error");
    if (!/^\d{3,5}$/.test(raw)) {
      msg.textContent = "Enter a 3- or 5-digit ZIP code.";
      msg.classList.add("error");
      return;
    }
    const prefix = raw.slice(0, 3);
    const zip5 = raw.length === 5 ? raw : null;
    if (!zones[prefix]) {
      msg.textContent = `No zone data for prefix ${prefix} — likely a military or territory ZIP served by the worldwide tables.`;
      msg.classList.add("error");
      return;
    }
    msg.textContent = "";
    setPinned(prefix, zip5);
    const f = zip3.features.find(x => x.properties.z === prefix);
    if (f && !isPR(f)) {
      const [[x0, y0], [x1, y1]] = path.bounds(f);
      const k = Math.min(8, 0.6 / Math.max((x1 - x0) / W, (y1 - y0) / H));
      svg.transition().duration(650).call(
        zoom.transform,
        d3.zoomIdentity.translate(W / 2, H / 2).scale(k)
          .translate(-(x0 + x1) / 2, -(y0 + y1) / 2)
      );
    }
  }
  document.getElementById("zip-go").addEventListener("click", doSearch);
  input.addEventListener("keydown", ev => { if (ev.key === "Enter") doSearch(); });

  /* ---------- table drawer ---------- */
  const drawer = document.getElementById("table-drawer");
  const toggle = document.getElementById("table-toggle");
  let tableBuilt = false;

  function buildTable() {
    const thead = drawer.querySelector("thead");
    thead.innerHTML = `<tr><th>Prefix</th>${services.map(s => `<th>${s.short}</th>`).join("")}</tr>`;
    const tbody = drawer.querySelector("tbody");
    const rows = Object.keys(zones).sort().map(p => {
      const cells = services.map(s => {
        const t = zones[p][s.id].tier;
        const txt = t === undefined || t === null ? "—" : (t === "ext" ? "Ext" : `Zone ${t}`);
        return `<td>${txt}</td>`;
      });
      return `<tr data-p="${p}"><td>${p}</td>${cells.join("")}</tr>`;
    });
    tbody.innerHTML = rows.join("");
    tableBuilt = true;
  }
  toggle.addEventListener("click", () => {
    if (!tableBuilt) buildTable();
    const open = drawer.hidden;
    drawer.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
  });
  document.getElementById("table-close").addEventListener("click", () => {
    drawer.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  });
  document.getElementById("table-filter").addEventListener("input", ev => {
    const q = ev.target.value.trim();
    drawer.querySelectorAll("tbody tr").forEach(tr => {
      tr.style.display = !q || tr.dataset.p.startsWith(q) ? "" : "none";
    });
  });
  document.addEventListener("keydown", ev => {
    if (ev.key === "Escape" && !drawer.hidden) {
      drawer.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }
  });

  /* ---------- boot ---------- */
  updateOriginCard();
  placeMarker();
  repaint();
})();
