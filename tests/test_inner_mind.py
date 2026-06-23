from __future__ import annotations

import math
import unittest

from abm.agent.rules import update_needs
from abm.environment import InnerMindDynamics
from tests.helpers import make_profile, make_state, make_trait, make_variable


class InnerMindDynamicsTest(unittest.TestCase):
    def test_idle_intrinsic_satisfaction_decays_to_boredom(self) -> None:
        dynamics = InnerMindDynamics()
        state = make_state(intrinsic_satisfaction=0.8)

        dynamics.idle(state, 1.0)

        self.assertAlmostEqual(
            state.intrinsic_satisfaction,
            0.8 * math.exp(-dynamics.config.intrinsic_decay_per_hour),
        )
        self.assertEqual(state.emotion["pleasure"], state.intrinsic_satisfaction)

    def test_skill_raises_flow_speed_for_game(self) -> None:
        dynamics = InnerMindDynamics()
        low_skill_trait = make_trait(game=0.9, game_skill=0.1, stress=0.1)
        high_skill_trait = make_trait(game=0.9, game_skill=0.8, stress=0.1)
        low_skill_state = make_state(intrinsic_satisfaction=0.1)
        high_skill_state = make_state(intrinsic_satisfaction=0.1)

        dynamics.game(low_skill_trait, low_skill_state, 0.25)
        dynamics.game(high_skill_trait, high_skill_state, 0.25)

        self.assertGreater(high_skill_state.intrinsic_satisfaction, low_skill_state.intrinsic_satisfaction)

    def test_conscientiousness_accelerates_study_skill_growth(self) -> None:
        dynamics = InnerMindDynamics()
        low_c = make_trait(study=0.8, study_skill=0.3, conscientiousness=0.1)
        high_c = make_trait(study=0.8, study_skill=0.3, conscientiousness=0.9)
        low_c_state = make_state(energy=0.9, satiety=0.9, intrinsic_satisfaction=0.2)
        high_c_state = make_state(energy=0.9, satiety=0.9, intrinsic_satisfaction=0.2)

        dynamics.study(low_c, low_c_state, 1.0)
        dynamics.study(high_c, high_c_state, 1.0)

        self.assertGreater(high_c.skills["study"], low_c.skills["study"])

    def test_study_frustration_and_bad_body_damage_mental_health(self) -> None:
        dynamics = InnerMindDynamics()
        trait = make_trait(stress=0.1, study=0.8, study_skill=0.1)
        state = make_state(energy=0.12, satiety=0.12, intrinsic_satisfaction=0.1)
        before = trait.mental_health

        dynamics.study(trait, state, 1.0)

        self.assertLess(trait.mental_health, before)

    def test_exercise_costs_more_energy_but_recovers_health(self) -> None:
        dynamics = InnerMindDynamics()
        exercise_trait = make_trait(exercise=0.9, exercise_skill=0.5, health=0.5, stress=0.4)
        music_trait = make_trait(music=0.9, music_skill=0.5, health=0.5, stress=0.4)
        exercise_state = make_state(energy=0.9, satiety=0.9, intrinsic_satisfaction=0.2)
        music_state = make_state(energy=0.9, satiety=0.9, intrinsic_satisfaction=0.2)

        dynamics.exercise(exercise_trait, exercise_state, 1.0)
        dynamics.music(music_trait, music_state, 1.0)

        self.assertLess(exercise_state.energy, music_state.energy)
        self.assertGreater(exercise_trait.physical_health, 0.5)
        self.assertGreater(exercise_trait.mental_health, 0.6)
        self.assertGreater(music_trait.mental_health, 0.6)

    def test_pad_projection_uses_intrinsic_activity_and_skill(self) -> None:
        dynamics = InnerMindDynamics()
        game_trait = make_trait(game=0.9, game_skill=0.7, stress=0.1)
        game_state = make_state(intrinsic_satisfaction=0.2)
        music_trait = make_trait(music=0.9, music_skill=0.4, stress=0.1)
        music_state = make_state(intrinsic_satisfaction=0.2)

        dynamics.game(game_trait, game_state, 0.5)
        dynamics.music(music_trait, music_state, 0.5)

        self.assertEqual(game_state.emotion["pleasure"], game_state.intrinsic_satisfaction)
        self.assertEqual(game_state.emotion["arousal"], 0.75)
        self.assertAlmostEqual(game_state.emotion["dominance"], game_trait.skills["game"])
        self.assertEqual(music_state.emotion["arousal"], 0.20)

    def test_update_needs_runs_inner_mind_activity(self) -> None:
        profile = make_profile()
        trait = make_trait(game=0.9, game_skill=0.3, stress=0.2)
        state = make_state(energy=0.9, satiety=0.9, intrinsic_satisfaction=0.1)
        context = make_variable(current_action="game")

        update_needs(profile, trait, state, context, 1800)

        self.assertGreater(trait.skills["game"], 0.3)
        self.assertGreater(state.intrinsic_satisfaction, 0.1)
        self.assertLess(state.energy, 0.9)


if __name__ == "__main__":
    unittest.main()
