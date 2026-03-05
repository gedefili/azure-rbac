/* Azure RBAC Dashboard – D3.js v7 graph visualisation */
/* global d3 */

"use strict";

// ── Colour helpers ────────────────────────────────────────────────────────────

const NODE_COLORS = {
  User:             "var(--user-color)",
  Group:            "var(--group-color)",
  ServicePrincipal: "var(--sp-color)",
  subscription:     "var(--resource-color)",
  management_group: "#d2a8ff",
  resource_group:   "#e3b341",
  resource:         "#a5a5a5",
  BuiltInRole:      "var(--role-color)",
  CustomRole:       "#ff7b72",
};

function nodeColor(d) {
  return NODE_COLORS[d.sub_type] || NODE_COLORS[d.node_type] || "#8b949e";
}

function nodeRadius(d) {
  if (d.node_type === "role") return 6;
  if (d.node_type === "resource") {
    if (d.sub_type === "subscription" || d.sub_type === "management_group") return 14;
    if (d.sub_type === "resource_group") return 10;
    return 7;
  }
  return 10; // principal
}

// ── State ─────────────────────────────────────────────────────────────────────

let allNodes = [];
let allLinks = [];
let allFindings = [];
let activeFilter = "all";
let simulation;
let svg, g, linkSel, nodeSel;

// ── Bootstrap ─────────────────────────────────────────────────────────────────

async function init() {
  await Promise.all([loadGraph(), loadFindings()]);
  renderGraph();
  renderFindings();
  updateStats();
  wireControls();
}

async function loadGraph() {
  try {
    const res = await fetch("/api/graph");
    const data = await res.json();
    allNodes = data.nodes || [];
    allLinks = data.links || [];
  } catch (e) {
    console.error("Failed to load graph:", e);
  }
}

async function loadFindings() {
  try {
    const res = await fetch("/api/findings");
    allFindings = await res.json();
  } catch (e) {
    console.error("Failed to load findings:", e);
  }
}

// ── Graph rendering ───────────────────────────────────────────────────────────

function renderGraph() {
  const container = document.getElementById("graph-container");
  const w = container.clientWidth;
  const h = container.clientHeight;

  d3.select("#graph-svg").selectAll("*").remove();

  if (allNodes.length === 0) {
    document.getElementById("empty-state").style.display = "block";
    return;
  }
  document.getElementById("empty-state").style.display = "none";

  const nodes = filteredNodes();
  const nodeIds = new Set(nodes.map(n => n.id));
  const links = allLinks.filter(l => nodeIds.has(l.source) && nodeIds.has(l.target));

  // Deep-copy to avoid D3 mutating original data
  const simNodes = nodes.map(n => ({ ...n }));
  const simLinks = links.map(l => ({ ...l }));

  svg = d3.select("#graph-svg");
  const zoom = d3.zoom()
    .scaleExtent([0.05, 5])
    .on("zoom", event => g.attr("transform", event.transform));
  svg.call(zoom);

  g = svg.append("g");

  // Arrow markers
  svg.append("defs").selectAll("marker")
    .data(["assigned", "scoped_to", "contains"])
    .join("marker")
      .attr("id", d => `arrow-${d}`)
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 20)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
    .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", d => d === "assigned" ? "var(--accent)" : "var(--border)");

  // Links
  linkSel = g.append("g").selectAll("line")
    .data(simLinks)
    .join("line")
      .attr("class", d => `link ${d.edge_type || ""}`)
      .attr("marker-end", d => `url(#arrow-${d.edge_type || "default"})`);

  // Node groups
  nodeSel = g.append("g").selectAll(".node")
    .data(simNodes, d => d.id)
    .join("g")
      .attr("class", d => `node${d.security_flags && d.security_flags.length ? " flagged" : ""}`)
      .call(d3.drag()
        .on("start", dragStarted)
        .on("drag", dragged)
        .on("end", dragEnded))
      .on("click", onNodeClick)
      .on("mouseover", onNodeMouseover)
      .on("mouseout", onNodeMouseout);

  nodeSel.append("circle")
    .attr("r", nodeRadius)
    .attr("fill", nodeColor)
    .attr("stroke", d => d.security_flags && d.security_flags.length ? "var(--critical)" : "var(--border)");

  nodeSel.append("text")
    .attr("dy", d => nodeRadius(d) + 12)
    .attr("text-anchor", "middle")
    .text(d => truncate(d.label, 20));

  simulation = d3.forceSimulation(simNodes)
    .force("link", d3.forceLink(simLinks).id(d => d.id).distance(80))
    .force("charge", d3.forceManyBody().strength(-150))
    .force("center", d3.forceCenter(w / 2, h / 2))
    .force("collision", d3.forceCollide().radius(d => nodeRadius(d) + 6))
    .on("tick", ticked);
}

