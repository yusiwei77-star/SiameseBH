from __future__ import annotations

import unittest

from abm.environment_dynamics import update_physiopsychological_state
from abm.agent.rules import should_interrupt
from abm.core.types import parse_time_to_seconds
from tests.helpers import make_state, make_trait, make_variable


class PhysioPsychologicalTest(unittest.TestCase):
    def test_high_stress_accelerates_awake_energy_drain(self) -> None:
        calm_trait = make_trait(stress=0.1)
        anxious_trait = make_trait(stress=0.9)
        calm = make_state(energy=0.8, satiety=0.8)
        anxious = make_state(energy=0.8, satiety=0.8)
        calm_variable = make_variable()
        anxious_variable = make_variable()

        update_physiopsychological_state(calm_trait, calm, calm_variable, 3600, current_second=parse_time_to_seconds("12:00:00"))
        update_physiopsychological_state(anxious_trait, anxious, anxious_variable, 3600, current_second=parse_time_to_seconds("12:00:00"))

        self.assertLess(anxious.energy, calm.energy)

    def test_poor_body_and_social_state_raise_smoothed_stress(self) -> None:
        trait = make_trait(stress=0.1)
        state = make_state(energy=0.1, satiety=0.1, extrinsic_satisfaction=0.2, social_return=0.1)
        context = make_variable()

        update_physiopsychological_state(trait, state, context, 3600, current_second=parse_time_to_seconds("12:00:00"))

        self.assertGreater(1.0 - trait.mental_health, 0.1)
        derived_focus = min(1.0, (state.energy + state.satiety) / 2.0) * trait.mental_health
        self.assertLess(derived_focus, 0.1)

    def test_focus_controls_academic_competence_gain_while_studying(self) -> None:
        focused_trait = make_trait(stress=0.1, study_skill=0.4)
        depleted_trait = make_trait(stress=0.8, study_skill=0.4)
        focused = make_state(energy=0.9, satiety=0.9)
        depleted = make_state(energy=0.1, satiety=0.1)
        focused_variable = make_variable(current_action="study")
        depleted_variable = make_variable(current_action="study")

        update_physiopsychological_state(focused_trait, focused, focused_variable, 3600, current_second=parse_time_to_seconds("12:00:00"))
        update_physiopsychological_state(depleted_trait, depleted, depleted_variable, 3600, current_second=parse_time_to_seconds("12:00:00"))

        self.assertGreater(focused_trait.skills["study"], depleted_trait.skills["study"])
        focused_focus = min(1.0, (focused.energy + focused.satiety) / 2.0) * focused_trait.mental_health
        depleted_focus = min(1.0, (depleted.energy + depleted.satiety) / 2.0) * depleted_trait.mental_health
        self.assertGreater(focused_focus, depleted_focus)

    def test_zero_energy_and_satiety_degrade_health_without_forced_phase_change(self) -> None:
        trait = make_trait(health=0.05, stress=0.5)
        state = make_state(energy=0.0, satiety=0.0)
        context = make_variable()

        update_physiopsychological_state(trait, state, context, 3600, current_second=parse_time_to_seconds("12:00:00"))

        self.assertEqual(trait.physical_health, 0.0)
        self.assertEqual(context.phase, "IDLE")
        self.assertIsNone(context.current_action)

    def test_service_activity_recovers_health_energy_and_stress(self) -> None:
        trait = make_trait(health=0.2, stress=0.7)
        state = make_state(energy=0.3, satiety=0.8, extrinsic_satisfaction=0.5)
        context = make_variable(phase="ACTIVITY", current_action="service")

        update_physiopsychological_state(trait, state, context, 3600, current_second=parse_time_to_seconds("12:00:00"))

        self.assertGreater(trait.physical_health, 0.2)
        self.assertGreater(state.energy, 0.3)
        self.assertLess(1.0 - trait.mental_health, 0.7)

    def test_low_health_interrupts_non_service_activity_only(self) -> None:
        studying_trait = make_trait(health=0.1)
        in_service_trait = make_trait(health=0.1)
        studying = make_state(energy=0.8, satiety=0.8)
        in_service = make_state(energy=0.8, satiety=0.8)
        studying_variable = make_variable(phase="ACTIVITY", current_action="study")
        in_service_variable = make_variable(phase="ACTIVITY", current_action="service")

        self.assertTrue(should_interrupt(studying_trait, studying, studying_variable, object(), parse_time_to_seconds("12:00:00")))  # type: ignore[arg-type]
        self.assertFalse(should_interrupt(in_service_trait, in_service, in_service_variable, object(), parse_time_to_seconds("12:00:00")))  # type: ignore[arg-type]

    def test_stress_reduces_sleep_energy_recovery(self) -> None:
        calm_trait = make_trait(stress=0.0)
        anxious_trait = make_trait(stress=0.9)
        calm = make_state(energy=0.2)
        anxious = make_state(energy=0.2)
        calm_variable = make_variable(current_action="sleep")
        anxious_variable = make_variable(current_action="sleep")

        update_physiopsychological_state(calm_trait, calm, calm_variable, 3600, current_second=parse_time_to_seconds("23:00:00"))
        update_physiopsychological_state(anxious_trait, anxious, anxious_variable, 3600, current_second=parse_time_to_seconds("23:00:00"))

        self.assertGreater(calm.energy, anxious.energy)
        self.assertGreater(calm_variable.current_sleep_energy_gain_per_hour, anxious_variable.current_sleep_energy_gain_per_hour)


if __name__ == "__main__":
    unittest.main()
