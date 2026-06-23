from __future__ import annotations

import math
import unittest

from abm.environment import MaterialConfig, MaterialDynamics
from abm.model.daily import StudentDailyModel
from tests.helpers import make_profile, make_state, make_trait, make_variable


class MaterialDynamicsTest(unittest.TestCase):
    def test_faster_meal_speed_shortens_meal_seconds(self) -> None:
        dynamics = MaterialDynamics()
        slow = dynamics.meal_seconds(make_profile(meal_speed=0.8), make_state(satiety=0.2))
        fast = dynamics.meal_seconds(make_profile(meal_speed=1.2), make_state(satiety=0.2))

        self.assertGreater(slow, fast)

    def test_eating_updates_satiety_without_energy_drain(self) -> None:
        dynamics = MaterialDynamics()
        profile = make_profile(meal_speed=1.0)
        state = make_state(satiety=0.6, energy=0.8)
        before_energy = state.energy

        dynamics.eat(profile, state, 3600 / 3600)

        expected = 1.0 - (1.0 - 0.6) * math.exp(-dynamics.config.eating_rate_per_hour)
        self.assertAlmostEqual(state.satiety, expected)
        self.assertEqual(state.energy, before_energy)

    def test_eating_slows_as_satiety_gets_high(self) -> None:
        dynamics = MaterialDynamics()
        profile = make_profile(meal_speed=1.0)
        hungry = make_state(satiety=0.2)
        nearly_full = make_state(satiety=0.8)

        hungry_delta = dynamics.eat(profile, hungry, 5 / 60).satiety
        full_delta = dynamics.eat(profile, nearly_full, 5 / 60).satiety

        self.assertGreater(hungry_delta, full_delta)
        self.assertLess(nearly_full.satiety, 1.0)

    def test_meal_seconds_reaches_target_with_closed_form_solution(self) -> None:
        dynamics = MaterialDynamics()
        profile = make_profile(meal_speed=1.0)
        state = make_state(satiety=0.4)

        seconds = dynamics.meal_seconds(profile, state)
        dynamics.eat(profile, state, seconds / 3600)

        self.assertGreaterEqual(state.satiety, dynamics.config.meal_target_satiety)

    def test_walking_cost_uses_diagonal_distance(self) -> None:
        dynamics = MaterialDynamics(MaterialConfig(walk_energy_cost_per_cell=0.01))
        state = make_state(energy=1.0)

        delta = dynamics.walking_cost(state, (0, 0), (1, 1))

        self.assertAlmostEqual(delta.walked_cells, math.sqrt(2))
        self.assertAlmostEqual(state.energy, 1.0 - 0.01 * math.sqrt(2))

    def test_extreme_hunger_or_exhaustion_damages_physical_health(self) -> None:
        dynamics = MaterialDynamics()
        profile = make_profile()
        trait = make_trait(health=0.8)
        state = make_state(energy=0.8, satiety=0.05)
        context = make_variable()

        delta = dynamics.advance(profile, trait, state, context, 3600)

        pressure = dynamics._low_body_pressure(state.satiety)
        expected = 0.8 - dynamics.config.physical_health_damage_per_hour * pressure
        self.assertAlmostEqual(delta.physical_health, expected - 0.8)
        self.assertAlmostEqual(trait.physical_health, expected)

    def test_good_energy_and_satiety_recover_physical_health_linearly(self) -> None:
        dynamics = MaterialDynamics()
        profile = make_profile()
        trait = make_trait(health=0.8)
        state = make_state(energy=0.8, satiety=0.8)
        context = make_variable()

        delta = dynamics.advance(profile, trait, state, context, 3600)

        readiness = min(
            dynamics._body_recovery_readiness(state.energy),
            dynamics._body_recovery_readiness(state.satiety),
        )
        expected = 0.8 + dynamics.config.physical_health_recover_per_hour * readiness
        self.assertAlmostEqual(delta.physical_health, expected - 0.8)
        self.assertAlmostEqual(trait.physical_health, expected)

    def test_middle_energy_and_satiety_do_not_change_physical_health(self) -> None:
        dynamics = MaterialDynamics()
        profile = make_profile()
        trait = make_trait(health=0.8)
        state = make_state(energy=0.45, satiety=0.45)
        context = make_variable()

        delta = dynamics.advance(profile, trait, state, context, 3600)

        self.assertEqual(delta.physical_health, 0.0)
        self.assertEqual(trait.physical_health, 0.8)

    def test_physical_health_damage_is_faster_than_recovery(self) -> None:
        dynamics = MaterialDynamics()

        self.assertGreater(
            dynamics.config.physical_health_damage_per_hour,
            dynamics.config.physical_health_recover_per_hour,
        )

    def test_eat_activity_uses_remaining_seconds_only(self) -> None:
        model = StudentDailyModel(
            "map/summary.json",
            student_count=1,
            start_time="07:30:00",
            seconds_per_step=1,
            rng=5,
        )
        student = model.students[0]
        region = next(
            region
            for region in model.campus_map.regions_by_id.values()
            if region.function == "canteen" and region.available
        )
        student.context.target_region_id = region.id
        student.state.satiety = 0.4

        student._start_activity("eat")

        self.assertEqual(student.context.action_phase, "eating")
        self.assertGreater(student.context.remaining_action_seconds, 0)
        self.assertFalse(hasattr(student.context, "meal_eating_seconds"))
        self.assertFalse(hasattr(student.context, "meal_satiety_gain_per_hour"))


if __name__ == "__main__":
    unittest.main()
