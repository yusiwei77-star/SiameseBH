from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..core.types import StudentContext, StudentState, StudentTrait


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class InnerMindConfig:
    intrinsic_decay_per_hour: float = 0.12
    flow_rates_per_hour: dict[str, float] = field(
        default_factory=lambda: {"study": 1.0, "exercise": 1.15, "music": 1.05, "game": 1.30}
    )
    skill_rates_per_hour: dict[str, float] = field(
        default_factory=lambda: {"study": 0.035, "exercise": 0.025, "music": 0.030, "game": 0.035}
    )
    energy_cost_per_hour: dict[str, float] = field(
        default_factory=lambda: {"study": 0.09, "exercise": 0.22, "music": 0.015, "game": 0.06}
    )
    exercise_health_gain_per_hour: float = 0.025
    mental_recovery_per_hour: float = 0.030
    high_satisfaction_recovery_per_hour: float = 0.018
    mental_damage_per_hour: float = 0.035
    body_damage_per_hour: float = 0.040
    satisfaction_recovery_threshold: float = 0.65
    bad_body_threshold: float = 0.25


@dataclass(frozen=True)
class InnerMindDelta:
    energy: float = 0.0
    intrinsic_satisfaction: float = 0.0
    extrinsic_satisfaction: float = 0.0
    mental_health: float = 0.0
    physical_health: float = 0.0
    pleasure: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0
    skill_key: str | None = None
    skill_delta: float = 0.0


