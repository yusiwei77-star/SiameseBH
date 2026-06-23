"""Routing helpers for student activity candidate generation."""

from __future__ import annotations

from collections import deque

from .map import CampusMap, Pos, Region
from .pathfinding import PathResult


def route_to_region(campus_map: CampusMap, start: Pos, region: Region) -> tuple[Pos, PathResult] | None:
    cache: dict[tuple[Pos, str], tuple[Pos, PathResult] | None] = getattr(
        campus_map,
        "_student_route_cache",
        {},
    )
    cache_key = (start, region.id)
    if cache_key in cache:
        return cache[cache_key]

    tree = _region_route_tree(campus_map, region)
    if tree is None:
        cache[cache_key] = None
        setattr(campus_map, "_student_route_cache", cache)
        return None

    parents, costs, expanded = tree
    cost = costs.get(start)
    if cost is None:
        best = None
    else:
        path = _reconstruct_region_path(parents, start)
        target_pos = path[-1]
        best = (
            target_pos,
            PathResult(
                True,
                path,
                float(cost),
                expanded,
                start,
                target_pos,
                "ok",
                region.id,
                "entrance",
            ),
        )
    cache[cache_key] = best
    setattr(campus_map, "_student_route_cache", cache)
    return best


def _region_route_tree(
    campus_map: CampusMap,
    region: Region,
) -> tuple[dict[Pos, Pos | None], dict[Pos, int], int] | None:
    cache: dict[str, tuple[dict[Pos, Pos | None], dict[Pos, int], int] | None] = getattr(
        campus_map,
        "_student_region_route_tree_cache",
        {},
    )
    if region.id in cache:
        return cache[region.id]

    starts = tuple(pos for pos in sorted(region.entrances) if campus_map.is_walkable(pos))
    if not starts:
        cache[region.id] = None
        setattr(campus_map, "_student_region_route_tree_cache", cache)
        return None

    parents: dict[Pos, Pos | None] = {start: None for start in starts}
    costs: dict[Pos, int] = {start: 0 for start in starts}
    queue: deque[Pos] = deque(starts)
    expanded = 0
    while queue:
        current = queue.popleft()
        expanded += 1
        for neighbor in campus_map.neighbors(current, moore=True):
            if neighbor in parents:
                continue
            parents[neighbor] = current
            costs[neighbor] = costs[current] + 1
            queue.append(neighbor)

    cache[region.id] = (parents, costs, expanded)
    setattr(campus_map, "_student_region_route_tree_cache", cache)
    return cache[region.id]


def _route_tree(
    campus_map: CampusMap,
    start: Pos,
) -> tuple[dict[Pos, Pos | None], dict[Pos, int], int] | None:
    cache: dict[Pos, tuple[dict[Pos, Pos | None], dict[Pos, int], int] | None] = getattr(
        campus_map,
        "_student_route_tree_cache",
        {},
    )
    if start in cache:
        return cache[start]
    if not campus_map.is_walkable(start):
        cache[start] = None
        setattr(campus_map, "_student_route_tree_cache", cache)
        return None

    parents: dict[Pos, Pos | None] = {start: None}
    costs: dict[Pos, int] = {start: 0}
    queue: deque[Pos] = deque([start])
    expanded = 0
    while queue:
        current = queue.popleft()
        expanded += 1
        for neighbor in campus_map.neighbors(current, moore=True):
            if neighbor in parents:
                continue
            parents[neighbor] = current
            costs[neighbor] = costs[current] + 1
            queue.append(neighbor)

    cache[start] = (parents, costs, expanded)
    setattr(campus_map, "_student_route_tree_cache", cache)
    return cache[start]


def _reconstruct_path(parents: dict[Pos, Pos | None], goal: Pos) -> tuple[Pos, ...]:
    path = [goal]
    current = goal
    while parents[current] is not None:
        current = parents[current]
        path.append(current)
    path.reverse()
    return tuple(path)


def _reconstruct_region_path(parents: dict[Pos, Pos | None], start: Pos) -> tuple[Pos, ...]:
    path = [start]
    current = start
    while parents[current] is not None:
        current = parents[current]
        path.append(current)
    return tuple(path)


def grid_distance(a: Pos, b: Pos) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))
