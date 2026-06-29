"""Checkpoint serialization for the daily student model."""

from __future__ import annotations

import json
from pathlib import Path

from ..agent.student import ACTIVITY_HISTORY_LIMIT
from ..core.types import SECONDS_PER_DAY, StudentProfile, StudentState, StudentTrait, StudentContext


METRIC_KEYS = (
    "energy",
    "satiety",
    "physical_health",
    "mental_health",
    "wellbeing",
    "intrinsic_satisfaction",
    "extrinsic_satisfaction",
)
CHECKPOINT_HOURLY_ARCHIVE_DAYS = 14
CHECKPOINT_HOURLY_ARCHIVE_LIMIT = CHECKPOINT_HOURLY_ARCHIVE_DAYS * 24


def _legacy_action_started_at(raw: int | None) -> int | None:
    """Convert old-format total-elapsed-seconds to second-of-day (0..86399)."""
    if raw is None:
        return None
    if raw >= SECONDS_PER_DAY:
        return raw % SECONDS_PER_DAY
    return raw


def normalize_metrics_history(
    history: list[dict[str, object]],
    *,
    seconds_per_step: int,
) -> list[dict[str, object]]:
    """Convert older wall-clock metric samples to simulation elapsed seconds."""
    normalized: list[dict[str, object]] = []
    last_elapsed: int | None = None
    for raw in history:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        elapsed_value = item.get("elapsed_seconds")
        if elapsed_value is None:
            step = int(item.get("step", 0) or 0)
            elapsed_value = step * seconds_per_step
        elapsed = int(elapsed_value)
        if last_elapsed is not None and elapsed <= last_elapsed:
            continue
        item["elapsed_seconds"] = elapsed
        item.pop("ts", None)
        normalized.append(item)
        last_elapsed = elapsed
    return normalized


def hourly_archive_from_metrics_history(
    history: list[dict[str, object]],
    *,
    current_elapsed: int,
) -> list[dict[str, object]]:
    """Build completed hourly metric buckets from raw samples."""
    buckets: dict[int, list[dict[str, object]]] = {}
    current_hour = current_elapsed // 3600
    for sample in history:
        elapsed = int(sample.get("elapsed_seconds", 0) or 0)
        hour_idx = elapsed // 3600
        if hour_idx >= current_hour:
            continue
        buckets.setdefault(hour_idx, []).append(sample)

    archive: list[dict[str, object]] = []
    for hour_idx in sorted(buckets):
        samples = buckets[hour_idx]
        if not samples:
            continue
        avg: dict[str, object] = {
            "bucketIndex": hour_idx,
            "elapsed_seconds": hour_idx * 3600,
            "count": len(samples),
            "step": samples[-1].get("step"),
        }
        for key in METRIC_KEYS:
            avg[key] = sum(float(sample.get(key, 0) or 0) for sample in samples) / len(samples)
        archive.append(avg)
    return archive


def trim_hourly_archive(
    archive: list[dict[str, object]],
    *,
    limit: int = CHECKPOINT_HOURLY_ARCHIVE_LIMIT,
) -> list[dict[str, object]]:
    """Keep only the recent hourly buckets needed for resumed frontend trends."""
    if limit <= 0:
        return []
    if len(archive) <= limit:
        return list(archive)
    return list(archive[-limit:])


def save_model_checkpoint(model, path: str | Path) -> None:
    """Save minimal model state as JSON so the simulation can be resumed later."""
    data: dict[str, object] = {
        "start_second": model.start_second,
        "global_seed": model.global_seed,
        "elapsed_seconds": model.elapsed_seconds,
        "campus_steps": model.campus_steps,
        "student_count": len(model.students),
        "agents": [agent_checkpoint_data(s) for s in model.students],
        "metrics_history": model._metrics_history,
        "hourly_archive": trim_hourly_archive(model._hourly_archive),
        "slot_attended_today": [list(pair) for pair in model._slot_attended_today],
        "attendance_day": model._attendance_day,
        "outer_mind_relationships": [
            {
                "source_id": tie.source_id,
                "target_id": tie.target_id,
                "closeness": tie.closeness,
            }
            for tie in model.outer_mind.ties()
        ],
    }
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    tmp.replace(path)


def agent_checkpoint_data(agent) -> dict[str, object]:
    v = agent.context
    rng = agent.behavior_rng
    return {
        "unique_id": int(agent.unique_id),
        "profile": {
            "name": agent.profile.name,
            "gender": agent.profile.gender,
            "home": agent.profile.home,
            "workplace": agent.profile.workplace,
            "normal_meal_speed": agent.profile.normal_meal_speed,
            "normal_walk_speed_cells_per_step": agent.profile.normal_walk_speed_cells_per_step,
        },
        "trait": {
            "personality": dict(agent.trait.personality),
            "wellbeing": agent.trait.wellbeing,
            "interests": dict(agent.trait.interests),
            "skills": dict(agent.trait.skills),
            "physical_health": agent.trait.physical_health,
            "mental_health": agent.trait.mental_health,
        },
        "state": {
            "emotion": dict(agent.state.emotion),
            "satiety": agent.state.satiety,
            "energy": agent.state.energy,
            "intrinsic_satisfaction": agent.state.intrinsic_satisfaction,
            "extrinsic_satisfaction": agent.state.extrinsic_satisfaction,
            "social_contribution": agent.state.social_contribution,
            "social_return": agent.state.social_return,
        },
        "context": {
            "pos": list(v.pos),
            "phase": v.phase,
            "path": [list(p) for p in v.path],
            "last_path": [list(p) for p in v.last_path],
            "path_index": v.path_index,
            "intention": v.intention,
            "target_pos": list(v.target_pos) if v.target_pos else None,
            "target_region_id": v.target_region_id,
            "current_action": v.current_action,
            "last_action": v.last_action,
            "action_started_at": v.action_started_at,
            "remaining_action_seconds": v.remaining_action_seconds,
            "action_phase": v.action_phase,
            "last_decision_reason": v.last_decision_reason,
            "current_speed_cells_per_step": v.current_speed_cells_per_step,
            "movement_progress": v.movement_progress,
            "activity_history": list(v.activity_history[:ACTIVITY_HISTORY_LIMIT]),
        },
        "metrics_hourly_archive": trim_hourly_archive(agent.metrics_hourly_archive),
        "rng_state": list(rng.getstate()),
    }


