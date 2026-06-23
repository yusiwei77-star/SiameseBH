from __future__ import annotations

import unittest

from abm.environment_dynamics import (
    INVITE_TO_EAT,
    RelationshipTier,
    SocialDynamicsConfig,
    SocialInformationalDynamics,
    SocialInvitation,
    SpatialDynamicsConfig,
    SpatialTrafficDynamics,
    WeatherCondition,
    WeatherSchedule,
    WeatherWindow,
)
from abm.core.map import Region
from tests.helpers import FakeAgent, make_profile, make_state, make_trait, make_variable


class TinyMap:
    def __init__(self, exits: int = 4) -> None:
        self.exits = exits

    def in_bounds(self, pos: tuple[int, int]) -> bool:
        return True

    def neighbors(self, pos: tuple[int, int], *, moore: bool = False) -> list[tuple[int, int]]:
        return [(pos[0] + index + 1, pos[1]) for index in range(self.exits)]


class TinySocialMap:
    def __init__(self) -> None:
        self.width = 5
        self.height = 3
        canteen = Region(
            id="canteen_1",
            terrain="building",
            name="Canteen",
            function="canteen",
            area=1,
            cell_count=1,
            available=True,
            open_time="00:00",
            close_time="23:59",
            entrances=((2, 1),),
            cells=frozenset({(2, 1)}),
            bounds={},
        )
        self.regions_by_id = {canteen.id: canteen}

    def is_walkable(self, pos: tuple[int, int]) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def neighbors(self, pos: tuple[int, int], *, moore: bool = False) -> list[tuple[int, int]]:
        x, y = pos
        offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if moore:
            offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        return [candidate for candidate in ((x + dx, y + dy) for dx, dy in offsets) if self.is_walkable(candidate)]


def agent(
    unique_id: int,
    pos: tuple[int, int],
    *,
    speed: float = 1.0,
    energy: float = 1.0,
    stress: float = 0.2,
) -> FakeAgent:
    return FakeAgent(
        unique_id=unique_id,
        profile=make_profile(walk_speed=speed),
        trait=make_trait(stress=stress),
        state=make_state(energy=energy),
        context=make_variable(pos=pos),
    )


