#!/usr/bin/env python3
"""Render a standalone HTML viewer from BHmap summary JSON.

Usage:
    python render_summary_html.py summary.json summary_view.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_html(summary: dict[str, Any]) -> str:
    embedded = json.dumps(summary, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__SUMMARY_JSON__", embedded)


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BHmap Summary Viewer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f8;
      --panel: #ffffff;
      --line: #d9dee6;
      --text: #17202a;
      --muted: #64748b;
      --accent: #176b87;
      --accent-soft: #dff2f6;
      --shadow: 0 10px 30px rgba(15, 23, 42, 0.14);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      height: 100vh;
      overflow: hidden;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", Arial, "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }

    .app {
      display: grid;
      grid-template-columns: 380px minmax(0, 1fr);
      height: 100vh;
      min-width: 900px;
    }

    aside {
      display: flex;
      flex-direction: column;
      gap: 14px;
      overflow-y: auto;
      padding: 16px;
      border-right: 1px solid var(--line);
      background: var(--panel);
    }

    main {
      position: relative;
      min-width: 0;
      overflow: hidden;
      background: #101820;
    }

    h1 {
      margin: 0;
      font-size: 19px;
      line-height: 1.25;
      font-weight: 700;
    }

    h2 {
      margin: 0 0 8px;
      font-size: 13px;
      line-height: 1.25;
      color: #334155;
      font-weight: 700;
    }

    .subtle {
      margin: 5px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }

    .section {
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }

    select, input, button {
      width: 100%;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      color: #1f2937;
      padding: 6px 9px;
      font: inherit;
      font-size: 13px;
    }

    button {
      cursor: pointer;
      transition: border-color .12s ease, background .12s ease, color .12s ease;
    }

    button:hover {
      border-color: #9eb7c1;
      background: #f8fbfc;
    }

    .button-row {
      display: flex;
      gap: 8px;
      margin-top: 8px;
    }

    .button-row button {
      min-width: 0;
      flex: 1;
    }

    .palette-grid {
      display: flex;
      flex-direction: column;
      gap: 7px;
    }

    .palette-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 52px;
      gap: 10px;
      align-items: center;
      font-size: 13px;
    }

    .palette-row label {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    input[type="color"] {
      height: 30px;
      padding: 2px;
      cursor: pointer;
    }

    .stats {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }

    .stat {
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 8px;
      background: #f8fafc;
    }

    .stat strong {
      display: block;
      font-size: 16px;
      line-height: 1.2;
    }

    .stat span {
      color: var(--muted);
      font-size: 11px;
    }

    .region-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-height: 290px;
      overflow: auto;
      padding-right: 3px;
    }

    .region-item {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      width: 100%;
      text-align: left;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fff;
      padding: 8px 9px;
      cursor: pointer;
      font: inherit;
    }

    .region-item.active {
      border-color: var(--accent);
      background: var(--accent-soft);
    }

    .region-title {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
      font-weight: 700;
    }

    .region-meta {
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }

    .detail {
      display: grid;
      grid-template-columns: 96px minmax(0, 1fr);
      gap: 7px 10px;
      font-size: 13px;
    }

    .detail .label {
      color: var(--muted);
    }

    .detail .value {
      min-width: 0;
      overflow-wrap: anywhere;
    }

    canvas {
      display: block;
      width: 100%;
      height: 100%;
      cursor: pointer;
    }

    canvas.panning {
      cursor: grab;
    }

    .status {
      position: absolute;
      left: 14px;
      right: 14px;
      bottom: 14px;
      display: flex;
      justify-content: space-between;
      gap: 10px;
      pointer-events: none;
      color: #e6edf3;
      font-size: 12px;
    }

    .status span {
      max-width: 48%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      padding: 7px 10px;
      border-radius: 7px;
      background: rgba(10, 16, 24, .78);
      box-shadow: var(--shadow);
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <section class="section">
        <h1>BHmap Summary Viewer</h1>
        <p class="subtle">Standalone relative-grid view. No BHmap image required.</p>
      </section>

      <section class="section">
        <h2>Filters</h2>
        <select id="terrainFilter"></select>
        <select id="regionFilter" style="margin-top:8px"></select>
      </section>

      <section class="section">
        <h2>Palette</h2>
        <div id="paletteEditor" class="palette-grid"></div>
        <div class="button-row">
          <button id="resetPalette" type="button">Reset</button>
          <button id="saveSummaryJson" type="button">Save JSON</button>
          <button id="saveSummaryHtml" type="button">Save HTML</button>
        </div>
        <p class="subtle" id="paletteStatus">Color changes apply immediately.</p>
      </section>

      <section class="section">
        <h2>Summary</h2>
        <div class="stats">
          <div class="stat"><strong id="terrainCount">0</strong><span>terrain cells</span></div>
          <div class="stat"><strong id="regionCount">0</strong><span>regions</span></div>
          <div class="stat"><strong id="entranceCount">0</strong><span>entrances</span></div>
        </div>
        <p class="subtle" id="coordinateInfo"></p>
      </section>

      <section class="section">
        <h2>Regions</h2>
        <div id="regionList" class="region-list"></div>
      </section>

      <section>
        <h2>Selected Region</h2>
        <div id="regionDetail" class="detail"></div>
      </section>
    </aside>

    <main>
      <canvas id="mapCanvas"></canvas>
      <div class="status">
        <span id="viewportStatus">Loading summary...</span>
        <span id="cellStatus">No cell</span>
      </div>
    </main>
  </div>

  <script>
    "use strict";

    const summary = __SUMMARY_JSON__;
    const GRID_SIZE = summary.gridSize || 25;
    const terrainPalette = summary.terrainPalette || {};
    const initialTerrainPalette = { ...terrainPalette };
    const canvas = document.getElementById("mapCanvas");
    const ctx = canvas.getContext("2d", { alpha: false });

    let terrainFilter = "all";
    let regionFilter = "all";
    let selectedRegionId = null;
    let view = { scale: 1, x: 0, y: 0 };
    let canvasSize = { width: 1, height: 1, dpr: 1 };
    let pointerState = null;
    let rafPending = false;
    let spaceDown = false;

    const terrainByCell = new Map();
    const regionById = new Map(summary.regions.map(region => [region.id, {
      ...region,
      cellSet: new Set(region.cells.map(cell => keyOf(cell.row, cell.col)))
    }]));
    const regionByCell = new Map();
    for (const region of regionById.values()) {
      for (const cell of region.cells) regionByCell.set(keyOf(cell.row, cell.col), region.id);
    }
    for (const cell of summary.terrainCells) {
      terrainByCell.set(keyOf(cell.row, cell.col), cell.terrain);
    }

    function keyOf(row, col) {
      return `${row},${col}`;
    }

    function parseKey(key) {
      const [row, col] = key.split(",").map(Number);
      return { row, col };
    }

    function colorFor(label) {
      if (terrainPalette[label]) return terrainPalette[label];
      let hash = 0;
      for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) >>> 0;
      const r = 72 + (hash & 127);
      const g = 72 + ((hash >> 8) & 127);
      const b = 72 + ((hash >> 16) & 127);
      return `#${[r, g, b].map(v => v.toString(16).padStart(2, "0")).join("")}`;
    }

    function hexToRgba(hex, alpha) {
      const n = Number.parseInt(hex.slice(1), 16);
      return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
    }

    function resizeCanvas() {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvasSize = {
        width: Math.max(1, Math.floor(rect.width)),
        height: Math.max(1, Math.floor(rect.height)),
        dpr
      };
      canvas.width = Math.floor(canvasSize.width * dpr);
      canvas.height = Math.floor(canvasSize.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      requestRender();
    }

    function fitSummary() {
      const width = summary.size.cols * GRID_SIZE;
      const height = summary.size.rows * GRID_SIZE;
      const scale = Math.min(canvasSize.width / width, canvasSize.height / height) * 0.92;
      view.scale = Math.max(0.02, scale);
      view.x = (canvasSize.width - width * view.scale) / 2;
      view.y = (canvasSize.height - height * view.scale) / 2;
      requestRender();
    }

    function screenToWorld(x, y) {
      return { x: (x - view.x) / view.scale, y: (y - view.y) / view.scale };
    }

    function worldToCell(world) {
      return { row: Math.floor(world.y / GRID_SIZE), col: Math.floor(world.x / GRID_SIZE) };
    }

    function eventPoint(event) {
      const rect = canvas.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    }

    function requestRender() {
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(() => {
        rafPending = false;
        render();
      });
    }

    function visibleRegions() {
      return summary.regions.filter(region => {
        if (regionFilter !== "all" && region.id !== regionFilter) return false;
        if (terrainFilter !== "all" && region.terrain !== terrainFilter) return false;
        return true;
      });
    }

    function visibleTerrainCells() {
      return summary.terrainCells.filter(cell => terrainFilter === "all" || cell.terrain === terrainFilter);
    }

    function render() {
      ctx.setTransform(canvasSize.dpr, 0, 0, canvasSize.dpr, 0, 0);
      ctx.fillStyle = "#101820";
      ctx.fillRect(0, 0, canvasSize.width, canvasSize.height);

      const left = Math.max(0, (0 - view.x) / view.scale);
      const top = Math.max(0, (0 - view.y) / view.scale);
      const right = Math.min(summary.size.cols * GRID_SIZE, (canvasSize.width - view.x) / view.scale);
      const bottom = Math.min(summary.size.rows * GRID_SIZE, (canvasSize.height - view.y) / view.scale);
      const rowStart = Math.max(0, Math.floor(top / GRID_SIZE) - 1);
      const rowEnd = Math.min(summary.size.rows - 1, Math.ceil(bottom / GRID_SIZE) + 1);
      const colStart = Math.max(0, Math.floor(left / GRID_SIZE) - 1);
      const colEnd = Math.min(summary.size.cols - 1, Math.ceil(right / GRID_SIZE) + 1);

      drawTerrain(rowStart, rowEnd, colStart, colEnd);
      drawRegions(rowStart, rowEnd, colStart, colEnd);
      drawEntrances(rowStart, rowEnd, colStart, colEnd);
      drawGrid(rowStart, rowEnd, colStart, colEnd);
      updateViewportStatus();
    }

    function drawTerrain(rowStart, rowEnd, colStart, colEnd) {
      for (const cell of visibleTerrainCells()) {
        if (cell.row < rowStart || cell.row > rowEnd || cell.col < colStart || cell.col > colEnd) continue;
        const x = view.x + cell.col * GRID_SIZE * view.scale;
        const y = view.y + cell.row * GRID_SIZE * view.scale;
        const w = GRID_SIZE * view.scale;
        const h = GRID_SIZE * view.scale;
        ctx.fillStyle = hexToRgba(colorFor(cell.terrain), 0.62);
        ctx.fillRect(x, y, w, h);
      }
    }

    function drawRegions(rowStart, rowEnd, colStart, colEnd) {
      for (const region of visibleRegions()) {
        if (region.bounds.rowMax < rowStart || region.bounds.rowMin > rowEnd || region.bounds.colMax < colStart || region.bounds.colMin > colEnd) continue;
        const selected = region.id === selectedRegionId;
        ctx.fillStyle = selected ? "rgba(255,255,255,.24)" : "rgba(255,255,255,.08)";
        ctx.strokeStyle = selected ? "rgba(255,255,255,.98)" : "rgba(255,255,255,.52)";
        ctx.lineWidth = selected ? 2.5 : 1.5;
        for (const cell of region.cells) {
          if (cell.row < rowStart || cell.row > rowEnd || cell.col < colStart || cell.col > colEnd) continue;
          const x = view.x + cell.col * GRID_SIZE * view.scale;
          const y = view.y + cell.row * GRID_SIZE * view.scale;
          const w = GRID_SIZE * view.scale;
          const h = GRID_SIZE * view.scale;
          ctx.fillRect(x, y, w, h);
          if (selected) ctx.strokeRect(x + 1, y + 1, Math.max(0, w - 2), Math.max(0, h - 2));
        }
      }
    }

    function drawEntrances(rowStart, rowEnd, colStart, colEnd) {
      ctx.fillStyle = "#facc15";
      ctx.strokeStyle = "#111827";
      ctx.lineWidth = 2;
      for (const region of visibleRegions()) {
        for (const entrance of region.entrances || []) {
          if (entrance.row < rowStart || entrance.row > rowEnd || entrance.col < colStart || entrance.col > colEnd) continue;
          const x = view.x + (entrance.col + 0.5) * GRID_SIZE * view.scale;
          const y = view.y + (entrance.row + 0.5) * GRID_SIZE * view.scale;
          const r = Math.max(4, Math.min(10, GRID_SIZE * view.scale * 0.35));
          ctx.beginPath();
          ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        }
      }
    }

    function drawGrid(rowStart, rowEnd, colStart, colEnd) {
      if (view.scale < 0.16) return;
      ctx.beginPath();
      ctx.strokeStyle = view.scale < 0.45 ? "rgba(255,255,255,.16)" : "rgba(255,255,255,.34)";
      ctx.lineWidth = 1;
      for (let col = colStart; col <= colEnd + 1; col++) {
        const x = Math.round(view.x + col * GRID_SIZE * view.scale) + 0.5;
        ctx.moveTo(x, view.y + rowStart * GRID_SIZE * view.scale);
        ctx.lineTo(x, view.y + (rowEnd + 1) * GRID_SIZE * view.scale);
      }
      for (let row = rowStart; row <= rowEnd + 1; row++) {
        const y = Math.round(view.y + row * GRID_SIZE * view.scale) + 0.5;
        ctx.moveTo(view.x + colStart * GRID_SIZE * view.scale, y);
        ctx.lineTo(view.x + (colEnd + 1) * GRID_SIZE * view.scale, y);
      }
      ctx.stroke();
    }

    function updateViewportStatus() {
      document.getElementById("viewportStatus").textContent =
        `${summary.size.rows}x${summary.size.cols} relative grid; zoom ${Math.round(view.scale * 100)}%`;
    }

    function updateCellStatus(event) {
      const pt = eventPoint(event);
      const { row, col } = worldToCell(screenToWorld(pt.x, pt.y));
      const terrain = terrainByCell.get(keyOf(row, col));
      const regionId = regionByCell.get(keyOf(row, col));
      const inside = row >= 0 && col >= 0 && row < summary.size.rows && col < summary.size.cols;
      document.getElementById("cellStatus").textContent = inside
        ? `row ${row}, col ${col}; ${terrain || "empty"}; ${regionId || "no region"}`
        : "Outside summary";
    }

    function selectRegion(id) {
      if (!regionById.has(id)) return;
      selectedRegionId = selectedRegionId === id ? null : id;
      regionFilter = "all";
      document.getElementById("regionFilter").value = "all";
      renderRegionList();
      renderDetail();
      requestRender();
    }

    function renderControls() {
      const terrains = Array.from(new Set(summary.terrainCells.map(cell => cell.terrain))).sort();
      document.getElementById("terrainFilter").innerHTML =
        `<option value="all">All terrain</option>` + terrains.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("");
      document.getElementById("regionFilter").innerHTML =
        `<option value="all">All regions</option>` + summary.regions.map(r => `<option value="${escapeHtml(r.id)}">${escapeHtml(r.id)}</option>`).join("");
      renderPaletteEditor(terrains);
    }

    function renderPaletteEditor(terrains) {
      const root = document.getElementById("paletteEditor");
      const ordered = [...new Set([...(summary.terrainLabels || []), ...terrains])].filter(label => terrains.includes(label));
      root.innerHTML = "";
      for (const terrain of ordered) {
        const row = document.createElement("div");
        row.className = "palette-row";
        const inputId = `palette-${terrain}`;
        row.innerHTML = `<label for="${escapeHtml(inputId)}">${escapeHtml(terrain)}</label><input id="${escapeHtml(inputId)}" type="color" value="${escapeHtml(colorFor(terrain))}">`;
        const input = row.querySelector("input");
        input.addEventListener("input", () => {
          terrainPalette[terrain] = input.value;
          summary.terrainPalette = { ...(summary.terrainPalette || {}), [terrain]: input.value };
          document.getElementById("paletteStatus").textContent = "Palette changed. Save JSON and HTML to persist it.";
          requestRender();
        });
        root.appendChild(row);
      }
    }

    function renderStats() {
      const entrances = summary.regions.reduce((sum, region) => sum + (region.entrances || []).length, 0);
      document.getElementById("terrainCount").textContent = String(summary.terrainCells.length);
      document.getElementById("regionCount").textContent = String(summary.regions.length);
      document.getElementById("entranceCount").textContent = String(entrances);
      document.getElementById("coordinateInfo").textContent =
        `origin row ${summary.origin.rowMin}, col ${summary.origin.colMin}; size ${summary.size.rows} rows x ${summary.size.cols} cols`;
    }

    function renderRegionList() {
      const root = document.getElementById("regionList");
      root.innerHTML = "";
      const list = visibleRegions();
      if (!list.length) {
        root.innerHTML = `<p class="subtle">No regions in this filter.</p>`;
        return;
      }
      for (const region of list) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `region-item${region.id === selectedRegionId ? " active" : ""}`;
        const title = region.name ? `${region.id} - ${region.name}` : region.id;
        button.innerHTML = `<span class="region-title">${escapeHtml(title)}</span><span class="region-meta">${escapeHtml(region.terrain)} / area ${region.area}</span>`;
        button.addEventListener("click", () => {
          selectedRegionId = selectedRegionId === region.id ? null : region.id;
          renderRegionList();
          renderDetail();
          requestRender();
        });
        root.appendChild(button);
      }
    }

    function renderDetail() {
      const region = regionById.get(selectedRegionId);
      const root = document.getElementById("regionDetail");
      if (!region) {
        root.innerHTML = `<span class="label">Region</span><span class="value">None selected</span>`;
        return;
      }
      const fields = [
        ["id", region.id],
        ["terrain", region.terrain],
        ["name", region.name || "-"],
        ["function", region.function || "-"],
        ["area", region.area],
        ["cellCount", region.cellCount],
        ["available", region.available ? "true" : "false"],
        ["open_time", region.open_time || "-"],
        ["close_time", region.close_time || "-"],
        ["entrances", (region.entrances || []).map(e => `(${e.row},${e.col})`).join(" ") || "-"],
        ["bounds", `${region.bounds.rowMin},${region.bounds.colMin} to ${region.bounds.rowMax},${region.bounds.colMax}`]
      ];
      root.innerHTML = fields.map(([k, v]) => `<span class="label">${escapeHtml(k)}</span><span class="value">${escapeHtml(v)}</span>`).join("");
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;"
      }[char]));
    }

    function summaryJsonText() {
      return JSON.stringify(summary, null, 2) + "\n";
    }

    function embeddedSummaryJson() {
      return JSON.stringify(summary).replace(/<\//g, "<\\/");
    }

    function currentHtmlText() {
      const html = "<!doctype html>\n" + document.documentElement.outerHTML;
      return html.replace(
        /const summary = .*?;\n    const GRID_SIZE =/s,
        `const summary = ${embeddedSummaryJson()};\n    const GRID_SIZE =`
      );
    }

    async function saveTextFile(filename, text, mimeType) {
      const blob = new Blob([text], { type: mimeType });
      if (window.showSaveFilePicker) {
        try {
          const handle = await window.showSaveFilePicker({
            suggestedName: filename,
            types: [{ description: filename, accept: { [mimeType]: [filename.slice(filename.lastIndexOf("."))] } }]
          });
          const writable = await handle.createWritable();
          await writable.write(blob);
          await writable.close();
          document.getElementById("paletteStatus").textContent = `Saved ${filename}.`;
          return;
        } catch (error) {
          if (error.name === "AbortError") return;
        }
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      document.getElementById("paletteStatus").textContent = `Downloaded ${filename}.`;
    }

    function resetPalette() {
      for (const key of Object.keys(terrainPalette)) delete terrainPalette[key];
      Object.assign(terrainPalette, initialTerrainPalette);
      summary.terrainPalette = { ...initialTerrainPalette };
      renderControls();
      requestRender();
      document.getElementById("paletteStatus").textContent = "Palette reset. Save JSON and HTML to persist it.";
    }

    function handleCanvasClick(event) {
      const pt = eventPoint(event);
      const { row, col } = worldToCell(screenToWorld(pt.x, pt.y));
      const regionId = regionByCell.get(keyOf(row, col));
      if (regionId) {
        selectedRegionId = selectedRegionId === regionId ? null : regionId;
        renderRegionList();
        renderDetail();
        requestRender();
      }
    }

    function beginPointer(event) {
      const pt = eventPoint(event);
      const shouldPan = spaceDown || event.button === 1 || event.button === 2;
      pointerState = { mode: shouldPan ? "pan" : "click", startX: pt.x, startY: pt.y, lastX: pt.x, lastY: pt.y, moved: false };
      canvas.setPointerCapture(event.pointerId);
      event.preventDefault();
    }

    function movePointer(event) {
      updateCellStatus(event);
      if (!pointerState) return;
      const pt = eventPoint(event);
      if (Math.hypot(pt.x - pointerState.startX, pt.y - pointerState.startY) > 4) pointerState.moved = true;
      if (pointerState.mode === "pan") {
        view.x += pt.x - pointerState.lastX;
        view.y += pt.y - pointerState.lastY;
        requestRender();
      }
      pointerState.lastX = pt.x;
      pointerState.lastY = pt.y;
      event.preventDefault();
    }

    function endPointer(event) {
      if (pointerState?.mode === "click" && !pointerState.moved) handleCanvasClick(event);
      pointerState = null;
      try {
        canvas.releasePointerCapture(event.pointerId);
      } catch (_) {}
      event.preventDefault();
    }

    function zoomAt(event) {
      const pt = eventPoint(event);
      const before = screenToWorld(pt.x, pt.y);
      const factor = Math.exp(-event.deltaY * 0.0015);
      view.scale = Math.max(0.025, Math.min(12, view.scale * factor));
      view.x = pt.x - before.x * view.scale;
      view.y = pt.y - before.y * view.scale;
      requestRender();
      event.preventDefault();
    }

    function setupEvents() {
      window.addEventListener("resize", () => {
        resizeCanvas();
        requestRender();
      });
      window.addEventListener("keydown", event => {
        if (event.code === "Space") {
          spaceDown = true;
          canvas.classList.add("panning");
          event.preventDefault();
        }
      });
      window.addEventListener("keyup", event => {
        if (event.code === "Space") {
          spaceDown = false;
          canvas.classList.remove("panning");
        }
      });
      canvas.addEventListener("pointerdown", beginPointer);
      canvas.addEventListener("pointermove", movePointer);
      canvas.addEventListener("pointerup", endPointer);
      canvas.addEventListener("pointercancel", endPointer);
      canvas.addEventListener("wheel", zoomAt, { passive: false });
      canvas.addEventListener("contextmenu", event => event.preventDefault());
      document.getElementById("terrainFilter").addEventListener("change", event => {
        terrainFilter = event.target.value;
        renderRegionList();
        requestRender();
      });
      document.getElementById("regionFilter").addEventListener("change", event => {
        regionFilter = event.target.value;
        if (regionFilter !== "all") selectedRegionId = regionFilter;
        renderRegionList();
        renderDetail();
        requestRender();
      });
      document.getElementById("resetPalette").addEventListener("click", resetPalette);
      document.getElementById("saveSummaryJson").addEventListener("click", () => {
        saveTextFile("summary.json", summaryJsonText(), "application/json");
      });
      document.getElementById("saveSummaryHtml").addEventListener("click", () => {
        saveTextFile("summary_view.html", currentHtmlText(), "text/html");
      });
    }

    renderControls();
    renderStats();
    renderRegionList();
    renderDetail();
    setupEvents();
    resizeCanvas();
    fitSummary();
    window.__BH_SUMMARY_VIEWER__ = {
      summary,
      selectRegion
    };
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a standalone BHmap summary HTML viewer.")
    parser.add_argument("summary", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    summary = load_json(args.summary)
    args.output.write_text(build_html(summary), encoding="utf-8")
    print(f"Wrote {args.output} with embedded summary data.")


if __name__ == "__main__":
    main()