def load_model_checkpoint(
    model_cls,
    checkpoint_path: str | Path,
    summary_path: str | Path = "map/summary.json",
    *,
    start_time: str = "00:00:00",
) -> object:
    """Restore a model from a JSON checkpoint file."""
    checkpoint_path = Path(checkpoint_path)
    with checkpoint_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    student_count = int(data["student_count"])
    model = model_cls(
        summary_path=summary_path,
        student_count=student_count,
        seconds_per_step=1,
        start_time=start_time,
    )
    # Override elapsed time (checkpoint takes priority if present)
    if "start_second" in data:
        model.start_second = int(data["start_second"])
    if "global_seed" in data:
        model.global_seed = int(data["global_seed"])
    model.elapsed_seconds = int(data["elapsed_seconds"])
    model.campus_steps = int(data["campus_steps"])

    # Clear initial positions so we can re-place agents at checkpoint positions
    for agent in model.students:
        model.grid.remove_agent(agent)

    # Restore agents
    cp_agents = data["agents"]
    for i, agent in enumerate(model.students):
        cp = cp_agents[i]
        if not all(key in cp for key in ("profile", "trait", "state", "context")):
            raise ValueError("checkpoint agent must use profile/trait/state/context format")
        profile_data = cp["profile"]
        trait_data = cp["trait"]
        state_data = cp["state"]
        variable_data = cp["context"]
        agent.profile = StudentProfile(**profile_data)
        agent.trait = StudentTrait(
            personality=dict(trait_data["personality"]),
            wellbeing=float(trait_data["wellbeing"]),
            interests=dict(trait_data["interests"]),
            skills=dict(trait_data["skills"]),
            physical_health=float(trait_data["physical_health"]),
            mental_health=float(trait_data["mental_health"]),
        )
        agent.state = StudentState(
            emotion=dict(state_data["emotion"]),
            satiety=float(state_data["satiety"]),
            energy=float(state_data["energy"]),
            intrinsic_satisfaction=float(state_data["intrinsic_satisfaction"]),
            extrinsic_satisfaction=float(state_data["extrinsic_satisfaction"]),
            social_contribution=float(state_data["social_contribution"]),
            social_return=float(state_data["social_return"]),
        )
        agent.context = StudentContext(
            pos=(int(variable_data["pos"][0]), int(variable_data["pos"][1])),
            phase=str(variable_data["phase"]),
            path=[tuple(p) for p in variable_data.get("path", [])],
            last_path=[tuple(p) for p in variable_data.get("last_path", [])],
            path_index=int(variable_data.get("path_index", 0)),
            intention=variable_data.get("intention"),
            target_pos=tuple(variable_data["target_pos"]) if variable_data.get("target_pos") else None,
            target_region_id=variable_data.get("target_region_id"),
            current_action=variable_data.get("current_action"),
            last_action=variable_data.get("last_action"),
            action_started_at=_legacy_action_started_at(variable_data.get("action_started_at")),
            remaining_action_seconds=int(variable_data.get("remaining_action_seconds", 0)),
            action_phase=variable_data.get("action_phase"),
        )
        agent.context.last_decision_reason = variable_data.get("last_decision_reason")
        agent.context.current_speed_cells_per_step = variable_data.get("current_speed_cells_per_step")
        agent.context.movement_progress = float(variable_data.get("movement_progress", 0))
        agent.context.activity_history = list(
            variable_data.get("activity_history", [])[:ACTIVITY_HISTORY_LIMIT]
        )
        agent.metrics_hourly_archive = trim_hourly_archive(
            normalize_metrics_history(
                cp.get("metrics_hourly_archive", []),
                seconds_per_step=model.seconds_per_step,
            )
        )
        if not agent.metrics_hourly_archive and cp.get("metrics_history"):
            legacy_metrics_history = normalize_metrics_history(
                cp.get("metrics_history", []),
                seconds_per_step=model.seconds_per_step,
            )
            agent.metrics_hourly_archive = trim_hourly_archive(
                hourly_archive_from_metrics_history(
                    legacy_metrics_history,
                    current_elapsed=model.elapsed_seconds,
                )
            )
        agent.metrics_history = []
        # Restore behavior RNG
        rng_state = cp["rng_state"]
        agent.behavior_rng.setstate((rng_state[0], tuple(rng_state[1]), rng_state[2]))
        # Re-place agent on grid
        model.grid.place_agent(agent, agent.context.pos)

    # Restore attendance tracking
    model._metrics_history = normalize_metrics_history(
        data.get("metrics_history", []),
        seconds_per_step=model.seconds_per_step,
    )
    model._hourly_archive = trim_hourly_archive(
        normalize_metrics_history(
            data.get("hourly_archive", []),
            seconds_per_step=model.seconds_per_step,
        )
    )
    model._slot_attended_today = {tuple(pair) for pair in data.get("slot_attended_today", [])}
    model._attendance_day = int(data.get("attendance_day", model.day))
    for tie in data.get("outer_mind_relationships", []):
        model.outer_mind.set_relationship(
            int(tie["source_id"]),
            int(tie["target_id"]),
            closeness=float(tie["closeness"]),
        )

    return model
