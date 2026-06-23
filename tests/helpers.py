from __future__ import annotations

from dataclasses import dataclass

from abm.core.types import StudentProfile, StudentState, StudentTrait, StudentContext


def make_profile(*, meal_speed: float = 1.0, walk_speed: float = 1.0, home: str | None = None, gender: str = "") -> StudentProfile:
    return StudentProfile(
        gender=gender,
        home=home,
        normal_meal_speed=meal_speed,
        normal_walk_speed_cells_per_step=walk_speed,
    )


def make_trait(
    *,
    stress: float = 0.2,
    health: float = 1.0,
    study: float = 0.7,
    exercise: float = 0.3,
    music: float = 0.4,
    game: float = 0.4,
    conscientiousness: float = 0.8,
    study_skill: float = 0.5,
    exercise_skill: float = 0.5,
    music_skill: float = 0.5,
    game_skill: float = 0.5,
    wellbeing: float = 0.5,
) -> StudentTrait:
    return StudentTrait(
        personality={
            "openness": 0.5,
            "conscientiousness": conscientiousness,
            "extraversion": (music + game) / 2.0,
            "agreeableness": 0.5,
            "neuroticism": stress,
        },
        wellbeing=wellbeing,
        interests={"study": study, "exercise": exercise, "music": music, "game": game},
        skills={"study": study_skill, "exercise": exercise_skill, "music": music_skill, "game": game_skill},
        physical_health=health,
        mental_health=max(0.0, min(1.0, 1.0 - stress)),
    )


def make_state(
    *,
    energy: float = 1.0,
    satiety: float = 1.0,
    intrinsic_satisfaction: float = 0.5,
    extrinsic_satisfaction: float = 0.8,
    social_return: float = 0.5,
    social_contribution: float = 0.0,
) -> StudentState:
    stress = 1.0 - extrinsic_satisfaction
    return StudentState(
        emotion={"pleasure": 1.0 - stress, "arousal": stress, "dominance": 0.5},
        energy=energy,
        satiety=satiety,
        intrinsic_satisfaction=intrinsic_satisfaction,
        extrinsic_satisfaction=extrinsic_satisfaction,
        social_contribution=social_contribution,
        social_return=social_return,
    )


def make_variable(
    *,
    pos: tuple[int, int] = (0, 0),
    phase: str = "IDLE",
    current_action: str | None = None,
    target_region_id: str | None = None,
) -> StudentContext:
    return StudentContext(
        pos=pos,
        phase=phase,
        current_action=current_action,
        target_region_id=target_region_id,
    )


@dataclass
class FakeAgent:
    unique_id: int
    profile: StudentProfile
    trait: StudentTrait
    state: StudentState
    context: StudentContext
