"""Mesa-ready campus map adapter built from map/summary.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


Pos = tuple[int, int]  # Mesa coordinate: (x, y) = (summary col, summary row)


@dataclass(frozen=True)
class Region:
    id: str
    terrain: str
    name: str
    function: str
    area: int
    cell_count: int
    available: bool
    open_time: str
    close_time: str
    entrances: tuple[Pos, ...]
    cells: frozenset[Pos]
    bounds: dict[str, int]


class CampusMap:
    """Load relative-grid campus annotations and expose movement helpers."""

    base_walkable_terrains = frozenset({"road", "open_ground"})

    def __init__(self, summary: dict[str, Any]) -> None:
        self.summary = summary
        self.grid_size = int(summary["gridSize"])
        self.width = int(summary["size"]["cols"])
        self.height = int(summary["size"]["rows"])
        self.origin = dict(summary.get("origin", {}))
        self.terrain_labels = list(summary.get("terrainLabels", []))
        self.terrain_palette = dict(summary.get("terrainPalette", {}))

        self.terrain_by_pos: dict[Pos, str] = {}
        for cell in summary.get("terrainCells", []):
            pos = self.cell_to_pos(cell)
            self.terrain_by_pos[pos] = cell["terrain"]

        self.regions_by_id: dict[str, Region] = {}
        self.region_by_pos: dict[Pos, str] = {}
        self.entrances_by_region: dict[str, tuple[Pos, ...]] = {}
        self._entrance_to_region: dict[Pos, str] = {}

        for item in summary.get("regions", []):
            cells = frozenset(self.cell_to_pos(cell) for cell in item.get("cells", []))
            entrances = tuple(self.cell_to_pos(cell) for cell in item.get("entrances", []))
            region = Region(
                id=item["id"],
                terrain=item["terrain"],
                name=item.get("name", ""),
                function=item.get("function", ""),
                area=int(item.get("area", item.get("cellCount", 0))),
                cell_count=int(item.get("cellCount", item.get("area", 0))),
                available=item.get("available", True) is not False,
                open_time=item.get("open_time", "00:00"),
                close_time=item.get("close_time", "23:59"),
                entrances=entrances,
                cells=cells,
                bounds=dict(item.get("bounds", {})),
            )
            self.regions_by_id[region.id] = region
            self.entrances_by_region[region.id] = entrances
            for pos in cells:
                self.region_by_pos[pos] = region.id
            for pos in entrances:
                self._entrance_to_region[pos] = region.id

        self.walkable_positions = tuple(
            pos for pos in sorted(self.terrain_by_pos, key=lambda p: (p[1], p[0]))
            if self.is_walkable(pos)
        )
        self.walkable_position_set = frozenset(self.walkable_positions)
        self._neighbors4_by_pos = self._build_neighbor_cache(moore=False)
        self._neighbors8_by_pos = self._build_neighbor_cache(moore=True)

    @classmethod
    def from_file(cls, path: str | Path = "map/summary.json") -> "CampusMap":
        with Path(path).open("r", encoding="utf-8") as f:
            return cls(json.load(f))

    @staticmethod
    def cell_to_pos(cell: dict[str, int]) -> Pos:
        return int(cell["col"]), int(cell["row"])

    @staticmethod
    def pos_to_cell(pos: Pos) -> dict[str, int]:
        x, y = pos
        return {"row": y, "col": x}

    @property
    def terrain_cell_count(self) -> int:
        return len(self.terrain_by_pos)

    @property
    def region_count(self) -> int:
        return len(self.regions_by_id)

    def in_bounds(self, pos: Pos) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def terrain_at(self, pos: Pos) -> str | None:
        return self.terrain_by_pos.get(pos)

    def region_at(self, pos: Pos) -> Region | None:
        region_id = self.region_by_pos.get(pos)
        if region_id is None:
            return None
        return self.regions_by_id[region_id]

    def entrances(self, region_id: str) -> tuple[Pos, ...]:
        return self.entrances_by_region.get(region_id, ())

    def is_region_entrance(self, pos: Pos, region_id: str | None = None) -> bool:
        found_region_id = self._entrance_to_region.get(pos)
        if found_region_id is None:
            return False
        return region_id is None or found_region_id == region_id

    def is_walkable(self, pos: Pos) -> bool:
        if hasattr(self, "walkable_position_set"):
            return pos in self.walkable_position_set

        if not self.in_bounds(pos):
            return False

        terrain = self.terrain_at(pos)
        if terrain in self.base_walkable_terrains:
            return True

        region = self.region_at(pos)
        if terrain == "gate":
            return bool(region and region.available)

        if region and region.available and self.is_region_entrance(pos, region.id):
            return True

        return False

    def neighbors(self, pos: Pos, *, moore: bool = False) -> list[Pos]:
        if hasattr(self, "_neighbors8_by_pos"):
            cached = self._neighbors8_by_pos if moore else self._neighbors4_by_pos
            return list(cached.get(pos, ()))

        return list(self._neighbor_candidates(pos, moore=moore))

    def _build_neighbor_cache(self, *, moore: bool) -> dict[Pos, tuple[Pos, ...]]:
        return {
            pos: tuple(self._neighbor_candidates(pos, moore=moore))
            for pos in self.walkable_positions
        }

    def _neighbor_candidates(self, pos: Pos, *, moore: bool = False) -> Iterable[Pos]:
        x, y = pos
        offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if moore:
            offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        candidates = [(x + dx, y + dy) for dx, dy in offsets]
        return (candidate for candidate in candidates if self.is_walkable(candidate))

    def nearest_entrance(
        self,
        pos: Pos,
        region_id: str | None = None,
        *,
        only_available: bool = True,
    ) -> tuple[Pos, str, int] | None:
        candidates: Iterable[tuple[str, Region]]
        if region_id is None:
            candidates = self.regions_by_id.items()
        else:
            region = self.regions_by_id.get(region_id)
            candidates = [] if region is None else [(region_id, region)]

        best: tuple[Pos, str, int] | None = None
        x, y = pos
        for rid, region in candidates:
            if only_available and not region.available:
                continue
            for entrance in region.entrances:
                distance = abs(entrance[0] - x) + abs(entrance[1] - y)
                if best is None or distance < best[2]:
                    best = (entrance, rid, distance)
        return best

    def require_walkable_positions(self) -> tuple[Pos, ...]:
        if not self.walkable_positions:
            raise ValueError("campus map has no walkable positions")
        return self.walkable_positions