class SpatialTrafficDynamicsTest(unittest.TestCase):
    def test_faster_profiles_produce_larger_movement_budgets(self) -> None:
        dynamics = SpatialTrafficDynamics(
            SpatialDynamicsConfig(base_accident_probability=0.0),
            rng=1,
        )
        slow = agent(1, (0, 0), speed=0.6)
        fast = agent(2, (1, 0), speed=2.4)

        result = dynamics.step([slow, fast], TinyMap(), current_second=0, seconds_per_step=1)

        self.assertEqual(result.movement_budgets[1], 0)
        self.assertEqual(result.movement_budgets[2], 2)
        self.assertAlmostEqual(slow.context.movement_progress, 0.6)
        self.assertAlmostEqual(fast.context.movement_progress, 0.4)

    def test_accident_hold_forces_speed_to_zero(self) -> None:
        dynamics = SpatialTrafficDynamics(
            SpatialDynamicsConfig(base_accident_probability=0.0),
            rng=1,
        )
        student = agent(1, (0, 0), speed=2.0)
        student.context.accident_hold_seconds = 30

        result = dynamics.step([student], TinyMap(), current_second=0, seconds_per_step=10)

        self.assertEqual(result.effective_speeds[1], 0.0)
        self.assertEqual(result.movement_budgets[1], 0)
        self.assertEqual(student.context.current_speed_cells_per_step, 0.0)
        self.assertEqual(student.context.accident_hold_seconds, 20)

    def test_same_cell_pair_accident_changes_state(self) -> None:
        dynamics = SpatialTrafficDynamics(
            SpatialDynamicsConfig(base_accident_probability=1.0),
            rng=3,
        )
        left = agent(1, (0, 0), speed=1.0)
        right = agent(2, (0, 0), speed=1.5)

        result = dynamics.step([left, right], TinyMap(), current_second=0, seconds_per_step=1)

        self.assertEqual(len(result.accidents), 1)
        self.assertEqual(result.accidents[0].participant_ids, (1, 2))
        self.assertEqual(result.movement_budgets[1], 0)
        self.assertEqual(result.movement_budgets[2], 0)
        self.assertEqual(left.context.current_speed_cells_per_step, 0.0)
        self.assertEqual(right.context.current_speed_cells_per_step, 0.0)
        self.assertLess(left.state.energy, 1.0)
        self.assertGreater(1.0 - left.trait.mental_health, 0.2)
        self.assertTrue(left.context.active_accident_ids)
        self.assertTrue(right.context.active_accident_ids)

    def test_agent_already_in_accident_can_form_another_pair_accident(self) -> None:
        dynamics = SpatialTrafficDynamics(
            SpatialDynamicsConfig(base_accident_probability=1.0),
            rng=4,
        )
        students = [agent(1, (0, 0)), agent(2, (0, 0)), agent(3, (0, 0))]

        result = dynamics.step(students, TinyMap(), current_second=0, seconds_per_step=1)

        self.assertEqual(len(result.accidents), 3)
        self.assertTrue(any(len(student.context.active_accident_ids) > 1 for student in students))

    def test_rain_and_snow_raise_accident_probability(self) -> None:
        dynamics = SpatialTrafficDynamics(rng=1)

        clear = dynamics.accident_probability(
            weather=WeatherCondition.CLEAR,
            occupancy=2,
            speed_range=1.0,
        )
        rain = dynamics.accident_probability(
            weather=WeatherCondition.RAIN,
            occupancy=2,
            speed_range=1.0,
        )
        snow = dynamics.accident_probability(
            weather=WeatherCondition.SNOW,
            occupancy=2,
            speed_range=1.0,
        )

        self.assertGreater(rain, clear)
        self.assertGreater(snow, rain)

    def test_congestion_increases_energy_drain(self) -> None:
        dynamics = SpatialTrafficDynamics(
            SpatialDynamicsConfig(
                congestion_capacity=1,
                congestion_energy_drain_per_hour=0.1,
                base_accident_probability=0.0,
            ),
            rng=1,
        )
        alone = agent(1, (0, 0))
        crowded_left = agent(2, (1, 0))
        crowded_right = agent(3, (1, 0))

        result = dynamics.step(
            [alone, crowded_left, crowded_right],
            TinyMap(),
            current_second=0,
            seconds_per_step=3600,
        )

        self.assertNotIn(1, result.congestion_energy_loss)
        self.assertAlmostEqual(result.congestion_energy_loss[2], 0.1)
        self.assertAlmostEqual(crowded_left.state.energy, 0.9)
        self.assertAlmostEqual(crowded_right.state.energy, 0.9)
        self.assertAlmostEqual(alone.state.energy, 1.0)

    def test_movement_budget_costs_energy_by_walkable_cells(self) -> None:
        dynamics = SpatialTrafficDynamics(
            SpatialDynamicsConfig(
                base_accident_probability=0.0,
                movement_energy_cost_per_cell=0.01,
            ),
            rng=1,
        )
        near = agent(1, (0, 0), speed=3.0, energy=1.0)
        far = agent(2, (1, 0), speed=3.0, energy=1.0)
        idle = agent(3, (2, 0), speed=3.0, energy=1.0)
        near.context.phase = "MOVING"
        near.context.path = [(0, 0), (0, 1)]
        far.context.phase = "MOVING"
        far.context.path = [(1, 0), (1, 1), (1, 2), (1, 3)]

        result = dynamics.step([near, far, idle], TinyMap(), current_second=0, seconds_per_step=1)

        self.assertEqual(result.movement_budgets[near.unique_id], 3)
        self.assertEqual(result.movement_budgets[far.unique_id], 3)
        self.assertAlmostEqual(result.movement_energy_loss[near.unique_id], 0.01)
        self.assertAlmostEqual(result.movement_energy_loss[far.unique_id], 0.03)
        self.assertNotIn(idle.unique_id, result.movement_energy_loss)
        self.assertAlmostEqual(near.state.energy, 0.99)
        self.assertAlmostEqual(far.state.energy, 0.97)
        self.assertAlmostEqual(idle.state.energy, 1.0)

    def test_weather_schedule_is_deterministic(self) -> None:
        schedule = WeatherSchedule(
            windows=(WeatherWindow(3600, 7200, WeatherCondition.RAIN),),
            default=WeatherCondition.CLEAR,
        )

        self.assertEqual(schedule.condition_at(0), WeatherCondition.CLEAR)
        self.assertEqual(schedule.condition_at(3600), WeatherCondition.RAIN)
        self.assertEqual(schedule.condition_at(7200), WeatherCondition.RAIN)
        self.assertEqual(schedule.condition_at(7201), WeatherCondition.CLEAR)


