"""Deterministic daily course schedule generation for student agents."""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..core.map import Region
from ..core.types import parse_time_to_seconds


COURSE_SLOT_TIMES = (
    ("08:00:00", "09:35:00"),
    ("09:50:00", "11:25:00"),
    ("14:00:00", "15:35:00"),
    ("15:50:00", "17:25:00"),
    ("19:00:00", "20:35:00"),
)


@dataclass(frozen=True)
class CourseSession:
    course_id: str
    day: int
    slot_index: int
    start_second: int
    end_second: int
    region_id: str
    region_name: str

    def contains(self, *, day: int, second_of_day: int) -> bool:
        return self.day == day and self.start_second <= second_of_day < self.end_second


class AcademicScheduleBook:
    """Generate stable per-student daily course schedules."""

    def __init__(
        self,
        teaching_regions: list[Region],
        *,
        rng: int | None = 1,
        min_courses_per_day: int = 0,
        max_courses_per_day: int = 5,
    ) -> None:
        self.teaching_regions = tuple(sorted(teaching_regions, key=lambda region: region.id))
        self.seed = 1 if rng is None else int(rng)
        self.min_courses_per_day = min_courses_per_day
        self.max_courses_per_day = max_courses_per_day
        self._cache: dict[tuple[int, int], tuple[CourseSession, ...]] = {}

    def sessions_for(self, *, student_id: int, day: int) -> tuple[CourseSession, ...]:
        key = (int(student_id), int(day))
        if key not in self._cache:
            self._cache[key] = self._generate(student_id=key[0], day=key[1])
        return self._cache[key]

    def _generate(self, *, student_id: int, day: int) -> tuple[CourseSession, ...]:
        if not self.teaching_regions:
            return ()

        rng = random.Random(self.seed + student_id * 1009 + day * 9176)
        max_count = min(self.max_courses_per_day, len(COURSE_SLOT_TIMES))
        min_count = max(0, min(self.min_courses_per_day, max_count))
        course_count = rng.randint(min_count, max_count) if max_count else 0
        slot_indices = sorted(rng.sample(range(len(COURSE_SLOT_TIMES)), course_count))
        sessions: list[CourseSession] = []
        for slot_index in slot_indices:
            start_text, end_text = COURSE_SLOT_TIMES[slot_index]
            region = rng.choice(self.teaching_regions)
            sessions.append(
                CourseSession(
                    course_id=f"d{day}:s{student_id}:slot{slot_index}:{region.id}",
                    day=day,
                    slot_index=slot_index,
                    start_second=parse_time_to_seconds(start_text),
                    end_second=parse_time_to_seconds(end_text),
                    region_id=region.id,
                    region_name=region.name,
                )
            )
        return tuple(sessions)
