from __future__ import annotations

import unittest

from abm.model.schedule import AcademicScheduleBook, COURSE_SLOT_TIMES, CourseSession
from abm.core.map import Region
from abm.environment_dynamics import (
    sleep_energy_gain_per_hour,
    update_academic_cycle_state,
    update_circadian_sleep_state,
)
from abm.core.types import parse_time_to_seconds
from tests.helpers import make_state, make_trait, make_variable


def teaching_region(region_id: str = "building_001") -> Region:
    return Region(
        id=region_id,
        terrain="building",
        name="Teaching",
        function="teaching",
        area=100,
        cell_count=100,
        available=True,
        open_time="00:00",
        close_time="23:59",
        entrances=((0, 0),),
        cells=frozenset({(0, 0)}),
        bounds={},
    )


def course(region_id: str = "building_001") -> CourseSession:
    return CourseSession(
        course_id="course-1",
        day=0,
        slot_index=0,
        start_second=parse_time_to_seconds("08:00:00"),
        end_second=parse_time_to_seconds("09:35:00"),
        region_id=region_id,
        region_name="Teaching",
    )


class TemporalAcademicTest(unittest.TestCase):
    def test_day_sleep_recovers_energy_slower_than_night_sleep(self) -> None:
        night_trait = make_trait(stress=0.0)
        day_trait = make_trait(stress=0.0)
        night_state = make_state(energy=0.4)
        day_state = make_state(energy=0.4)
        night_variable = make_variable(current_action="sleep")
        day_variable = make_variable(current_action="sleep")

        self.assertGreater(
            sleep_energy_gain_per_hour(parse_time_to_seconds("23:00:00")),
            sleep_energy_gain_per_hour(parse_time_to_seconds("12:00:00")),
        )
        update_circadian_sleep_state(night_trait, night_state, night_variable, 3600, parse_time_to_seconds("23:00:00"))
        update_circadian_sleep_state(day_trait, day_state, day_variable, 3600, parse_time_to_seconds("12:00:00"))

        self.assertGreater(night_state.energy, day_state.energy)
        self.assertEqual(night_variable.current_sleep_energy_gain_per_hour, 0.45)
        self.assertEqual(day_variable.current_sleep_energy_gain_per_hour, 0.12)

    def test_missing_active_course_raises_stress_once(self) -> None:
        trait = make_trait(stress=0.2)
        state = make_state()
        context = make_variable(phase="MOVING")
        session = course()

        first = update_academic_cycle_state(
            trait,
            state,
            context,
            day=0,
            second_of_day=parse_time_to_seconds("08:30:00"),
            course_sessions=(session,),
        )
        second = update_academic_cycle_state(
            trait,
            state,
            context,
            day=0,
            second_of_day=parse_time_to_seconds("08:45:00"),
            course_sessions=(session,),
        )

        self.assertEqual(first.missed_course_id, session.course_id)
        self.assertIsNone(second.missed_course_id)
        self.assertAlmostEqual(1.0 - trait.mental_health, 0.38)
        self.assertEqual(len(context.missed_course_penalty_ids), 1)

    def test_being_at_matching_classroom_avoids_stress_penalty(self) -> None:
        trait = make_trait(stress=0.2)
        state = make_state()
        context = make_variable(phase="ACTIVITY", current_action="study", target_region_id="building_001")
        session = course("building_001")

        result = update_academic_cycle_state(
            trait,
            state,
            context,
            day=0,
            second_of_day=parse_time_to_seconds("08:30:00"),
            course_sessions=(session,),
        )

        self.assertEqual(result.active_course_id, session.course_id)
        self.assertIsNone(result.missed_course_id)
        self.assertAlmostEqual(1.0 - trait.mental_health, 0.2)

    def test_academic_schedule_is_daily_stable_and_uses_defined_slots(self) -> None:
        book = AcademicScheduleBook([teaching_region()], rng=7)

        first = book.sessions_for(student_id=1, day=0)
        second = book.sessions_for(student_id=1, day=0)
        next_day = book.sessions_for(student_id=1, day=1)
        valid_slots = {
            (parse_time_to_seconds(start), parse_time_to_seconds(end))
            for start, end in COURSE_SLOT_TIMES
        }

        self.assertEqual(first, second)
        self.assertNotEqual(first, next_day)
        self.assertTrue(first)
        for session in first:
            self.assertIn((session.start_second, session.end_second), valid_slots)


if __name__ == "__main__":
    unittest.main()
