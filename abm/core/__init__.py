"""Core types and spatial infrastructure (no Mesa dependency)."""

from .map import CampusMap, Pos, Region
from .pathfinding import PathResult, astar, path_to_region
from .routing import grid_distance, route_to_region
from .types import (
    SECONDS_PER_DAY,
    StudentContext,
    StudentProfile,
    StudentState,
    StudentTrait,
    format_seconds_as_time,
    parse_time_to_seconds,
    pos_payload,
)

__all__ = [
    "CampusMap",
    "PathResult",
    "Pos",
    "Region",
    "SECONDS_PER_DAY",
    "StudentContext",
    "StudentProfile",
    "StudentState",
    "StudentTrait",
    "astar",
    "format_seconds_as_time",
    "grid_distance",
    "parse_time_to_seconds",
    "path_to_region",
    "pos_payload",
    "route_to_region",
]
