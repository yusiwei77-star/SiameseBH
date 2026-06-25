from __future__ import annotations

import unittest

from abm.environment import OuterMindDynamics
from tests.helpers import FakeAgent, make_profile, make_state, make_trait, make_variable


def make_social_agent(
    unique_id: int,
    *,
    trait=None,
    state=None,
    action: str | None = "social",
    region: str = "hall_001",
) -> FakeAgent:
    return FakeAgent(
        unique_id=unique_id,
        profile=make_profile(),
        trait=trait or make_trait(),
        state=state or make_state(),
        context=make_variable(phase="ACTIVITY" if action else "IDLE", current_action=action, target_region_id=region),
    )


class OuterMindDynamicsTest(unittest.TestCase):
    def test_interest_compatibility_accelerates_closeness_growth(self) -> None:
        similar_left = make_social_agent(1, trait=make_trait(study=1.0, exercise=0.0, music=0.0, game=0.0))
        similar_right = make_social_agent(2, trait=make_trait(study=1.0, exercise=0.0, music=0.0, game=0.0))
        different_left = make_social_agent(3, trait=make_trait(study=1.0, exercise=0.0, music=0.0, game=0.0))
        different_right = make_social_agent(4, trait=make_trait(study=0.0, exercise=0.0, music=0.0, game=1.0))
        similar = OuterMindDynamics()
        different = OuterMindDynamics()

        similar.advance([similar_left, similar_right], 3600)
        different.advance([different_left, different_right], 3600)

        self.assertGreater(similar.closeness(1, 2), different.closeness(3, 4))

    def test_reverse_closeness_mirror_effect_accelerates_closeness_growth(self) -> None:
        left = make_social_agent(1, trait=make_trait(study=1.0, exercise=0.0, music=0.0, game=0.0))
        right = make_social_agent(2, trait=make_trait(study=0.0, exercise=0.0, music=0.0, game=1.0))
        mirrored = OuterMindDynamics()
        unmirrored = OuterMindDynamics()
        mirrored.set_relationship(2, 1, closeness=0.8)
        unmirrored.set_relationship(2, 1, closeness=0.05)

        mirrored.advance([left, right], 3600)
        unmirrored.advance([left, right], 3600)

        self.assertGreater(mirrored.closeness(1, 2), unmirrored.closeness(1, 2))

    def test_cognitive_dissonance_cools_one_sided_closeness(self) -> None:
        dynamics = OuterMindDynamics()
        dynamics.set_relationship(1, 2, closeness=0.9)
        dynamics.set_relationship(2, 1, closeness=0.1)
        before_gap = dynamics.closeness(1, 2) - dynamics.closeness(2, 1)

        dynamics.advance([], 3600)

        after_gap = dynamics.closeness(1, 2) - dynamics.closeness(2, 1)
        self.assertLess(dynamics.closeness(1, 2), 0.9)
        self.assertLess(after_gap, before_gap)

    def test_relationship_and_social_memory_decay_without_interaction(self) -> None:
        dynamics = OuterMindDynamics()
        dynamics.set_relationship(1, 2, closeness=0.6)
        trait = make_trait()
        trait.personality["extraversion"] = 0.8
        agent = make_social_agent(
            1,
            trait=trait,
            state=make_state(social_contribution=0.8, social_return=0.8, extrinsic_satisfaction=0.8),
            action=None,
        )

        dynamics.advance([agent], 3600)

        self.assertLess(dynamics.closeness(1, 2), 0.6)
        self.assertLess(agent.state.social_contribution, 0.8)
        self.assertLess(agent.state.social_return, 0.8)
        self.assertLess(agent.state.extrinsic_satisfaction, 0.8)

    def test_social_exchange_updates_return_energy_extrinsic_and_wellbeing(self) -> None:
        dynamics = OuterMindDynamics()
        initiator = make_social_agent(
            1,
            trait=make_trait(wellbeing=0.4),
            state=make_state(energy=0.9, social_contribution=0.0, social_return=0.05, extrinsic_satisfaction=0.3),
        )
        responder = make_social_agent(2, state=make_state(energy=0.9))
        responder.trait.personality["agreeableness"] = 1.0
        dynamics.set_relationship(2, 1, closeness=0.8)

        delta = dynamics.advance([initiator, responder], 3600)

        self.assertGreater(initiator.state.social_contribution, 0.0)
        self.assertGreater(initiator.state.social_return, 0.05)
        self.assertLess(initiator.state.energy, 0.9)
        self.assertGreater(initiator.state.extrinsic_satisfaction, 0.3)
        self.assertNotEqual(initiator.trait.wellbeing, 0.4)
        self.assertLess(delta.energy_changes[1], 0.0)
        self.assertGreater(delta.relationship_changes[(1, 2)], 0.0)


if __name__ == "__main__":
    unittest.main()
