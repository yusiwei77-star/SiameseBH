from __future__ import annotations

import math
import random
import unittest

from abm.model.daily import StudentDailyModel
from abm.agent.policy import RuleBasedStudentPolicy
from abm.core.types import StudentProfile, StudentState, StudentTrait, StudentContext, parse_time_to_seconds
from tests.helpers import make_profile, make_state, make_trait, make_variable


def choose(
    policy: RuleBasedStudentPolicy,
    profile: StudentProfile,
    trait: StudentTrait,
    state: StudentState,
    context: StudentContext,
    *,
    time_text: str,
    legal_actions: set[str],
) -> str | None:
    decision = policy.choose_action(
        profile,
        trait,
        state,
        context,
        second_of_day=parse_time_to_seconds(time_text),
        legal_actions=legal_actions,
        rng=random.Random(1),
    )
    return None if decision is None else decision.action


class RuleBasedStudentPolicyTest(unittest.TestCase):
    def test_low_satiety_selects_eat_when_legal(self) -> None:
        policy = RuleBasedStudentPolicy()
        profile = make_profile()
        trait = make_trait(stress=0.2)
        state = make_state(energy=0.8, satiety=0.1)
        context = make_variable()

        action = choose(
            policy,
            profile,
            trait,
            state,
            context,
            time_text="12:00:00",
            legal_actions={"eat", "study", "social"},
        )

        self.assertEqual(action, "eat")

    def test_low_energy_at_night_selects_sleep(self) -> None:
        policy = RuleBasedStudentPolicy()
        profile = make_profile()
        trait = make_trait(stress=0.2)
        state = make_state(energy=0.15, satiety=0.8)
        context = make_variable()

        action = choose(
            policy,
            profile,
            trait,
            state,
            context,
            time_text="23:30:00",
            legal_actions={"sleep", "eat", "study"},
        )

        self.assertEqual(action, "sleep")

    def test_low_health_prioritizes_service(self) -> None:
        policy = RuleBasedStudentPolicy()
        profile = make_profile()
        sick_trait = make_trait(health=0.1)
        sick = make_state(energy=0.7, satiety=0.7)
        context = make_variable()

        sick_action = choose(
            policy,
            profile,
            sick_trait,
            sick,
            context,
            time_text="10:00:00",
            legal_actions={"service", "study", "social"},
        )

        self.assertEqual(sick_action, "service")

    def test_high_social_need_selects_social_when_legal(self) -> None:
        policy = RuleBasedStudentPolicy()
        profile = make_profile()
        trait = make_trait(music=1.0, game=1.0, exercise=0.2, stress=0.1)
        state = make_state(energy=0.85, satiety=0.85, social_return=0.1)
        context = make_variable()

        action = choose(
            policy,
            profile,
            trait,
            state,
            context,
            time_text="19:00:00",
            legal_actions={"social", "exercise", "study"},
        )

        self.assertEqual(action, "social")

    def test_low_energy_and_satiety_suppress_exercise(self) -> None:
        policy = RuleBasedStudentPolicy()
        profile = make_profile()
        trait = make_trait(exercise=1.0, stress=0.1)
        state = make_state(energy=0.2, satiety=0.2)
        context = make_variable()

        action = choose(
            policy,
            profile,
            trait,
            state,
            context,
            time_text="18:00:00",
            legal_actions={"exercise", "rest"},
        )

        self.assertEqual(action, "rest")

    def test_invitation_response_rejects_hard_constraints_and_accepts_good_meal_invite(self) -> None:
        policy = RuleBasedStudentPolicy()
        profile = make_profile()
        trait = make_trait(music=1.0, game=1.0, stress=0.2)
        busy = make_state()
        busy_variable = make_variable(phase="ACTIVITY", current_action="study")
        hungry = make_state(satiety=0.2, social_return=0.2)
        hungry_variable = make_variable()

        rejected = policy.choose_invitation_response(
            profile,
            trait,
            busy,
            busy_variable,
            invitation={"action": "Invite_to_Eat"},
            intimacy=0.9,
            second_of_day=parse_time_to_seconds("12:00:00"),
            rng=random.Random(1),
        )
        accepted = policy.choose_invitation_response(
            profile,
            trait,
            hungry,
            hungry_variable,
            invitation={"action": "Invite_to_Eat"},
            intimacy=0.9,
            second_of_day=parse_time_to_seconds("12:00:00"),
            rng=random.Random(1),
        )

        self.assertFalse(rejected.accepted)
        self.assertTrue(accepted.accepted)

    def test_daily_model_rule_policy_smoke(self) -> None:
        model = StudentDailyModel(
            "map/summary.json",
            student_count=100,
            start_time="07:30:00",
            seconds_per_step=1,
            rng=5,
        )

        for _ in range(2):
            model.step()
        snapshot = model.snapshot()

        self.assertEqual(snapshot["agent_count"], 100)
        self.assertNotIn("policy_kind", snapshot)
        agent = snapshot["agents"][0]
        self.assertEqual(set(agent) >= {"id", "profile", "trait", "state", "context"}, True)
        self.assertNotIn("meta", agent)
        self.assertNotIn("reward", agent["state"])
        self.assertNotIn("policy_scores", agent)
        self.assertNotIn("status", agent)

    def test_daily_model_snapshot_includes_average_metrics_and_social_network(self) -> None:
        model = StudentDailyModel(
            "map/summary.json",
            student_count=4,
            start_time="07:30:00",
            seconds_per_step=300,
            rng=5,
        )

        snapshot = model.snapshot()

        self.assertEqual(
            set(snapshot["average_metrics"]),
            {
                "energy",
                "satiety",
                "physical_health",
                "mental_health",
                "wellbeing",
                "intrinsic_satisfaction",
                "extrinsic_satisfaction",
            },
        )
        for value in snapshot["average_metrics"].values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        self.assertEqual(snapshot["social_network"]["nodes"], [])
        self.assertEqual(snapshot["social_network"]["edges"], [])

        left, right = model.students[:2]
        for student in (left, right):
            student.context.phase = "ACTIVITY"
            student.context.current_action = "social"
            student.context.target_region_id = "test_social_region"
        model.outer_mind.advance([left, right], 3600)
        snapshot = model.snapshot()

        self.assertGreaterEqual(len(snapshot["social_network"]["nodes"]), 2)
        self.assertGreaterEqual(len(snapshot["social_network"]["edges"]), 2)

    def test_metrics_history_uses_simulation_elapsed_seconds(self) -> None:
        model = StudentDailyModel(
            "map/summary.json",
            student_count=4,
            start_time="07:30:00",
            seconds_per_step=300,
            rng=5,
        )

        model.step()
        model.step()

        history = model.metrics_history()
        self.assertEqual([sample["elapsed_seconds"] for sample in history], [300, 600])
        self.assertTrue(all("ts" not in sample for sample in history))

    def test_agent_initialization_uses_reproducible_local_prng_seed(self) -> None:
        left = StudentDailyModel(
            "map/summary.json",
            student_count=6,
            start_time="07:30:00",
            seconds_per_step=1,
            rng=17,
        )
        right = StudentDailyModel(
            "map/summary.json",
            student_count=10,
            start_time="07:30:00",
            seconds_per_step=1,
            rng=17,
        )
        changed_seed = StudentDailyModel(
            "map/summary.json",
            student_count=6,
            start_time="07:30:00",
            seconds_per_step=1,
            rng=18,
        )

        for index in range(6):
            self.assertEqual(left.students[index].trait, right.students[index].trait)
            self.assertEqual(left.students[index].state, right.students[index].state)
            self.assertEqual(
                left.students[index].profile.normal_meal_speed,
                right.students[index].profile.normal_meal_speed,
            )
            self.assertEqual(
                left.students[index].profile.normal_walk_speed_cells_per_step,
                right.students[index].profile.normal_walk_speed_cells_per_step,
            )

        self.assertNotEqual(left.students[0].trait, changed_seed.students[0].trait)

    def test_path_progress_uses_fractional_walk_speed(self) -> None:
        model = StudentDailyModel(
            "map/summary.json",
            student_count=2,
            start_time="07:30:00",
            seconds_per_step=1,
            rng=5,
        )
        slow = model.students[0]
        fast = model.students[1]
        slow_start = slow.context.pos
        fast_start = fast.context.pos
        slow.profile.normal_walk_speed_cells_per_step = 0.8
        fast.profile.normal_walk_speed_cells_per_step = 1.2
        slow.context.phase = "MOVING"
        fast.context.phase = "MOVING"
        slow.context.path = [slow_start, (slow_start[0] + 1, slow_start[1]), (slow_start[0] + 2, slow_start[1])]
        fast.context.path = [
            fast_start,
            (fast_start[0] + 1, fast_start[1]),
            (fast_start[0] + 2, fast_start[1]),
            (fast_start[0] + 3, fast_start[1]),
        ]

        slow._advance_path()
        fast._advance_path()

        self.assertEqual(slow.context.path_index, 0)
        self.assertEqual(slow.context.pos, slow_start)
        self.assertAlmostEqual(slow.context.movement_progress, 0.8)
        self.assertEqual(fast.context.path_index, 1)
        self.assertEqual(fast.context.pos, fast.context.path[1])
        self.assertAlmostEqual(fast.context.movement_progress, 0.2)

        slow._advance_path()

        self.assertEqual(slow.context.path_index, 1)
        self.assertEqual(slow.context.pos, slow.context.path[1])
        self.assertAlmostEqual(slow.context.movement_progress, 0.6)

    def test_diagonal_path_progress_costs_sqrt_two(self) -> None:
        model = StudentDailyModel(
            "map/summary.json",
            student_count=1,
            start_time="07:30:00",
            seconds_per_step=1,
            rng=5,
        )
        student = model.students[0]
        start = student.context.pos
        student.profile.normal_walk_speed_cells_per_step = 1.0
        student.context.phase = "MOVING"
        student.context.path = [start, (start[0] + 1, start[1] + 1), (start[0] + 2, start[1] + 1)]

        student._advance_path()

        self.assertEqual(student.context.path_index, 0)
        self.assertEqual(student.context.pos, start)
        self.assertAlmostEqual(student.context.movement_progress, 1.0)

        student._advance_path()

        self.assertEqual(student.context.path_index, 1)
        self.assertEqual(student.context.pos, student.context.path[1])
        self.assertAlmostEqual(student.context.movement_progress, 2.0 - math.sqrt(2))

    def test_snapshot_render_motion_projects_next_step(self) -> None:
        model = StudentDailyModel(
            "map/summary.json",
            student_count=1,
            start_time="07:30:00",
            seconds_per_step=1,
            rng=5,
        )
        student = model.students[0]
        start = student.context.pos
        student.profile.normal_walk_speed_cells_per_step = 0.8
        student.context.phase = "MOVING"
        student.context.path = [start, (start[0] + 1, start[1]), (start[0] + 2, start[1])]
        student.context.path_index = 0
        student.context.movement_progress = 0.4
        student.context.intention = "study"
        student.context.target_region_id = "region_1"

        motion = student.snapshot()["context"]["render_motion"]

        self.assertIsNotNone(motion)
        self.assertAlmostEqual(motion["start_distance"], 0.4)
        self.assertAlmostEqual(motion["end_distance"], 1.2)
        self.assertAlmostEqual(motion["total_distance"], 2.0)
        self.assertEqual(motion["start_elapsed_seconds"], model.elapsed_seconds)
        self.assertEqual(motion["end_elapsed_seconds"], model.elapsed_seconds + model.seconds_per_step)
        self.assertEqual(motion["phase_after"], "MOVING")

    def test_snapshot_render_motion_marks_arrival_projection(self) -> None:
        model = StudentDailyModel(
            "map/summary.json",
            student_count=1,
            start_time="07:30:00",
            seconds_per_step=1,
            rng=5,
        )
        student = model.students[0]
        start = student.context.pos
        student.profile.normal_walk_speed_cells_per_step = 1.0
        student.context.phase = "MOVING"
        student.context.path = [start, (start[0] + 1, start[1])]
        student.context.path_index = 0
        student.context.movement_progress = 0.2
        student.context.intention = "study"
        student.context.target_region_id = "region_1"

        motion = student.snapshot()["context"]["render_motion"]

        self.assertIsNotNone(motion)
        self.assertAlmostEqual(motion["start_distance"], 0.2)
        self.assertAlmostEqual(motion["end_distance"], 1.0)
        self.assertEqual(motion["phase_after"], "ACTIVITY")


if __name__ == "__main__":
    unittest.main()