function ticked() {
  linkSel
    .attr("x1", d => d.source.x)
    .attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x)
    .attr("y2", d => d.target.y);

  nodeSel.attr("transform", d => `translate(${d.x},${d.y})`);
}

function filteredNodes() {
  const q = document.getElementById("search-box").value.toLowerCase();
  return allNodes.filter(n => {
    if (activeFilter === "flagged") {
      if (!n.security_flags || n.security_flags.length === 0) return false;
    } else if (activeFilter !== "all") {
      if (n.node_type !== activeFilter) return false;
    }
    if (q) {
      return (n.label || "").toLowerCase().includes(q) ||
             (n.id || "").toLowerCase().includes(q);
    }
    return true;
  });
}

// ── Drag handlers ─────────────────────────────────────────────────────────────

function dragStarted(event, d) {
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}
function dragged(event, d) { d.fx = event.x; d.fy = event.y; }
function dragEnded(event, d) {
  if (!event.active) simulation.alphaTarget(0);
  d.fx = null; d.fy = null;
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

function onNodeMouseover(event, d) {
  const tt = document.getElementById("tooltip");
  document.getElementById("tt-title").textContent = d.label;
  document.getElementById("tt-type").textContent =
    `${d.node_type}${d.sub_type ? " · " + d.sub_type : ""}`;
  const flags = d.security_flags || [];
  document.getElementById("tt-flags").textContent =
    flags.length ? "⚠ " + flags.join(", ") : "";
  tt.style.display = "block";
  moveTip(event);
}
function onNodeMouseout() {
  document.getElementById("tooltip").style.display = "none";
}
document.addEventListener("mousemove", e => {
  const tt = document.getElementById("tooltip");
  if (tt.style.display !== "none") moveTip(e);
});
function moveTip(event) {
  const tt = document.getElementById("tooltip");
  const container = document.getElementById("graph-container");
  const rect = container.getBoundingClientRect();
  let x = event.clientX - rect.left + 14;
  let y = event.clientY - rect.top + 14;
  if (x + 290 > rect.width) x = event.clientX - rect.left - 290;
  tt.style.left = x + "px";
  tt.style.top = y + "px";
}

// ── Detail panel ──────────────────────────────────────────────────────────────

async function onNodeClick(event, d) {
  event.stopPropagation();
  document.getElementById("dp-title").textContent = d.label;
  document.getElementById("dp-type").textContent =
    `${d.node_type}${d.sub_type ? " · " + d.sub_type : ""}`;

  // Metadata
  const metaEl = document.getElementById("dp-metadata");
  metaEl.innerHTML = "";
  for (const [k, v] of Object.entries(d.metadata || {})) {
    if (typeof v === "object") continue;
    const row = document.createElement("div");
    row.className = "dp-item";
    row.textContent = `${k}: ${v}`;
    metaEl.appendChild(row);
  }

  // Security flags
  const flagsEl = document.getElementById("dp-flags");
  flagsEl.innerHTML = "";
  (d.security_flags || []).forEach(f => {
    const el = document.createElement("div");
    el.className = "dp-item";
    el.style.color = "var(--critical)";
    el.textContent = "⚠ " + f;
    flagsEl.appendChild(el);
  });

  // Fetch neighbours
  try {
    const res = await fetch(`/api/graph/node/${encodeURIComponent(d.id)}`);
    const detail = await res.json();
    const neighEl = document.getElementById("dp-neighbours");
    neighEl.innerHTML = "";
    (detail.neighbours || [])
      .filter(n => n.id !== d.id)
      .forEach(n => {
        const el = document.createElement("div");
        el.className = "dp-item";
        el.textContent = `${n.label} (${n.node_type})`;
        neighEl.appendChild(el);
      });
  } catch (e) { /* ignore */ }

  document.getElementById("detail-panel").classList.add("open");
}

// Close detail on background click
document.getElementById("graph-container").addEventListener("click", () => {
  document.getElementById("detail-panel").classList.remove("open");
});
document.getElementById("close-detail").addEventListener("click", () => {
  document.getElementById("detail-panel").classList.remove("open");
});

// ── Findings panel ────────────────────────────────────────────────────────────

function renderFindings() {
  const list = document.getElementById("findings-list");
  list.innerHTML = "";
  if (allFindings.length === 0) {
    list.innerHTML = '<p style="font-size:12px;color:var(--text-muted)">No findings loaded.</p>';
    return;
  }
  const order = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
  const sorted = [...allFindings].sort(
    (a, b) => (order[a.severity] ?? 5) - (order[b.severity] ?? 5)
  );
  sorted.forEach(f => {
    const card = document.createElement("div");
    card.className = `finding-card ${f.severity}`;
    card.innerHTML = `
      <div class="sev ${f.severity}">${f.severity}</div>
      <div class="title">${escHtml(f.title)}</div>
      <div class="desc">${escHtml(f.description)}</div>
    `;
    card.addEventListener("click", () => {
      // Highlight affected nodes
      if (nodeSel) {
        nodeSel.select("circle")
          .attr("stroke", d =>
            (f.affected_nodes || []).includes(d.id) ? "white" :
            d.security_flags && d.security_flags.length ? "var(--critical)" : "var(--border)"
          )
          .attr("stroke-width", d =>
            (f.affected_nodes || []).includes(d.id) ? 3 : 1.5
          );
      }
    });
    list.appendChild(card);
  });
}

// ── Stats ─────────────────────────────────────────────────────────────────────

function updateStats() {
  document.getElementById("stat-nodes").textContent = allNodes.length;
  document.getElementById("stat-edges").textContent = allLinks.length;
  document.getElementById("stat-principals").textContent =
    allNodes.filter(n => n.node_type === "principal").length;
  document.getElementById("stat-findings").textContent = allFindings.length;
  document.getElementById("tenant-label").textContent =
    `${allNodes.filter(n => n.sub_type === "subscription").length} subscription(s)`;
}

// ── Controls ──────────────────────────────────────────────────────────────────

function wireControls() {
  // Filter buttons
  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilter = btn.dataset.type;
      renderGraph();
    });
  });

  // Reset view
  document.getElementById("btn-reset").addEventListener("click", () => {
    d3.select("#graph-svg").transition().duration(500).call(
      d3.zoom().transform, d3.zoomIdentity
    );
  });

  // Reload
  document.getElementById("btn-reload").addEventListener("click", async () => {
    await fetch("/api/graph/reload", { method: "POST" });
    await Promise.all([loadGraph(), loadFindings()]);
    renderGraph();
    renderFindings();
    updateStats();
  });

  // Search
  document.getElementById("search-box").addEventListener("input", () => renderGraph());
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function truncate(str, max) {
  if (!str) return "";
  return str.length > max ? str.slice(0, max - 1) + "…" : str;
}

function escHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ── Entry point ───────────────────────────────────────────────────────────────

window.addEventListener("DOMContentLoaded", init);