class SocialInformationalDynamicsTest(unittest.TestCase):
    def test_initialize_keeps_relationship_network_sparse(self) -> None:
        dynamics = SocialInformationalDynamics(rng=1)
        students = [
            FakeAgent(
                unique_id=index,
                profile=make_profile(home="group_a"),
                trait=make_trait(),
                state=make_state(),
                context=make_variable(pos=(index, 0)),
            )
            for index in range(20)
        ]
        students[0].context.relationships[1] = dynamics.config.friend_initial_intimacy

        dynamics.initialize(students)

        active_edges = list(dynamics._active_relationship_pairs())
        self.assertEqual(len(active_edges), 1)
        self.assertEqual(active_edges[0][0], (0, 1))
        self.assertEqual(dynamics.get_intimacy(2, 3), dynamics.config.same_group_initial_intimacy)
        self.assertNotIn(3, dynamics._active_neighbors(2))

    def test_relationship_tier_boundaries(self) -> None:
        dynamics = SocialInformationalDynamics()

        self.assertEqual(dynamics.tier_for(0.8), RelationshipTier.INTIMATE)
        self.assertEqual(dynamics.tier_for(0.4), RelationshipTier.FRIEND)
        self.assertEqual(dynamics.tier_for(0.1), RelationshipTier.ACQUAINTANCE)
        self.assertEqual(dynamics.tier_for(0.09), RelationshipTier.STRANGER)

    def test_high_intimacy_decays_slower_than_low_intimacy(self) -> None:
        dynamics = SocialInformationalDynamics(
            SocialDynamicsConfig(coaction_gain_per_hour=0.0, emotional_contagion_per_hour=0.0),
            rng=1,
        )
        students = [agent(1, (0, 0)), agent(2, (1, 0)), agent(3, (2, 0))]
        dynamics.initialize(students)
        dynamics.set_intimacy(1, 2, 0.9)
        dynamics.set_intimacy(1, 3, 0.2)

        dynamics.update_relationships(students, 3600)

        self.assertLess(0.9 - dynamics.get_intimacy(1, 2), 0.2 - dynamics.get_intimacy(1, 3))

    def test_coaction_raises_intimacy_with_smaller_gain_at_high_baseline(self) -> None:
        dynamics = SocialInformationalDynamics(
            SocialDynamicsConfig(relationship_decay_per_hour=0.0, emotional_contagion_per_hour=0.0),
            rng=1,
        )
        students = [agent(1, (0, 0)), agent(2, (1, 0)), agent(3, (2, 0)), agent(4, (3, 0))]
        for student in students:
            student.context.current_action = "study"
            student.context.target_region_id = "library"
        dynamics.initialize(students)
        dynamics.set_intimacy(1, 2, 0.2)
        dynamics.set_intimacy(3, 4, 0.8)

        dynamics.update_relationships(students, 3600)

        low_gain = dynamics.get_intimacy(1, 2) - 0.2
        high_gain = dynamics.get_intimacy(3, 4) - 0.8
        self.assertGreater(low_gain, 0.0)
        self.assertGreater(high_gain, 0.0)
        self.assertGreater(low_gain, high_gain)

    def test_emotional_contagion_only_applies_to_intimate_relationships(self) -> None:
        dynamics = SocialInformationalDynamics(
            SocialDynamicsConfig(
                relationship_decay_per_hour=0.0,
                coaction_gain_per_hour=0.0,
                emotional_contagion_per_hour=1.0,
            ),
            rng=1,
        )
        calm = agent(1, (0, 0), stress=0.0)
        tense = agent(2, (1, 0), stress=1.0)
        acquaintance = agent(3, (2, 0), stress=0.0)
        dynamics.initialize([calm, tense, acquaintance])
        dynamics.set_intimacy(1, 2, 0.8)
        dynamics.set_intimacy(1, 3, 0.4)

        result = dynamics.update_relationships([calm, tense, acquaintance], 3600)

        self.assertGreater(1.0 - calm.trait.mental_health, 0.0)
        self.assertLess(1.0 - tense.trait.mental_health, 1.0)
        self.assertEqual(1.0 - acquaintance.trait.mental_health, 0.0)
        self.assertIn(1, result.stress_deltas)
        self.assertNotIn(3, result.stress_deltas)

    def test_emotional_contagion_uses_weighted_mean_not_friend_count_sum(self) -> None:
        many_dynamics = SocialInformationalDynamics(
            SocialDynamicsConfig(
                relationship_decay_per_hour=0.0,
                coaction_gain_per_hour=0.0,
                emotional_contagion_per_hour=0.1,
            ),
            rng=1,
        )
        central = agent(1, (0, 0), stress=0.0)
        friends = [agent(index, (index, 0), stress=1.0) for index in range(2, 7)]
        many_agents = [central, *friends]
        many_dynamics.initialize(many_agents)
        for friend in friends:
            many_dynamics.set_intimacy(central.unique_id, friend.unique_id, 0.8)

        many_dynamics.update_relationships(many_agents, 3600)

        single_dynamics = SocialInformationalDynamics(
            SocialDynamicsConfig(
                relationship_decay_per_hour=0.0,
                coaction_gain_per_hour=0.0,
                emotional_contagion_per_hour=0.1,
            ),
            rng=1,
        )
        single_central = agent(1, (0, 0), stress=0.0)
        single_friend = agent(2, (1, 0), stress=1.0)
        single_dynamics.initialize([single_central, single_friend])
        single_dynamics.set_intimacy(single_central.unique_id, single_friend.unique_id, 0.8)

        single_dynamics.update_relationships([single_central, single_friend], 3600)

        self.assertAlmostEqual(1.0 - central.trait.mental_health, 1.0 - single_central.trait.mental_health)
        self.assertAlmostEqual(1.0 - central.trait.mental_health, 0.1)

    def test_invitations_only_target_friend_tier_or_above(self) -> None:
        dynamics = SocialInformationalDynamics(
            SocialDynamicsConfig(proposal_probability_per_hour=1.0, eat_invitation_satiety_threshold=1.0),
            rng=1,
        )
        sender = agent(1, (0, 0), energy=1.0)
        friend = agent(2, (1, 0), energy=1.0)
        acquaintance = agent(3, (2, 0), energy=1.0)
        for student in (sender, friend, acquaintance):
            student.state.satiety = 0.4
        dynamics.initialize([sender, friend, acquaintance])
        dynamics.set_intimacy(1, 2, 0.4)
        dynamics.set_intimacy(1, 3, 0.39)

        result = dynamics.create_invitations([sender, friend, acquaintance], current_step=1, seconds_per_step=3600)

        self.assertTrue(result.delivered_invitations)
        self.assertTrue(any(item.to_id == 2 for item in result.delivered_invitations))
        self.assertFalse(any(item.to_id == 3 for item in result.delivered_invitations))

    def test_invitation_target_uses_softmax_exploration(self) -> None:
        dynamics = SocialInformationalDynamics(
            SocialDynamicsConfig(invitation_softmax_temperature=1.0),
            rng=2,
        )
        sender = agent(1, (0, 0))
        closest = agent(2, (1, 0))
        secondary = agent(3, (2, 0))
        dynamics.initialize([sender, closest, secondary])
        dynamics.set_intimacy(1, 2, 0.9)
        dynamics.set_intimacy(1, 3, 0.4)

        target = dynamics._choose_invitation_target(sender, [closest, secondary])

        self.assertEqual(target.unique_id, secondary.unique_id)

    def test_accepting_invitation_binds_agents_to_same_canteen(self) -> None:
        dynamics = SocialInformationalDynamics(rng=1)
        sender = agent(1, (0, 1), stress=0.2)
        target = agent(2, (4, 1), stress=0.2)
        invitation = SocialInvitation(
            invitation_id="invite-1",
            from_id=1,
            to_id=2,
            action=INVITE_TO_EAT,
            created_step=0,
        )
        target.context.social_mailbox.append(invitation.to_payload())
        dynamics.initialize([sender, target])
        dynamics.set_intimacy(1, 2, 0.7)

        result = dynamics.resolve_invitations(
            [sender, target],
            TinySocialMap(),
            current_step=1,
            invitation_resolver=lambda *_args: (True, "test_accept"),
        )

        self.assertEqual(len(result.accepted_invitations), 1)
        self.assertEqual(sender.context.phase, "MOVING")
        self.assertEqual(target.context.phase, "MOVING")
        self.assertEqual(sender.context.target_region_id, "canteen_1")
        self.assertEqual(target.context.target_region_id, "canteen_1")
        self.assertEqual(sender.context.joint_action_id, target.context.joint_action_id)

    def test_rejecting_invitation_raises_inviter_stress(self) -> None:
        dynamics = SocialInformationalDynamics(SocialDynamicsConfig(reject_stress_gain=0.05), rng=1)
        sender = agent(1, (0, 1), stress=0.2)
        target = agent(2, (4, 1), stress=0.2)
        target.context.social_mailbox.append(
            SocialInvitation("invite-1", 1, 2, INVITE_TO_EAT, 0).to_payload()
        )
        dynamics.initialize([sender, target])
        dynamics.set_intimacy(1, 2, 0.7)

        result = dynamics.resolve_invitations(
            [sender, target],
            TinySocialMap(),
            current_step=1,
            invitation_resolver=lambda *_args: (False, "test_reject"),
        )

        self.assertEqual(len(result.rejected_invitations), 1)
        self.assertAlmostEqual(1.0 - sender.trait.mental_health, 0.25)
        self.assertLess(dynamics.get_intimacy(1, 2), 0.7)

    def test_hard_constraint_prevents_forced_binding(self) -> None:
        dynamics = SocialInformationalDynamics(rng=1)
        sender = agent(1, (0, 1), stress=0.2)
        target = agent(2, (4, 1), stress=0.2)
        target.context.phase = "ACTIVITY"
        target.context.current_action = "study"
        target.context.social_mailbox.append(
            SocialInvitation("invite-1", 1, 2, INVITE_TO_EAT, 0).to_payload()
        )
        dynamics.initialize([sender, target])
        dynamics.set_intimacy(1, 2, 0.7)

        result = dynamics.resolve_invitations(
            [sender, target],
            TinySocialMap(),
            current_step=1,
            invitation_resolver=lambda *_args: (True, "test_accept"),
        )

        self.assertEqual(len(result.expired_invitations), 1)
        self.assertEqual(target.context.phase, "ACTIVITY")
        self.assertIsNone(sender.context.joint_action_id)


if __name__ == "__main__":
    unittest.main()
