from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.map import Pos
from ..core.types import StudentContext, StudentProfile, StudentState, StudentTrait


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True)
class MaterialConfig:
    walk_energy_cost_per_cell: float = 0.0015
    awake_energy_drain_per_hour: float = 0.055
    awake_satiety_drain_per_hour: float = 0.11
    sleep_energy_gain_per_hour: float = 0.45
    sleep_satiety_drain_per_hour: float = 0.04
    meal_target_satiety: float = 0.95
    eating_rate_per_hour: float = 5.0
    health_damage_start: float = 0.25
    health_recover_start: float = 0.55
    physical_health_damage_per_hour: float = 0.05
    physical_health_recover_per_hour: float = 0.01


@dataclass(frozen=True)
class MaterialDelta:
    energy: float = 0.0
    satiety: float = 0.0
    physical_health: float = 0.0
    walked_cells: float = 0.0


class MaterialDynamics:
    """Equations for walking, eating, sleeping, and basic body state."""

    def __init__(self, config: MaterialConfig | None = None) -> None:
        self.config = config or MaterialConfig()

    def advance(
        self,
        profile: StudentProfile,
        trait: StudentTrait,
        state: StudentState,
        context: StudentContext,
        seconds: int,
    ) -> MaterialDelta:
        hours = max(0, seconds) / 3600.0
        action = context.current_action
        if action == "sleep":
            delta = self.sleep(state, hours)
        elif action == "eat":
            delta = self.eat(profile, state, hours)
        else:
            delta = self.awake_drain(state, hours)

        health_delta = self.physical_health_drift(trait, state, hours)
        return MaterialDelta(
            energy=delta.energy,
            satiety=delta.satiety,
            physical_health=health_delta.physical_health,
            walked_cells=delta.walked_cells,
        )

    def awake_drain(self, state: StudentState, hours: float) -> MaterialDelta:
        before_energy = state.energy
        before_satiety = state.satiety
        state.energy = _clamp01(state.energy - self.config.awake_energy_drain_per_hour * hours)
        state.satiety = _clamp01(state.satiety - self.config.awake_satiety_drain_per_hour * hours)
        return MaterialDelta(energy=state.energy - before_energy, satiety=state.satiety - before_satiety)

    def sleep(self, state: StudentState, hours: float) -> MaterialDelta:
        before_energy = state.energy
        before_satiety = state.satiety
        state.energy = _clamp01(state.energy + self.config.sleep_energy_gain_per_hour * hours)
        state.satiety = _clamp01(state.satiety - self.config.sleep_satiety_drain_per_hour * hours)
        return MaterialDelta(energy=state.energy - before_energy, satiety=state.satiety - before_satiety)

    def eat(self, profile: StudentProfile, state: StudentState, hours: float) -> MaterialDelta:
        before = state.satiety
        decay = math.exp(-self.eating_rate_per_hour(profile) * max(0.0, hours))
        state.satiety = _clamp01(1.0 - (1.0 - _clamp01(state.satiety)) * decay)
        return MaterialDelta(satiety=state.satiety - before)

    def eating_rate_per_hour(self, profile: StudentProfile) -> float:
        return self.config.eating_rate_per_hour * max(0.1, profile.normal_meal_speed)

    def meal_seconds(self, profile: StudentProfile, state: StudentState) -> int:
        current = _clamp01(state.satiety)
        target = _clamp01(self.config.meal_target_satiety)
        if current >= target:
            return 0
        if target >= 1.0:
            target = 1.0 - 1e-9
        remaining_ratio = (1.0 - target) / max(1e-9, 1.0 - current)
        hours = -math.log(remaining_ratio) / self.eating_rate_per_hour(profile)
        return max(1, math.ceil(hours * 3600))

    def physical_health_drift(self, trait: StudentTrait, state: StudentState, hours: float) -> MaterialDelta:
        before = trait.physical_health
        hours = max(0.0, hours)
        damage_pressure = max(
            self._low_body_pressure(state.satiety),
            self._low_body_pressure(state.energy),
        )
        recovery_readiness = min(
            self._body_recovery_readiness(state.satiety),
            self._body_recovery_readiness(state.energy),
        )
        if damage_pressure > 0.0:
            trait.physical_health = _clamp01(
                trait.physical_health - self.config.physical_health_damage_per_hour * damage_pressure * hours
            )
        elif recovery_readiness > 0.0:
            trait.physical_health = _clamp01(
                trait.physical_health + self.config.physical_health_recover_per_hour * recovery_readiness * hours
            )
        return MaterialDelta(physical_health=trait.physical_health - before)

    def _low_body_pressure(self, value: float) -> float:
        value = _clamp01(value)
        threshold = self.config.health_damage_start
        if value >= threshold:
            return 0.0
        return ((threshold - value) / max(1e-9, threshold)) ** 2

    def _body_recovery_readiness(self, value: float) -> float:
        value = _clamp01(value)
        threshold = self.config.health_recover_start
        if value <= threshold:
            return 0.0
        return (value - threshold) / max(1e-9, 1.0 - threshold)

    def walking_cost(self, state: StudentState, from_pos: Pos, to_pos: Pos) -> MaterialDelta:
        distance = math.hypot(to_pos[0] - from_pos[0], to_pos[1] - from_pos[1])
        before = state.energy
        state.energy = _clamp01(state.energy - self.config.walk_energy_cost_per_cell * distance)
        return MaterialDelta(energy=state.energy - before, walked_cells=distance)


DEFAULT_MATERIAL_DYNAMICS = MaterialDynamics()
