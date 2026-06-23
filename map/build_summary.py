#!/usr/bin/env python3
"""Build a BHmap annotation summary decoupled from the source image.

Usage:
    python build_summary.py annotations.json regions.json summary.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


GENERATED_TERRAINS = ("building", "sports_field", "gate")
GENERATED_TERRAIN_SET = set(GENERATED_TERRAINS)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def key_of(row: int, col: int) -> tuple[int, int]:
    return row, col


def relative_cell(row: int, col: int, origin: dict[str, int]) -> dict[str, int]:
    return {"row": row - origin["rowMin"], "col": col - origin["colMin"]}


def relative_bounds(bounds: dict[str, int], origin: dict[str, int]) -> dict[str, int]:
    return {
        "rowMin": bounds["rowMin"] - origin["rowMin"],
        "colMin": bounds["colMin"] - origin["colMin"],
        "rowMax": bounds["rowMax"] - origin["rowMin"],
        "colMax": bounds["colMax"] - origin["colMin"],
    }


def normalize_cells(annotation: dict[str, Any]) -> list[dict[str, Any]]:
    cells = []
    for item in annotation.get("cells", []):
        row = item.get("row")
        col = item.get("col")
        terrain = item.get("terrain")
        if isinstance(row, int) and isinstance(col, int) and isinstance(terrain, str) and terrain:
            cells.append({"row": row, "col": col, "terrain": terrain})
    if not cells:
        raise ValueError("annotations JSON does not contain terrain cells")
    cells.sort(key=lambda c: (c["row"], c["col"], c["terrain"]))
    return cells


def compute_origin_and_size(cells: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    row_min = min(c["row"] for c in cells)
    row_max = max(c["row"] for c in cells)
    col_min = min(c["col"] for c in cells)
    col_max = max(c["col"] for c in cells)
    return (
        {"rowMin": row_min, "colMin": col_min},
        {"rows": row_max - row_min + 1, "cols": col_max - col_min + 1},
    )


def generate_regions(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terrain_by_cell: dict[tuple[int, int], str] = {}
    for cell in cells:
        if cell["terrain"] in GENERATED_TERRAIN_SET:
            terrain_by_cell[key_of(cell["row"], cell["col"])] = cell["terrain"]

    visited: set[tuple[int, int]] = set()
    found: list[dict[str, Any]] = []

    for start, terrain in terrain_by_cell.items():
        if start in visited:
            continue

        stack = [start]
        visited.add(start)
        region_cells: list[tuple[int, int]] = []
        row_min = row_max = start[0]
        col_min = col_max = start[1]

        while stack:
          row, col = stack.pop()
          region_cells.append((row, col))
          row_min = min(row_min, row)
          row_max = max(row_max, row)
          col_min = min(col_min, col)
          col_max = max(col_max, col)

          for next_cell in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
              if next_cell in visited or terrain_by_cell.get(next_cell) != terrain:
                  continue
              visited.add(next_cell)
              stack.append(next_cell)

        region_cells.sort()
        found.append(
            {
                "terrain": terrain,
                "cells": region_cells,
                "cellCount": len(region_cells),
                "area": len(region_cells),
                "bounds": {
                    "rowMin": row_min,
                    "colMin": col_min,
                    "rowMax": row_max,
                    "colMax": col_max,
                },
            }
        )

    found.sort(key=lambda r: (r["terrain"], r["bounds"]["rowMin"], r["bounds"]["colMin"]))
    per_terrain: dict[str, int] = defaultdict(int)
    for region in found:
        per_terrain[region["terrain"]] += 1
        region["id"] = f'{region["terrain"]}_{per_terrain[region["terrain"]]:03d}'
    return found


def build_summary(annotation: dict[str, Any], region_metadata: dict[str, Any]) -> dict[str, Any]:
    grid_size = annotation.get("gridSize")
    if not isinstance(grid_size, int):
        raise ValueError("annotations JSON must contain integer gridSize")

    terrain_cells_abs = normalize_cells(annotation)
    origin, size = compute_origin_and_size(terrain_cells_abs)
    generated_regions_abs = generate_regions(terrain_cells_abs)
    metadata_by_id = {r.get("id"): r for r in region_metadata.get("regions", []) if r.get("id")}

    terrain_cells = [
        {**relative_cell(c["row"], c["col"], origin), "terrain": c["terrain"]}
        for c in terrain_cells_abs
    ]

    regions = []
    for generated in generated_regions_abs:
        saved = metadata_by_id.get(generated["id"], {})
        cell_set_abs = set(generated["cells"])
        entrances = []
        for entrance in saved.get("entrances", []):
            row = entrance.get("row")
            col = entrance.get("col")
            if isinstance(row, int) and isinstance(col, int) and (row, col) in cell_set_abs:
                entrances.append(relative_cell(row, col, origin))
        entrances.sort(key=lambda c: (c["row"], c["col"]))

        relative_cells = [
            relative_cell(row, col, origin)
            for row, col in generated["cells"]
        ]

        regions.append(
            {
                "id": generated["id"],
                "terrain": generated["terrain"],
                "name": saved.get("name", "") or "",
                "function": saved.get("function", "") or "",
                "area": generated["area"],
                "cellCount": generated["cellCount"],
                "available": saved.get("available", True) is not False,
                "open_time": saved.get("open_time", "00:00") or "00:00",
                "close_time": saved.get("close_time", "23:59") or "23:59",
                "entrances": entrances,
                "bounds": relative_bounds(generated["bounds"], origin),
                "cells": relative_cells,
            }
        )

    return {
        "schemaVersion": 1,
        "gridSize": grid_size,
        "origin": origin,
        "size": size,
        "terrainLabels": annotation.get("labels", {}).get("terrain", []),
        "terrainPalette": annotation.get("palette", {}).get("terrain", {}),
        "generation": {
            "regionTerrains": list(GENERATED_TERRAINS),
            "connectivity": 4,
            "coordinateSystem": "relative_grid_offset",
            "area": "cellCount",
        },
        "terrainCells": terrain_cells,
        "regions": regions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a source-image-independent BHmap summary JSON.")
    parser.add_argument("annotations", type=Path)
    parser.add_argument("regions", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    summary = build_summary(load_json(args.annotations), load_json(args.regions))
    write_json(args.output, summary)
    print(f"Wrote {args.output} with {len(summary['terrainCells'])} terrain cells and {len(summary['regions'])} regions.")


if __name__ == "__main__":
    main()
