"""A* path planning helpers for the campus activity map."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from math import inf
from typing import Callable

from .map import CampusMap, Pos


CostFn = Callable[[Pos, Pos], float]


@dataclass(frozen=True)
class PathResult:
    reachable: bool
    path: tuple[Pos, ...]
    cost: float | None
    expanded: int
    start: Pos
    goal: Pos
    reason: str
    goal_region: str | None = None
    target_kind: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "reachable": self.reachable,
            "path": [pos_to_record(pos) for pos in self.path],
            "cost": self.cost,
            "expanded": self.expanded,
            "start": pos_to_record(self.start),
            "goal": pos_to_record(self.goal),
            "reason": self.reason,
            "goal_region": self.goal_region,
            "target_kind": self.target_kind,
        }


def pos_to_record(pos: Pos) -> dict[str, int]:
    x, y = pos
    return {"x": x, "y": y, "row": y, "col": x}


def manhattan(a: Pos, b: Pos) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def chebyshev(a: Pos, b: Pos) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def astar(
    campus_map: CampusMap,
    start: Pos,
    goal: Pos,
    *,
    cost_fn: CostFn | None = None,
) -> PathResult:
    """Plan an 8-neighbor, equal-cost path over CampusMap.neighbors()."""

    start = (int(start[0]), int(start[1]))
    goal = (int(goal[0]), int(goal[1]))

    if not campus_map.is_walkable(start):
        return PathResult(False, (), None, 0, start, goal, "start_not_walkable")
    if not campus_map.is_walkable(goal):
        return PathResult(False, (), None, 0, start, goal, "goal_not_walkable")
    if start == goal:
        return PathResult(True, (start,), 0, 0, start, goal, "start_is_goal")

    step_cost = cost_fn or (lambda _current, _neighbor: 1.0)
    frontier: list[tuple[float, int, Pos]] = []
    serial = count()
    heappush(frontier, (chebyshev(start, goal), next(serial), start))

    came_from: dict[Pos, Pos | None] = {start: None}
    cost_so_far: dict[Pos, float] = {start: 0.0}
    expanded = 0

    while frontier:
        _priority, _serial, current = heappop(frontier)
        expanded += 1

        if current == goal:
            path = _reconstruct_path(came_from, goal)
            return PathResult(True, path, cost_so_far[goal], expanded, start, goal, "ok")

        for neighbor in campus_map.neighbors(current, moore=True):
            new_cost = cost_so_far[current] + float(step_cost(current, neighbor))
            if new_cost < cost_so_far.get(neighbor, inf):
                cost_so_far[neighbor] = new_cost
                priority = new_cost + chebyshev(neighbor, goal)
                came_from[neighbor] = current
                heappush(frontier, (priority, next(serial), neighbor))

    return PathResult(False, (), None, expanded, start, goal, "unreachable")


def path_to_region(campus_map: CampusMap, start: Pos, region_id: str) -> PathResult:
    """Plan from start to the nearest reachable legal target for a region."""

    start = (int(start[0]), int(start[1]))
    region = campus_map.regions_by_id.get(region_id)
    if region is None:
        return PathResult(False, (), None, 0, start, start, "region_not_found", region_id, "region")
    if not region.available:
        return PathResult(False, (), None, 0, start, start, "region_unavailable", region_id, "region")

    candidates = [pos for pos in region.entrances if campus_map.is_walkable(pos)]
    target_kind = "entrance"

    if not candidates and region.terrain == "gate":
        candidates = [pos for pos in region.cells if campus_map.is_walkable(pos)]
        target_kind = "gate_cell"

    if not candidates:
        return PathResult(
            False,
            (),
            None,
            0,
            start,
            start,
            "region_has_no_walkable_target",
            region_id,
            target_kind,
        )

    best: PathResult | None = None
    for goal in sorted(candidates, key=lambda pos: (chebyshev(start, pos), pos[1], pos[0])):
        result = astar(campus_map, start, goal)
        result = PathResult(
            result.reachable,
            result.path,
            result.cost,
            result.expanded,
            result.start,
            result.goal,
            result.reason,
            region_id,
            target_kind,
        )
        if result.reachable and (best is None or (result.cost or inf) < (best.cost or inf)):
            best = result

    if best is not None:
        return best

    nearest = min(candidates, key=lambda pos: (chebyshev(start, pos), pos[1], pos[0]))
    failed = astar(campus_map, start, nearest)
    return PathResult(
        False,
        (),
        None,
        failed.expanded,
        start,
        nearest,
        "region_target_unreachable",
        region_id,
        target_kind,
    )


def _reconstruct_path(came_from: dict[Pos, Pos | None], goal: Pos) -> tuple[Pos, ...]:
    path = [goal]
    current = goal
    while came_from[current] is not None:
        current = came_from[current]  # type: ignore[assignment]
        path.append(current)
    path.reverse()
    return tuple(path)