class InnerMindDynamics:
    """Equations for study, exercise, music, and game activities."""

    def __init__(self, config: InnerMindConfig | None = None) -> None:
        self.config = config or InnerMindConfig()

    def advance(
        self,
        trait: StudentTrait,
        state: StudentState,
        context: StudentContext,
        seconds: int,
    ) -> InnerMindDelta:
        hours = max(0, seconds) / 3600.0
        action = context.current_action
        if action == "study":
            return self.study(trait, state, hours)
        if action == "exercise":
            return self.exercise(trait, state, hours)
        if action == "music":
            return self.music(trait, state, hours)
        if action == "game":
            return self.game(trait, state, hours)
        return self.idle(state, hours)

    def study(self, trait: StudentTrait, state: StudentState, hours: float) -> InnerMindDelta:
        return self._activity(trait, state, "study", hours)

    def exercise(self, trait: StudentTrait, state: StudentState, hours: float) -> InnerMindDelta:
        return self._activity(trait, state, "exercise", hours)

    def music(self, trait: StudentTrait, state: StudentState, hours: float) -> InnerMindDelta:
        return self._activity(trait, state, "music", hours)

    def game(self, trait: StudentTrait, state: StudentState, hours: float) -> InnerMindDelta:
        return self._activity(trait, state, "game", hours)

    def idle(self, state: StudentState, hours: float) -> InnerMindDelta:
        before_intrinsic = state.intrinsic_satisfaction
        before_pleasure = state.emotion.get("pleasure", 0.5)
        if hours > 0:
            state.intrinsic_satisfaction = _clamp01(
                state.intrinsic_satisfaction * math.exp(-self.config.intrinsic_decay_per_hour * hours)
            )
        state.emotion["pleasure"] = state.intrinsic_satisfaction
        return InnerMindDelta(
            intrinsic_satisfaction=state.intrinsic_satisfaction - before_intrinsic,
            pleasure=state.emotion["pleasure"] - before_pleasure,
        )

    def _activity(
        self,
        trait: StudentTrait,
        state: StudentState,
        action: str,
        hours: float,
    ) -> InnerMindDelta:
        before_energy = state.energy
        before_intrinsic = state.intrinsic_satisfaction
        before_mental = trait.mental_health
        before_health = trait.physical_health
        before_skill = trait.skills.get(action, 0.5)
        before_pleasure = state.emotion.get("pleasure", 0.5)
        before_arousal = state.emotion.get("arousal", 0.3)
        before_dominance = state.emotion.get("dominance", 0.5)

        self._update_intrinsic_satisfaction(trait, state, action, before_skill, hours)
        self._update_skill(trait, action, before_skill, hours)
        self._update_energy(state, action, hours)
        self._update_physical_health(trait, state, action, hours)
        self._update_mental_health(trait, state, action, before_skill, before_mental, hours)
        self._project_pad(trait, state, action)

        return InnerMindDelta(
            energy=state.energy - before_energy,
            intrinsic_satisfaction=state.intrinsic_satisfaction - before_intrinsic,
            mental_health=trait.mental_health - before_mental,
            physical_health=trait.physical_health - before_health,
            pleasure=state.emotion.get("pleasure", 0.5) - before_pleasure,
            arousal=state.emotion.get("arousal", 0.3) - before_arousal,
            dominance=state.emotion.get("dominance", 0.5) - before_dominance,
            skill_key=action,
            skill_delta=trait.skills[action] - before_skill,
        )

    def _update_intrinsic_satisfaction(
        self,
        trait: StudentTrait,
        state: StudentState,
        action: str,
        skill: float,
        hours: float,
    ) -> None:
        target = _clamp01(trait.interests.get(action, 0.5) * trait.mental_health)
        flow_rate = self._flow_rate(trait, action, skill)
        decay = math.exp(-flow_rate * max(0.0, hours))
        state.intrinsic_satisfaction = _clamp01(target - (target - state.intrinsic_satisfaction) * decay)

    def _update_skill(self, trait: StudentTrait, action: str, skill: float, hours: float) -> None:
        skill_rate = self._skill_rate(trait, action)
        decay = math.exp(-skill_rate * max(0.0, hours))
        trait.skills[action] = _clamp01(1.0 - (1.0 - _clamp01(skill)) * decay)

    def _update_energy(self, state: StudentState, action: str, hours: float) -> None:
        cost = self.config.energy_cost_per_hour.get(action, 0.0)
        state.energy = _clamp01(state.energy - cost * max(0.0, hours))

    def _update_physical_health(self, trait: StudentTrait, state: StudentState, action: str, hours: float) -> None:
        if action != "exercise":
            return
        readiness = _clamp01((state.energy + state.satiety) * 0.5)
        rate = self.config.exercise_health_gain_per_hour * readiness
        decay = math.exp(-rate * max(0.0, hours))
        trait.physical_health = _clamp01(1.0 - (1.0 - trait.physical_health) * decay)

    def _update_mental_health(
        self,
        trait: StudentTrait,
        state: StudentState,
        action: str,
        skill: float,
        before_mental: float,
        hours: float,
    ) -> None:
        neuroticism = _clamp01(trait.personality.get("neuroticism", 0.3))
        recovery = self._mental_recovery(action, trait, state) * hours
        damage = self._mental_damage(action, state, skill, neuroticism) * hours
        trait.mental_health = _clamp01(before_mental + recovery - damage)

    def _mental_recovery(self, action: str, trait: StudentTrait, state: StudentState) -> float:
        high_satisfaction = max(0.0, state.intrinsic_satisfaction - self.config.satisfaction_recovery_threshold)
        recovery = self.config.high_satisfaction_recovery_per_hour * high_satisfaction
        if action in {"exercise", "music"}:
            recovery += self.config.mental_recovery_per_hour * trait.interests.get(action, 0.5)
        return recovery

    def _mental_damage(self, action: str, state: StudentState, skill: float, neuroticism: float) -> float:
        low_body = max(
            0.0,
            self.config.bad_body_threshold - min(_clamp01(state.energy), _clamp01(state.satiety)),
        ) / max(1e-9, self.config.bad_body_threshold)
        damage = self.config.body_damage_per_hour * low_body * (1.0 + neuroticism)
        if action == "study":
            readiness = _clamp01((state.energy + state.satiety) * 0.5)
            frustration = (1.0 - _clamp01(skill)) * (1.0 - readiness) * (1.0 + neuroticism)
            damage += self.config.mental_damage_per_hour * frustration
        return damage

    def _project_pad(self, trait: StudentTrait, state: StudentState, action: str) -> None:
        skill = _clamp01(trait.skills.get(action, 0.5))
        state.emotion["pleasure"] = state.intrinsic_satisfaction
        state.emotion["arousal"] = self._arousal_target(action, skill)
        state.emotion["dominance"] = skill

    def _arousal_target(self, action: str, skill: float) -> float:
        if action == "exercise":
            return 0.80
        if action == "game":
            return 0.75
        if action == "music":
            return 0.20
        if action == "study":
            if skill < 0.35:
                return 0.78
            return 0.50
        return 0.35

    def _flow_rate(self, trait: StudentTrait, action: str, skill: float) -> float:
        base = self.config.flow_rates_per_hour.get(action, 1.0)
        rate = base * (1.0 + _clamp01(skill))
        if action == "study":
            rate *= 1.0 + _clamp01(trait.personality.get("conscientiousness", 0.5))
        return rate

    def _skill_rate(self, trait: StudentTrait, action: str) -> float:
        base = self.config.skill_rates_per_hour.get(action, 0.0)
        if action == "study":
            conscientiousness = _clamp01(trait.personality.get("conscientiousness", 0.5))
            openness = _clamp01(trait.personality.get("openness", 0.5))
            return base * (1.0 + conscientiousness + openness)
        return base


DEFAULT_INNER_MIND_DYNAMICS = InnerMindDynamics()
