"""Rule-based policy for daily student behavior."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable

from ..core.types import SECONDS_PER_DAY, StudentProfile, StudentState, StudentTrait, StudentContext


ACTIONS = ("sleep", "rest", "eat", "study", "exercise", "social", "service")


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    scores: dict[str, float]
    reason: str


@dataclass(frozen=True)
class InvitationResponse:
    accepted: bool
    score: float
    reason: str


@dataclass(frozen=True)
class StudentPolicyConfig:
    low_energy_threshold: float = 0.28
    low_satiety_threshold: float = 0.30
    low_health_threshold: float = 0.35
    urgent_health_threshold: float = 0.18
    high_stress_threshold: float = 0.70
    course_priority_bonus: float = 4.0
    meal_time_bonus: float = 0.85
    night_sleep_bonus: float = 1.25
    evening_social_bonus: float = 0.45
    invitation_accept_threshold: float = 0.58


class RuleBasedStudentPolicy:
    """Deterministic, interpretable policy for dynamics sanity checks."""

    def __init__(self, config: StudentPolicyConfig | None = None, *, rng: int | None = None) -> None:
        self.config = config or StudentPolicyConfig()
        self.rng = random.Random(rng)

    def score_actions(
        self,
        profile: StudentProfile,
        trait: StudentTrait,
        state: StudentState,
        context: StudentContext,
        *,
        second_of_day: int,
    ) -> dict[str, float]:
        second = second_of_day % SECONDS_PER_DAY
        meal_time = _meal_time(second)
        night = _night_time(second)
        daytime = _daytime(second)
        evening = _evening_time(second)

        energy_need = 1.0 - _clamp01(state.energy)
        satiety_need = 1.0 - _clamp01(state.satiety)
        health_need = 1.0 - _clamp01(trait.physical_health)
        social_need = _clamp01(max(1.0 - state.social_return, state.social_contribution))
        study_skill = _clamp01(trait.skills.get("study", 0.5))
        stress = 1.0 - _clamp01(trait.mental_health)
        study_interest = _clamp01(trait.interests.get("study", 0.5))
        exercise_interest = _clamp01(trait.interests.get("exercise", 0.5))
        leisure_interest = _clamp01(
            (trait.interests.get("music", 0.5) + trait.interests.get("game", 0.5)) / 2.0
        )

        scores = {action: -0.25 for action in ACTIONS}
        scores["eat"] = (
            2.9 * satiety_need
            + (self.config.meal_time_bonus if meal_time else 0.0)
            + 0.25 * stress
            - (0.85 if state.satiety > 0.82 else 0.0)
        )
        scores["sleep"] = (
            2.7 * energy_need
            + (self.config.night_sleep_bonus if night else -0.55)
            + 0.35 * stress
            - (0.45 if state.satiety < self.config.low_satiety_threshold else 0.0)
        )
        scores["rest"] = (
            1.45 * energy_need
            + 0.95 * stress
            + (0.35 if state.energy < 0.55 else 0.0)
            - (0.30 if meal_time and state.satiety < 0.55 else 0.0)
        )
        scores["study"] = (
            0.95 * study_interest
            + 0.70 * study_skill
            + 0.85 * _clamp01(1.0 - state.extrinsic_satisfaction)
            + (0.45 if daytime else -0.25)
            - 0.80 * stress
            - (0.65 if state.energy < self.config.low_energy_threshold else 0.0)
            - (0.40 if state.satiety < self.config.low_satiety_threshold else 0.0)
        )
        scores["exercise"] = (
            1.25 * exercise_interest
            + 0.90 * _clamp01(state.energy)
            + (0.55 if evening else 0.0)
            - 0.75 * stress
            - (1.15 if state.energy < 0.45 else 0.0)
            - (1.05 if state.satiety < 0.45 else 0.0)
        )
        scores["social"] = (
            1.25 * leisure_interest
            + 1.35 * social_need
            + (self.config.evening_social_bonus if evening else 0.0)
            - 0.55 * stress
            - (0.55 if state.energy < self.config.low_energy_threshold else 0.0)
        )
        scores["service"] = (
            2.8 * health_need
            + (1.6 if trait.physical_health < self.config.low_health_threshold else 0.0)
            + (1.2 if trait.physical_health < self.config.urgent_health_threshold else 0.0)
            + (0.8 if state.energy < 0.12 or state.satiety < 0.12 else 0.0)
            + (0.7 if stress > self.config.high_stress_threshold else 0.0)
        )
        return scores

    def choose_action(
        self,
        profile: StudentProfile,
        trait: StudentTrait,
        state: StudentState,
        context: StudentContext,
        *,
        second_of_day: int,
        legal_actions: Iterable[str],
        rng: random.Random,
    ) -> PolicyDecision | None:
        legal_set = set(legal_actions)
        legal = [action for action in ACTIONS if action in legal_set]
        if not legal:
            return None

        scores = self.score_actions(profile, trait, state, context, second_of_day=second_of_day)
        action = max(legal, key=lambda item: scores[item])
        reason = f"policy=rule_based action={action} score={scores[action]:.3f}"
        return PolicyDecision(action=action, scores=scores, reason=reason)

    def choose_invitation_response(
        self,
        profile: StudentProfile,
        trait: StudentTrait,
        state: StudentState,
        context: StudentContext,
        *,
        invitation: dict[str, object],
        intimacy: float,
        second_of_day: int,
        rng: random.Random,
    ) -> InvitationResponse:
        if context.phase == "ACTIVITY" and context.current_action:
            return InvitationResponse(False, -1.0, "policy_reject_current_activity")
        if trait.physical_health <= self.config.urgent_health_threshold:
            return InvitationResponse(False, -1.0, "policy_reject_medical_need")

        action = str(invitation.get("action", ""))
        stress = 1.0 - _clamp01(trait.mental_health)
        score = (
            0.45 * _clamp01(intimacy)
            + 0.30 * (1.0 - _clamp01(state.satiety))
            + 0.18 * _clamp01(
                (trait.interests.get("music", 0.5) + trait.interests.get("game", 0.5)) / 2.0
            )
            + 0.14 * _clamp01(1.0 - state.social_return)
            + (0.12 if _meal_time(second_of_day % SECONDS_PER_DAY) else 0.0)
            + (0.08 if action == "Invite_to_Eat" else -0.25)
            - 0.20 * stress
        )
        accepted = score >= self.config.invitation_accept_threshold
        reason = (
            f"policy_{'accept' if accepted else 'reject'} "
            f"score={score:.3f} threshold={self.config.invitation_accept_threshold:.3f} "
            f"intimacy={intimacy:.3f}"
        )
        return InvitationResponse(accepted, score, reason)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _in_window(second: int, start: int, end: int) -> bool:
    if start <= end:
        return start <= second <= end
    return second >= start or second <= end


def _meal_time(second: int) -> bool:
    return (
        _in_window(second, 6 * 3600 + 30 * 60, 8 * 3600 + 30 * 60)
        or _in_window(second, 11 * 3600 + 30 * 60, 13 * 3600 + 30 * 60)
        or _in_window(second, 17 * 3600 + 30 * 60, 19 * 3600 + 30 * 60)
    )


def _night_time(second: int) -> bool:
    return _in_window(second, 22 * 3600, 7 * 3600)


def _daytime(second: int) -> bool:
    return _in_window(second, 8 * 3600, 18 * 3600)


def _evening_time(second: int) -> bool:
    return _in_window(second, 17 * 3600, 22 * 3600)
