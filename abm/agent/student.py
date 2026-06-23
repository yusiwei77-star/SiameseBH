"""Daily student agent behavior and snapshot serialization."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from mesa import Agent

from ..environment import DEFAULT_MATERIAL_DYNAMICS
from ..core.movement import step_distance
from ..core.types import (
    StudentProfile,
    StudentState,
    StudentTrait,
    StudentContext,
    pos_payload,
)
from .rules import (
    activity_duration,
    available_actions,
    build_candidates,
    should_interrupt,
    update_needs,
)

if TYPE_CHECKING:
    from ..model.daily import StudentDailyModel


class DailyStudentAgent(Agent):
    """A student whose destinations are selected from needs, preferences, and time."""

    def __init__(
        self,
        model: "StudentDailyModel",
        profile: StudentProfile,
        trait: StudentTrait,
        state: StudentState,
        context: StudentContext,
        *,
        rng: random.Random,
    ) -> None:
        super().__init__(model)
        self.profile = profile
        self.trait = trait
        self.state = state
        self.context = context
        self.behavior_rng = rng

    def step(self) -> None:
        self._update_activity_phase()
        update_needs(
            self.profile,
            self.trait,
            self.state,
            self.context,
            self.model.seconds_per_step,
            current_second=self.model.current_second,
        )

        if self.context.phase == "MOVING":
            self._advance_path()
            return

        if self.context.phase == "ACTIVITY":
            if should_interrupt(self.trait, self.state, self.context, self.model.campus_map, self.model.second_of_day):
                self._clear_activity("interrupted_by_hard_constraint")
            else:
                self.context.remaining_action_seconds -= self.model.seconds_per_step
                self._update_activity_phase()
                if self.context.remaining_action_seconds > 0:
                    return
                self._clear_activity("activity_finished")

        self._decide_next_action()
        if self.context.phase == "MOVING":
            self._advance_path()

    def snapshot(self, *, include_last_path: bool = True, include_path: bool = True) -> dict[str, object]:
        target_region = (
            self.model.campus_map.regions_by_id.get(self.context.target_region_id)
            if self.context.target_region_id
            else None
        )
        home_region = self.model.campus_map.regions_by_id.get(self.profile.home or "")
        return {
            "id": self.unique_id,
            "time": self.model.current_time,
            "elapsed_seconds": self.model.elapsed_seconds,
            "second_of_day": self.model.second_of_day,
            "day": self.model.day,
            "profile": {
                "name": self.profile.name,
                "gender": self.profile.gender,
                "home": self.profile.home,
                "origin_name": home_region.name if home_region else "",
                "workplace": self.profile.workplace,
                "normal_meal_speed": self.profile.normal_meal_speed,
                "normal_walk_speed_cells_per_step": self.profile.normal_walk_speed_cells_per_step,
            },
            "trait": {
                "personality": dict(self.trait.personality),
                "wellbeing": self.trait.wellbeing,
                "interests": dict(self.trait.interests),
                "skills": dict(self.trait.skills),
                "physical_health": self.trait.physical_health,
                "mental_health": self.trait.mental_health,
            },
            "state": {
                "emotion": dict(self.state.emotion),
                "satiety": self.state.satiety,
                "energy": self.state.energy,
                "intrinsic_satisfaction": self.state.intrinsic_satisfaction,
                "extrinsic_satisfaction": self.state.extrinsic_satisfaction,
                "social_contribution": self.state.social_contribution,
                "social_return": self.state.social_return,
            },
            "context": {
                "pos": pos_payload(self.context.pos),
                "phase": self.context.phase,
                "path": [pos_payload(pos) for pos in self.context.path] if include_path else [],
                "path_key": self.path_key(),
                "last_path_key": self.last_path_key(),
                "last_path": [pos_payload(pos) for pos in self.context.last_path] if include_last_path else [],
                "path_index": self.context.path_index,
                "current_speed_cells_per_step": self.context.current_speed_cells_per_step,
                "movement_progress": self.context.movement_progress,
                "intention": self.context.intention,
                "target_pos": pos_payload(self.context.target_pos) if self.context.target_pos else None,
                "target_region_id": self.context.target_region_id,
                "target_region_name": target_region.name if target_region else "",
                "current_action": self.context.current_action,
                "last_action": self.context.last_action,
                "action_started_at": self.context.action_started_at,
                "remaining_action_seconds": self.context.remaining_action_seconds,
                "action_phase": self.context.action_phase,
                "reason": self.context.last_decision_reason,
                "path_length": len(self.context.path),
                "reachable": bool(self.context.path),
                "render_motion": self.render_motion(),
            },
            "arrived": False,
        }

    def render_motion(self) -> dict[str, object] | None:
        if self.context.phase != "MOVING" or len(self.context.path) <= 1:
            return None
        distances = self._cumulative_path_distances(self.context.path)
        if not distances:
            return None
        last_index = len(self.context.path) - 1
        path_index = max(0, min(last_index, int(self.context.path_index)))
        if path_index >= last_index:
            return None
        segment_distance = step_distance(self.context.path[path_index], self.context.path[path_index + 1])
        progress = max(0.0, min(float(self.context.movement_progress), segment_distance))
        start_distance = distances[path_index] + progress
        speed = max(0.0, float(self.profile.normal_walk_speed_cells_per_step))
        end_distance = min(distances[-1], start_distance + speed)
        if end_distance <= start_distance + 1e-9:
            return None
        return {
            "path_key": self.path_key(),
            "start_distance": start_distance,
            "end_distance": end_distance,
            "total_distance": distances[-1],
            "start_elapsed_seconds": self.model.elapsed_seconds,
            "end_elapsed_seconds": self.model.elapsed_seconds + self.model.seconds_per_step,
            "phase_after": "ACTIVITY" if end_distance >= distances[-1] - 1e-9 else "MOVING",
        }

    @staticmethod
    def _cumulative_path_distances(path: list[tuple[int, int]]) -> list[float]:
        if not path:
            return []
        distances = [0.0]
        for index in range(1, len(path)):
            distances.append(distances[index - 1] + step_distance(path[index - 1], path[index]))
        return distances

    def path_key(self) -> str:
        return self._path_key(self.context.path, self.context.intention, self.context.target_region_id)

    def last_path_key(self) -> str:
        return self._path_key(self.context.last_path, self.context.last_action, self.context.target_region_id)

    @staticmethod
    def _path_key(path: list[tuple[int, int]], action: str | None, region_id: str | None) -> str:
        if not path:
            return ""
        first = path[0]
        last = path[-1]
        path_hash = 2166136261
        for x, y in path:
            path_hash ^= (int(x) & 0xFFFF) | ((int(y) & 0xFFFF) << 16)
            path_hash = (path_hash * 16777619) & 0xFFFFFFFF
        return (
            f"{action or ''}|{region_id or ''}|"
            f"{len(path)}|{first[0]},{first[1]}|{last[0]},{last[1]}|{path_hash:08x}"
        )

    def _decide_next_action(self) -> None:
        legal_actions = available_actions(
            self.model.campus_map,
            self.profile,
            self.state,
            second_of_day=self.model.second_of_day,
        )
        decision = self.model.policy.choose_action(
            self.profile,
            self.trait,
            self.state,
            self.context,
            second_of_day=self.model.second_of_day,
            legal_actions=legal_actions,
            rng=self.behavior_rng,
        )
        if decision is None:
            self._idle_without_candidate("no_valid_action")
            return

        candidates = build_candidates(
            self.model.campus_map,
            self.profile,
            self.trait,
            self.state,
            self.context,
            second_of_day=self.model.second_of_day,
            rng=self.behavior_rng,
            activities={decision.action},
        )
        if not candidates:
            self._idle_without_candidate(f"no_reachable_candidate action={decision.action}")
            return

        choice = max(candidates, key=lambda candidate: candidate.utility)
        self.context.intention = choice.activity
        self.context.target_pos = choice.target_pos
        self.context.target_region_id = choice.region.id
        self.context.path = list(choice.route.path)
        self.context.path_index = 0
        self.context.current_speed_cells_per_step = self.profile.normal_walk_speed_cells_per_step
        self.context.movement_progress = 0.0
        self.context.last_action = choice.activity
        self.context.last_decision_reason = f"{decision.reason} target={choice.region.id} {choice.reason}"

        if len(self.context.path) <= 1:
            self._start_activity(choice.activity)
        else:
            self.context.phase = "MOVING"
            self.context.current_action = None

    def _idle_without_candidate(self, reason: str) -> None:
        self.context.phase = "IDLE"
        self.context.current_action = None
        self.context.intention = None
        self.context.target_pos = None
        self.context.target_region_id = None
        self.context.path = []
        self.context.path_index = 0
        self.context.current_speed_cells_per_step = 0.0
        self.context.movement_progress = 0.0
        self.context.last_action = None
        self._clear_meal_fields()
        self.context.last_decision_reason = reason

    def _advance_path(self) -> None:
        if self.context.path_index >= len(self.context.path) - 1:
            self._start_activity(self.context.intention or "rest")
            return

        speed = max(0.0, float(self.profile.normal_walk_speed_cells_per_step))
        self.context.current_speed_cells_per_step = speed
        progress = max(0.0, self.context.movement_progress) + speed
        while self.context.path_index < len(self.context.path) - 1:
            current = self.context.path[self.context.path_index]
            next_pos = self.context.path[self.context.path_index + 1]
            segment_distance = step_distance(current, next_pos)
            if progress + 1e-9 < segment_distance:
                self.context.movement_progress = progress
                return

            progress -= segment_distance
            self.context.path_index += 1
            self.context.pos = self.context.path[self.context.path_index]
            self.model.grid.move_agent(self, self.context.pos)
            DEFAULT_MATERIAL_DYNAMICS.walking_cost(self.state, current, next_pos)
            if self.context.path_index >= len(self.context.path) - 1:
                self.context.movement_progress = 0.0
                self._start_activity(self.context.intention or "rest")
                return

        self.context.movement_progress = 0.0

    def _start_activity(self, activity: str) -> None:
        self.context.phase = "ACTIVITY"
        self.context.current_action = activity
        self.context.action_started_at = self.model.current_second
        if len(self.context.path) > 1:
            self.context.last_path = list(self.context.path)
        self.context.path = []
        self.context.path_index = 0
        self.context.current_speed_cells_per_step = 0.0
        self.context.movement_progress = 0.0
        if activity == "eat":
            region = self.model.campus_map.regions_by_id.get(self.context.target_region_id or "")
            if region is None:
                self.context.remaining_action_seconds = activity_duration(activity)
                self._clear_meal_fields()
            else:
                meal_seconds = DEFAULT_MATERIAL_DYNAMICS.meal_seconds(self.profile, self.state)
                self.context.remaining_action_seconds = meal_seconds
                self._update_activity_phase()
                self.context.last_decision_reason = (
                    f"{self.context.last_decision_reason or f'start_{activity}'} "
                    f"meal_seconds={meal_seconds}s"
                )
        else:
            self.context.remaining_action_seconds = activity_duration(activity)
            self._clear_meal_fields()
        self.context.last_decision_reason = self.context.last_decision_reason or f"start_{activity}"

    def _clear_activity(self, reason: str) -> None:
        self.context.phase = "IDLE"
        self.context.current_action = None
        self.context.intention = None
        self.context.target_pos = None
        self.context.target_region_id = None
        self.context.path = []
        self.context.path_index = 0
        self.context.current_speed_cells_per_step = 0.0
        self.context.movement_progress = 0.0
        self.context.remaining_action_seconds = 0
        self.context.action_started_at = None
        self._clear_meal_fields()
        self.context.last_decision_reason = reason

    def _update_activity_phase(self) -> None:
        if self.context.phase != "ACTIVITY" or self.context.current_action != "eat":
            return
        self.context.action_phase = "eating"

    def _clear_meal_fields(self) -> None:
        self.context.action_phase = None
