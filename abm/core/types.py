"""Shared student data types for the daily campus simulation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .map import Pos


SECONDS_PER_DAY = 24 * 60 * 60


@dataclass
class StudentProfile:
    name: str = ""
    gender: str = ""
    home: str | None = None
    workplace: str | None = None
    normal_meal_speed: float = 1.0
    normal_walk_speed_cells_per_step: float = 1.0


@dataclass
class StudentTrait:
    personality: dict[str, float] = field(
        default_factory=lambda: {
            "openness": 0.5,
            "conscientiousness": 0.8,
            "extraversion": 0.4,
            "agreeableness": 0.5,
            "neuroticism": 0.3,
        }
    )
    wellbeing: float = 0.8
    interests: dict[str, float] = field(
        default_factory=lambda: {"study": 0.7, "exercise": 0.3, "music": 0.4, "game": 0.4}
    )
    skills: dict[str, float] = field(
        default_factory=lambda: {"study": 0.5, "exercise": 0.5, "music": 0.5, "game": 0.5}
    )
    physical_health: float = 1.0
    mental_health: float = 0.8


@dataclass
class StudentState:
    emotion: dict[str, float] = field(
        default_factory=lambda: {"pleasure": 0.5, "arousal": 0.5, "dominance": 0.5}
    )
    satiety: float = 0.5
    energy: float = 0.8
    intrinsic_satisfaction: float = 0.0
    extrinsic_satisfaction: float = 0.0
    social_contribution: float = 0.0
    social_return: float = 0.0


@dataclass
class StudentContext:
    pos: Pos
    phase: str = "IDLE"
    path: list[Pos] = field(default_factory=list)
    last_path: list[Pos] = field(default_factory=list)
    path_index: int = 0
    intention: str | None = None
    target_pos: Pos | None = None
    target_region_id: str | None = None
    current_action: str | None = None
    last_action: str | None = None
    action_started_at: int | None = None
    remaining_action_seconds: int = 0
    action_phase: str | None = None
    last_decision_reason: str | None = None
    current_speed_cells_per_step: float | None = None
    movement_progress: float = 0.0
    activity_history: list[dict[str, object]] = field(default_factory=list)


def parse_time_to_seconds(text: str) -> int:
    parts = text.strip().split(":")
    if len(parts) not in {2, 3}:
        raise ValueError("start_time must use HH:MM or HH:MM:SS")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2]) if len(parts) == 3 else 0
    except ValueError as exc:
        raise ValueError("start_time must contain integer HH:MM or HH:MM:SS values") from exc
    if not 0 <= hour <= 23:
        raise ValueError("start_time hour must be in 0..23")
    if not 0 <= minute <= 59:
        raise ValueError("start_time minute must be in 0..59")
    if not 0 <= second <= 59:
        raise ValueError("start_time second must be in 0..59")
    return hour * 3600 + minute * 60 + second


def format_seconds_as_time(seconds: int) -> str:
    seconds = seconds % SECONDS_PER_DAY
    hour = seconds // 3600
    minute = (seconds % 3600) // 60
    second = seconds % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def pos_payload(pos: Pos) -> dict[str, int]:
    x, y = pos
    return {"x": x, "y": y, "row": y, "col": x}
