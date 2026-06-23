"""Schedule-free daily student behavior model."""

from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path

from mesa import Model
from mesa.space import MultiGrid

from .schedule import AcademicScheduleBook
from ..core.map import CampusMap, Pos, Region
from ..core.types import (
    SECONDS_PER_DAY,
    StudentProfile,
    StudentState,
    StudentTrait,
    StudentContext,
    format_seconds_as_time,
    parse_time_to_seconds,
)
from ..agent.policy import RuleBasedStudentPolicy
from .checkpoint import load_model_checkpoint, save_model_checkpoint
from ..agent.student import DailyStudentAgent
from ..environment import OuterMindDynamics


class StudentDailyModel(Model):
    """Run students with endogenous daily behavior and no required schedule."""

    def __init__(
        self,
        summary_path: str | Path = "map/summary.json",
        *,
        student_count: int = 10,
        male_count: int | None = None,
        start_time: str = "00:00:00",
        seconds_per_step: int = 1,
        rng: int | None = 1,
    ) -> None:
        super().__init__(rng=rng)
        if seconds_per_step <= 0:
            raise ValueError("seconds_per_step must be positive")
        self.campus_map = CampusMap.from_file(summary_path)
        self.grid = MultiGrid(self.campus_map.width, self.campus_map.height, torus=False)
        self.students: list[DailyStudentAgent] = []
        self.policy = RuleBasedStudentPolicy(rng=rng)
        self.outer_mind = OuterMindDynamics()
        self.academic_schedule = AcademicScheduleBook(
            self._available_regions_by_function("teaching"),
            rng=rng,
        )
        self.campus_steps = 0
        self.global_seed = 1 if rng is None else int(rng)
        self.start_second = parse_time_to_seconds(start_time)
        self.seconds_per_step = int(seconds_per_step)
        self.elapsed_seconds = 0
        self._slot_attended_today: set[tuple[int, int]] = set()
        self._attendance_day = self.day
        self._metrics_history: list[dict[str, object]] = []

        dormitories = self._available_regions_by_function("dormitory")
        if not dormitories:
            raise ValueError("need at least one dormitory region")

        # Split dormitories into east / west by campus midpoint
        mid_col = self.campus_map.width / 2
        east_dorms: list[Region] = []
        west_dorms: list[Region] = []
        for d in dormitories:
            cells = list(d.cells)
            avg_col = sum(c[0] for c in cells) / len(cells)
            if avg_col > mid_col:
                east_dorms.append(d)
            else:
                west_dorms.append(d)
        if not east_dorms:
            raise ValueError("need at least one east-side dormitory")
        if not west_dorms:
            raise ValueError("need at least one west-side dormitory")
        self._east_dorms = east_dorms
        self._west_dorms = west_dorms

        # Laboratory regions for workplace assignment
        lab_regions = self._available_regions_by_function("laboratory")
        self._lab_ids = [r.id for r in lab_regions] if lab_regions else [dormitories[0].id]

        actual_male = male_count if male_count is not None else student_count // 2

        for index in range(student_count):
            agent_id = index + 1
            gender = "male" if index < actual_male else "female"
            if gender == "male":
                dormitory = east_dorms[index % len(east_dorms)]
            else:
                dormitory = west_dorms[(index - actual_male) % len(west_dorms)]
            start = self._select_entrance(dormitory, index % len(dormitory.entrances))
            profile = self._profile_for(index, agent_id, dormitory, gender)
            trait = self._trait_for(agent_id)
            state = self._state_for(agent_id, trait)
            context = self._context_for(index, start)
            context.last_decision_reason = "initialized_without_schedule"
            agent = DailyStudentAgent(
                self,
                profile,
                trait,
                state,
                context,
                rng=self._local_rng(agent_id, "behavior"),
            )
            self.grid.place_agent(agent, start)
            self.students.append(agent)

    def _local_rng(self, agent_id: int, stream: str) -> random.Random:
        seed_text = f"{self.global_seed}:{agent_id}:{stream}".encode("utf-8")
        seed = int.from_bytes(hashlib.blake2b(seed_text, digest_size=8).digest(), "big")
        return random.Random(seed)

    def _state_for(self, agent_id: int, trait: StudentTrait) -> StudentState:
        # NOTE: 以下初始化值假设仿真从早上 7:00 开始。
        # 若仿真从其他时间点开始，energy/satiety 等身体状态需相应调整。
        rng = self._local_rng(agent_id, "state")
        return StudentState(
            emotion={
                "pleasure": 0.5,
                "arousal": 0.5,
                "dominance": 0.5,
            },
            energy=0.8,
            satiety=0.5,
            intrinsic_satisfaction=0.0,
            extrinsic_satisfaction=0.0,
            social_contribution=0.0,
            social_return=0.0,
        )

    @staticmethod
    def _context_for(index: int, start: Pos) -> StudentContext:
        return StudentContext(
            pos=start,
            phase="IDLE",
        )

    def _trait_for(self, agent_id: int) -> StudentTrait:
        rng = self._local_rng(agent_id, "trait")
        neuroticism = rng.betavariate(4.0, 4.0)
        # 随机生成模长为1的四维向量，interests 和 skills 共享同一方向
        raw = [rng.gauss(0.0, 1.0) for _ in range(4)]
        norm = math.hypot(*raw)
        interest_vec = [v / norm for v in raw]
        return StudentTrait(
            personality={
                "openness": rng.betavariate(4.0, 4.0),
                "conscientiousness": rng.betavariate(4.0, 4.0),
                "extraversion": rng.betavariate(4.0, 4.0),
                "agreeableness": rng.betavariate(4.0, 4.0),
                "neuroticism": neuroticism,
            },
            wellbeing=0.8,
            interests={
                "study": interest_vec[0],
                "exercise": interest_vec[1],
                "music": interest_vec[2],
                "game": interest_vec[3],
            },
            skills={
                "study": interest_vec[0],
                "exercise": interest_vec[1],
                "music": interest_vec[2],
                "game": interest_vec[3],
            },
            physical_health=0.8,
            mental_health=0.8,
        )

    @property
    def current_second(self) -> int:
        return self.start_second + self.elapsed_seconds

    @property
    def second_of_day(self) -> int:
        return self.current_second % SECONDS_PER_DAY

    @property
    def day(self) -> int:
        return self.current_second // SECONDS_PER_DAY

    @property
    def current_time(self) -> str:
        return format_seconds_as_time(self.second_of_day)

    @property
    def all_arrived(self) -> bool:
        return False

    def state_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for student in self.students:
            counts[student.context.phase] = counts.get(student.context.phase, 0) + 1
        return counts

    def activity_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for student in self.students:
            activity = student.context.current_action or student.context.intention or "none"
            counts[activity] = counts.get(activity, 0) + 1
        return counts

    def agent_snapshots(
        self,
        *,
        include_last_path: bool = True,
        include_path: bool | dict[int, bool] = True,
    ) -> list[dict[str, object]]:
        snapshots: list[dict[str, object]] = []
        for student in self.students:
            if isinstance(include_path, dict):
                student_include_path = bool(include_path.get(int(student.unique_id), False))
            else:
                student_include_path = include_path
            snapshots.append(
                student.snapshot(
                    include_last_path=include_last_path,
                    include_path=student_include_path,
                )
            )
        return snapshots

    def average_metrics(self) -> dict[str, float]:
        if not self.students:
            return {
                "energy": 0.0,
                "satiety": 0.0,
                "physical_health": 0.0,
                "mental_health": 0.0,
                "wellbeing": 0.0,
                "intrinsic_satisfaction": 0.0,
                "extrinsic_satisfaction": 0.0,
            }
        count = len(self.students)
        return {
            "energy": sum(student.state.energy for student in self.students) / count,
            "satiety": sum(student.state.satiety for student in self.students) / count,
            "physical_health": sum(student.trait.physical_health for student in self.students) / count,
            "mental_health": sum(student.trait.mental_health for student in self.students) / count,
            "wellbeing": sum(student.trait.wellbeing for student in self.students) / count,
            "intrinsic_satisfaction": sum(student.state.intrinsic_satisfaction for student in self.students) / count,
            "extrinsic_satisfaction": sum(student.state.extrinsic_satisfaction for student in self.students) / count,
        }

    def course_slot_attendance(self) -> list[dict[str, object]]:
        # Reset cumulative attendance when day changes
        if self.day != self._attendance_day:
            self._slot_attended_today.clear()
            self._attendance_day = self.day

        slots: list[dict[str, object]] = [{"enrolled": 0, "attended": 0} for _ in range(5)]
        for student in self.students:
            sid = int(student.unique_id)
            sessions = self.course_sessions_for(student)
            for session in sessions:
                si = session.slot_index
                slots[si]["enrolled"] = int(slots[si]["enrolled"]) + 1
                # Already checked this (student, slot) 鈥?carry forward
                if (sid, si) in self._slot_attended_today:
                    slots[si]["attended"] = int(slots[si]["attended"]) + 1
                    continue
                # First time this student enters this slot's course window: check once.
                if session.contains(day=self.day, second_of_day=self.second_of_day):
                    is_present = (
                        student.context.phase == "ACTIVITY"
                        and student.context.current_action == "study"
                        and student.context.target_region_id == session.region_id
                    )
                    if is_present:
                        self._slot_attended_today.add((sid, si))
                        slots[si]["attended"] = int(slots[si]["attended"]) + 1
        return slots

    def save_checkpoint(self, path: str | Path) -> None:
        """Save minimal model state as JSON so the simulation can be resumed later."""
        save_model_checkpoint(self, path)

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: str | Path,
        summary_path: str | Path = "map/summary.json",
        *,
        start_time: str = "00:00:00",
    ) -> "StudentDailyModel":
        """Restore a model from a JSON checkpoint file."""
        return load_model_checkpoint(
            cls,
            checkpoint_path,
            summary_path=summary_path,
            start_time=start_time,
        )

    def snapshot(
        self,
        *,
        include_metrics_history: bool = True,
        include_agent_last_paths: bool = True,
        include_agent_paths: bool | dict[int, bool] = True,
    ) -> dict[str, object]:
        state = {
            "step": self.campus_steps,
            "time": self.current_time,
            "day": self.day,
            "elapsed_seconds": self.elapsed_seconds,
            "seconds_per_step": self.seconds_per_step,
            "average_metrics": self.average_metrics(),
            "course_slot_attendance": self.course_slot_attendance(),
            "state_counts": self.state_counts(),
            "activity_counts": self.activity_counts(),
            "social_dynamics": {
                "delivered_invitations": 0,
                "accepted_invitations": 0,
                "rejected_invitations": 0,
                "expired_invitations": 0,
                "tier_counts": {},
            },
            "social_network": self.social_network_snapshot(),
            "all_arrived": False,
            "arrived_count": 0,
            "agent_count": len(self.students),
            "agents": self.agent_snapshots(
                include_last_path=include_agent_last_paths,
                include_path=include_agent_paths,
            ),
        }
        if include_metrics_history:
            state["metrics_history"] = self.metrics_history()
        return state

    def metrics_history(self, *, tail: int | None = None) -> list[dict[str, object]]:
        if tail is None or tail <= 0:
            return list(self._metrics_history)
        return list(self._metrics_history[-tail:])

    def step(self) -> None:
        for student in self.students:
            student.step()
            if not self.campus_map.is_walkable(student.context.pos):
                raise RuntimeError(f"student moved to non-walkable position {student.context.pos}")
        self.outer_mind.advance(self.students, self.seconds_per_step)
        self.campus_steps += 1
        self.elapsed_seconds += self.seconds_per_step
        # Record metrics snapshot for frontend history
        m = self.average_metrics()
        self._metrics_history.append({
            "step": self.campus_steps,
            "elapsed_seconds": self.elapsed_seconds,
            "energy": m["energy"],
            "satiety": m["satiety"],
            "physical_health": m["physical_health"],
            "mental_health": m["mental_health"],
            "wellbeing": m["wellbeing"],
            "intrinsic_satisfaction": m["intrinsic_satisfaction"],
            "extrinsic_satisfaction": m["extrinsic_satisfaction"],
        })

    def social_network_snapshot(self) -> dict[str, object]:
        active_ties = [tie for tie in self.outer_mind.ties() if tie.closeness >= 0.05 or tie.trust >= 0.05]
        degree: dict[int, int] = {}
        tier_counts = {"intimate": 0, "friend": 0, "acquaintance": 0}
        edges: list[dict[str, object]] = []
        for tie in active_ties:
            tier = self._social_tier(tie.closeness)
            tier_counts[tier] += 1
            degree[tie.source_id] = degree.get(tie.source_id, 0) + 1
            degree[tie.target_id] = degree.get(tie.target_id, 0) + 1
            edges.append(
                {
                    "source": tie.source_id,
                    "target": tie.target_id,
                    "intimacy": tie.closeness,
                    "trust": tie.trust,
                    "tier": tier,
                }
            )

        nodes = [
            {
                "id": int(student.unique_id),
                "name": student.profile.name,
                "degree": degree.get(int(student.unique_id), 0),
            }
            for student in self.students
            if degree.get(int(student.unique_id), 0) > 0
        ]
        return {"nodes": nodes, "edges": edges, "tier_counts": tier_counts}

    @staticmethod
    def _social_tier(closeness: float) -> str:
        if closeness >= 0.70:
            return "intimate"
        if closeness >= 0.30:
            return "friend"
        return "acquaintance"

    def course_sessions_for(self, student: DailyStudentAgent):
        return self.academic_schedule.sessions_for(student_id=int(student.unique_id), day=self.day)

    _MALE_FIRST_NAMES = [
        "Aaron", "Bob", "Charlie", "David", "Edward", "Frank", "George", "Henry",
        "Ivan", "Jack", "Kevin", "Leo", "Marcus", "Nathan", "Oliver", "Paul",
        "Quinn", "Ryan", "Steven", "Tom", "Victor", "William", "Xavier", "Zack",
        "Adrian", "Brian", "Colin", "Daniel", "Elliot", "Gavin", "Isaac", "Kyle",
        "Miles", "Oscar", "Peter", "Ray", "Sam", "Troy", "Vince", "Wade",
    ]
    _FEMALE_FIRST_NAMES = [
        "Alice", "Bella", "Clara", "Diana", "Emily", "Fiona", "Grace", "Hannah",
        "Iris", "Julia", "Kate", "Luna", "Mia", "Nora", "Olivia", "Paula",
        "Queena", "Rachel", "Sarah", "Tessa", "Uma", "Wendy", "Xena", "Yvonne",
        "Anna", "Daisy", "Freya", "Holly", "Jenny", "Laura", "Nina", "Petra",
        "Rose", "Sophia", "Tina", "Vera", "Zoe", "Ella", "Lily", "Ruth",
    ]
    _LAST_NAMES = [
        "Brown", "Chen", "Davis", "Evans", "Foster", "Garcia", "Hayes", "Ito",
        "Jones", "Kim", "Lewis", "Moss", "Nash", "Owens", "Patel", "Quirk",
        "Ross", "Singh", "Taylor", "Ueda", "Vance", "Wells", "Xu", "Yang",
        "Adler", "Baker", "Clark", "Dunn", "Ellis", "Flynn", "Green", "Hart",
    ]

    @classmethod
    def _student_name(cls, index: int, gender: str) -> str:
        names = cls._MALE_FIRST_NAMES if gender == "male" else cls._FEMALE_FIRST_NAMES
        first = names[index % len(names)]
        last = cls._LAST_NAMES[(index * 7 + 3) % len(cls._LAST_NAMES)]
        return f"{first} {last}"

    def _profile_for(self, index: int, agent_id: int, dormitory: Region, gender: str) -> StudentProfile:
        rng = self._local_rng(agent_id, "profile")
        lab_id = self._lab_ids[(index * 7 + 3) % len(self._lab_ids)]
        return StudentProfile(
            name=self._student_name(index, gender),
            gender=gender,
            home=dormitory.id,
            workplace=lab_id,
            normal_meal_speed=rng.uniform(0.8, 1.2),
            normal_walk_speed_cells_per_step=rng.uniform(0.8, 1.2),
        )

    def region_activity_count(self, region_id: str, activity: str) -> int:
        return sum(
            1
            for student in self.students
            if student.context.phase == "ACTIVITY"
            and student.context.current_action == activity
            and student.context.target_region_id == region_id
        )

    def region_activity_phase_count(self, region_id: str, activity: str, activity_phase: str) -> int:
        return sum(
            1
            for student in self.students
            if student.context.phase == "ACTIVITY"
            and student.context.current_action == activity
            and student.context.action_phase == activity_phase
            and student.context.target_region_id == region_id
        )

    def _available_regions_by_function(self, function: str) -> list[Region]:
        return sorted(
            (
                region
                for region in self.campus_map.regions_by_id.values()
                if region.available and region.function == function and region.entrances
            ),
            key=lambda region: region.id,
        )

    def _select_entrance(self, region: Region, index: int) -> Pos:
        entrances = tuple(sorted(region.entrances, key=lambda pos: (pos[1], pos[0])))
        if not entrances:
            raise ValueError(f"region has no entrances: {region.id}")
        pos = entrances[index % len(entrances)]
        if not self.campus_map.is_walkable(pos):
            raise ValueError(f"entrance is not walkable for {region.id}: {pos}")
        return pos
