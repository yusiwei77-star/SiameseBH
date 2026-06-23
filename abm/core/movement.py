from __future__ import annotations

import math

from .map import Pos


def step_distance(a: Pos, b: Pos) -> float:
    """Return grid movement distance between adjacent path cells."""

    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    if dx == 0 and dy == 0:
        return 0.0
    if dx <= 1 and dy <= 1:
        return math.hypot(dx, dy)
    return math.hypot(dx, dy)
