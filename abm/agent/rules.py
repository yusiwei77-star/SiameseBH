"""Decision rules for schedule-free student daily behavior."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable

from ..core.map import CampusMap, Pos, Region
from ..environment import DEFAULT_INNER_MIND_DYNAMICS, DEFAULT_MATERIAL_DYNAMICS
from ..core.pathfinding import PathResult
from ..core.routing import grid_distance, route_to_region
from ..core.types import StudentProfile, StudentState, StudentTrait, StudentContext, parse_time_to_seconds


SLEEP_SECONDS = 8 * 60 * 60
REST_SECONDS = 45 * 60
EAT_SECONDS = 30 * 60
STUDY_SECONDS = 90 * 60
EXERCISE_SECONDS = 50 * 60
SOCIAL_SECONDS = 60 * 60
SERVICE_SECONDS = 20 * 60
MEDICAL_INTERRUPT_HEALTH_THRESHOLD = 0.18
MEDICAL_URGENT_HEALTH_THRESHOLD = 0.30
MEDICAL_ZERO_NEED_SECONDS = 10 * 60

ACTIVITY_DURATIONS = {
    "sleep": SLEEP_SECONDS,
    "rest": REST_SECONDS,
    "eat": EAT_SECONDS,
    "study": STUDY_SECONDS,
    "exercise": EXERCISE_SECONDS,
    "social": SOCIAL_SECONDS,
    "service": SERVICE_SECONDS,
}

STUDY_FUNCTIONS = frozenset({"library", "teaching", "laboratory"})
EXERCISE_FUNCTIONS = frozenset(
    {
        "basketball",
        "exercise",
        "football",
        "playground",
        "sport",
        "sports_field",
        "tennisball",
        "valleyball",
        "volleyball",
    }
)
SOCIAL_FUNCTIONS = frozenset({"hall", "dormitory", "basketball", "football", "playground", "sport"})
SERVICE_FUNCTIONS = frozenset({"service", "hospital"})
DAILY_ACTIONS = ("sleep", "rest", "eat", "study", "exercise", "social", "service")


@dataclass(frozen=True)
class ActivityCandidate:
    activity: str
    region: Region
    target_pos: Pos
    route: PathResult
    utility: float
    reason: str


def update_needs(
    profile: StudentProfile,
    trait: StudentTrait,
    state: StudentState,
    context: StudentContext,
    seconds: int,
    *,
    current_second: int = 0,
) -> None:
    """Advance material and inner-mind state by elapsed simulated seconds."""

    DEFAULT_MATERIAL_DYNAMICS.advance(profile, trait, state, context, seconds)
    DEFAULT_INNER_MIND_DYNAMICS.advance(trait, state, context, seconds)


def choose_activity(
    campus_map: CampusMap,
    profile: StudentProfile,
    trait: StudentTrait,
    state: StudentState,
    context: StudentContext,
    *,
    second_of_day: int,
    rng: random.Random,
) -> ActivityCandidate | None:
    candidates = build_candidates(campus_map, profile, trait, state, context, second_of_day=second_of_day, rng=rng)
    if not candidates:
        return None

    candidates = sorted(candidates, key=lambda candidate: candidate.utility, reverse=True)
    if len(candidates) == 1 or candidates[0].utility - candidates[1].utility >= 2.0:
        return candidates[0]

    temperature = max(0.12, 0.75 - 0.50 * trait.personality.get("conscientiousness", 0.8))
    return _softmax_pick(candidates, temperature, rng)


def build_candidates(
    campus_map: CampusMap,
    profile: StudentProfile,
    trait: StudentTrait,
    state: StudentState,
    context: StudentContext,
    *,
    second_of_day: int,
    rng: random.Random,
    activities: Iterable[str] | None = None,
) -> list[ActivityCandidate]:
    candidates: list[ActivityCandidate] = []
    activity_filter = set(activities) if activities is not None else None
    for activity, regions in _activity_regions(campus_map, profile).items():
        if activity_filter is not None and activity not in activity_filter:
            continue
        if activity == "eat" and state.satiety > 0.82:
            continue
        for region in regions:
            if not _region_open(region, second_of_day):
                continue
            route_candidate = route_to_region(campus_map, context.pos, region)
            if route_candidate is None:
                continue
            target_pos, route = route_candidate
            distance = grid_distance(target_pos, context.pos)
            utility, reason = _utility(
                activity,
                profile,
                trait,
                state,
                context,
                second_of_day=second_of_day,
                distance=distance,
                rng=rng,
            )
            candidates.append(
                ActivityCandidate(
                    activity=activity,
                    region=region,
                    target_pos=target_pos,
                    route=route,
                    utility=utility,
                    reason=reason,
                )
            )
    return candidates


def available_actions(
    campus_map: CampusMap,
    profile: StudentProfile,
    state: StudentState,
    *,
    second_of_day: int,
) -> set[str]:
    actions: set[str] = set()
    for activity, regions in _activity_regions(campus_map, profile).items():
        if activity == "eat" and state.satiety > 0.82:
            continue
        if any(_region_open(region, second_of_day) for region in regions):
            actions.add(activity)
    return actions


def activity_duration(activity: str) -> int:
    return ACTIVITY_DURATIONS.get(activity, REST_SECONDS)


def should_interrupt(
    trait: StudentTrait,
    state: StudentState,
    context: StudentContext,
    campus_map: CampusMap,
    second_of_day: int,
) -> bool:
    if (
        context.current_action != "service"
        and trait.physical_health <= MEDICAL_INTERRUPT_HEALTH_THRESHOLD
    ):
        return True
    if state.satiety <= 0.05 or state.energy <= 0.08:
        return True
    if context.target_region_id:
        region = campus_map.regions_by_id.get(context.target_region_id)
        if region is None or not region.available or not _region_open(region, second_of_day):
            return True
    if context.target_pos is not None and not campus_map.is_walkable(context.target_pos):
        return True
    return False


def _activity_regions(campus_map: CampusMap, profile: StudentProfile) -> dict[str, list[Region]]:
    home = campus_map.regions_by_id.get(profile.home or "")
    regions = [region for region in campus_map.regions_by_id.values() if region.available and region.entrances]
    by_activity: dict[str, list[Region]] = {
        "sleep": [home] if home and home.entrances and home.available else [],
        "rest": [home] if home and home.entrances and home.available else [],
        "eat": [region for region in regions if region.function == "canteen"],
        "study": [region for region in regions if region.function in STUDY_FUNCTIONS],
        "exercise": [
            region
            for region in regions
            if region.function in EXERCISE_FUNCTIONS or region.terrain == "sports_field"
        ],
        "social": [
            region
            for region in regions
            if region.function in SOCIAL_FUNCTIONS or region.terrain == "sports_field"
        ],
        "service": [region for region in regions if region.function in SERVICE_FUNCTIONS],
    }
    return by_activity


def _utility(
    activity: str,
    profile: StudentProfile,
    trait: StudentTrait,
    state: StudentState,
    context: StudentContext,
    *,
    second_of_day: int,
    distance: int,
    rng: random.Random,
) -> tuple[float, str]:
    base = {
        "sleep": -0.15,
        "rest": 0.05,
        "eat": 0.10,
        "study": 0.30,
        "exercise": -0.10,
        "social": 0.00,
        "service": -1.10,
    }.get(activity, 0.0)

    if activity == "eat":
        need = 3.2 * (1.0 - state.satiety)
        preference = 0.0
    elif activity in {"sleep", "rest"}:
        need = 2.8 * (1.0 - state.energy)
        preference = 0.0
    elif activity == "study":
        need = 1.4 * trait.interests.get("study", 0.5) - 0.8 * (1.0 - trait.mental_health)
        preference = 0.25 * trait.interests.get("study", 0.5)
    elif activity == "exercise":
        need = 1.5 * trait.interests.get("exercise", 0.5) * state.energy - 0.6 * (1.0 - state.satiety)
        preference = 0.30 * trait.interests.get("exercise", 0.5)
    elif activity == "social":
        social_interest = max(trait.interests.get("music", 0.5), trait.interests.get("game", 0.5))
        need = 1.6 * social_interest * (1.0 - state.social_return)
        preference = 0.25 * social_interest
    elif activity == "service":
        need = (
            3.6 * max(1.0 - trait.physical_health, 0.0)
            + 0.8 * max((1.0 - trait.mental_health) - 0.65, 0.0)
            + 0.7 * max(0.25 - state.energy, 0.0)
            + 0.7 * max(0.25 - state.satiety, 0.0)
            + (2.0 if trait.physical_health <= MEDICAL_URGENT_HEALTH_THRESHOLD else 0.0)
        )
        preference = 0.0
    else:
        need = 0.0
        preference = 0.0

    time_score = _time_score(activity, second_of_day)
    distance_score = -0.015 * distance
    inertia = 0.6 if context.current_action == activity else 0.0
    noise = rng.uniform(-0.15, 0.15)
    utility = base + need + preference + time_score + distance_score + inertia + noise
    reason = (
        f"activity={activity} utility={utility:.3f} base={base:.2f} need={need:.2f} "
        f"pref={preference:.2f} time={time_score:.2f} distance={distance_score:.2f} "
        f"inertia={inertia:.2f} noise={noise:.2f}"
    )
    return utility, reason


def _time_score(activity: str, second_of_day: int) -> float:
    if activity == "sleep" and (_in_window(second_of_day, "23:00", "23:59:59") or _in_window(second_of_day, "00:00", "07:00")):
        return 3.0
    if activity == "eat" and (
        _in_window(second_of_day, "06:30", "08:30")
        or _in_window(second_of_day, "11:30", "13:30")
        or _in_window(second_of_day, "17:30", "19:30")
    ):
        return 2.2
    if activity == "study" and _in_window(second_of_day, "08:00", "17:30"):
        return 1.2
    if activity in {"exercise", "social"} and _in_window(second_of_day, "17:00", "21:30"):
        return 0.9
    return 0.0


def _region_open(region: Region, second_of_day: int) -> bool:
    return _in_window(second_of_day, region.open_time, region.close_time)


def _in_window(second_of_day: int, start: str, end: str) -> bool:
    start_second = parse_time_to_seconds(start)
    end_second = parse_time_to_seconds(end)
    if start_second <= end_second:
        return start_second <= second_of_day <= end_second
    return second_of_day >= start_second or second_of_day <= end_second


def _softmax_pick(
    candidates: Iterable[ActivityCandidate],
    temperature: float,
    rng: random.Random,
) -> ActivityCandidate:
    choices = list(candidates)
    top = max(candidate.utility for candidate in choices)
    weights = [math.exp((candidate.utility - top) / temperature) for candidate in choices]
    total = sum(weights)
    draw = rng.random() * total
    running = 0.0
    for candidate, weight in zip(choices, weights):
        running += weight
        if draw <= running:
            return candidate
    return choices[-1]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
