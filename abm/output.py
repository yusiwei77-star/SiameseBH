"""Per-run output manager — creates run folders and manages JSONL incremental writes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

METRIC_KEYS = (
    "energy",
    "satiety",
    "physical_health",
    "mental_health",
    "wellbeing",
    "intrinsic_satisfaction",
    "extrinsic_satisfaction",
)


def make_run_id(students: int, start_time: str, *, run_name: str | None = None) -> str:
    """Build a human-readable run identifier from timestamp and parameters."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if run_name:
        return f"{ts}_{run_name}"
    start = start_time.replace(":", "")
    return f"{ts}_n{students}_t{start}"


def _agent_dir_name(agent) -> str:
    """Return folder name like 'male_Alice_Brown' for an agent."""
    name = agent.profile.name.replace(" ", "_")
    return f"{agent.profile.gender}_{name}"


def _r3(value: float) -> float:
    """Round to 3 decimal places to keep JSONL compact."""
    return round(float(value), 3)


class RunOutputManager:
    """Manages per-run output directory and incremental JSONL writes.

    Opens and maintains file handles for the current simulated day.
    On day boundaries, closes old handles and opens new ones under ``day_N/``.
    """

    def __init__(self, run_dir: Path, model) -> None:
        self.run_dir = Path(run_dir)
        self._model = model
        self._pop_handle: TextIO | None = None
        self._social_handle: TextIO | None = None
        self._agent_metrics: dict[int, TextIO] = {}   # agent_id -> handle
        self._agent_activities: dict[int, TextIO] = {}  # agent_id -> handle
        self._current_day = 1

        self._setup_directories()
        self._open_handles(day=1)
        self._write_metadata({
            "run_id": self.run_dir.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "config": {
                "students": len(model.students),
                "start_time": model.current_time,
                "seconds_per_step": model.seconds_per_step,
            },
        })

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_directories(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        agents_dir = self.run_dir / "agents"
        for agent in self._model.students:
            day_dir = agents_dir / _agent_dir_name(agent) / "day_1"
            day_dir.mkdir(parents=True, exist_ok=True)

    def _open_handles(self, day: int) -> None:
        agents_dir = self.run_dir / "agents"
        for agent in self._model.students:
            aid = int(agent.unique_id)
            day_dir = agents_dir / _agent_dir_name(agent) / f"day_{day}"
            self._agent_metrics[aid] = (day_dir / "metrics.jsonl").open("a", encoding="utf-8")
            self._agent_activities[aid] = (day_dir / "activities.jsonl").open("a", encoding="utf-8")

        self._pop_handle = (self.run_dir / "population_metrics.jsonl").open("a", encoding="utf-8")
        self._social_handle = (self.run_dir / "social_graph.jsonl").open("a", encoding="utf-8")

    # ------------------------------------------------------------------
    # Hourly writes
    # ------------------------------------------------------------------

    def write_population_hour(self, hour_idx: int, elapsed_seconds: int, avg: dict[str, Any]) -> None:
        if self._pop_handle is None:
            return
        line: dict[str, Any] = {"hour": hour_idx, "elapsed_seconds": elapsed_seconds}
        for key in METRIC_KEYS:
            line[key] = _r3(avg.get(key, 0))
        self._pop_handle.write(json.dumps(line, separators=(",", ":")) + "\n")
        self._pop_handle.flush()

    def write_social_graph_hour(self, hour_idx: int, elapsed_seconds: int) -> None:
        if self._social_handle is None:
            return
        snapshot = self._model.social_graph_snapshot()
        compact_ties = [
            {
                "s": t["source"],
                "t": t["target"],
                "c": _r3(t["closeness"]),
                "tier": t["tier"],
                "mutual": t["mutual"],
            }
            for t in snapshot.get("ties", [])
        ]
        line = {
            "hour": hour_idx,
            "elapsed_seconds": elapsed_seconds,
            "nodes": snapshot.get("nodes", []),
            "ties": compact_ties,
        }
        self._social_handle.write(json.dumps(line, separators=(",", ":")) + "\n")
        self._social_handle.flush()

    def write_agent_metrics_hour(self, agent, hour_idx: int, archive_entry: dict[str, Any]) -> None:
        handle = self._agent_metrics.get(int(agent.unique_id))
        if handle is None:
            return
        line: dict[str, Any] = {
            "hour": hour_idx,
            "elapsed_seconds": archive_entry.get("elapsed_seconds", hour_idx * 3600),
        }
        for key in METRIC_KEYS:
            line[key] = _r3(archive_entry.get(key, 0))
        handle.write(json.dumps(line, separators=(",", ":")) + "\n")
        handle.flush()

    # ------------------------------------------------------------------
    # Activity writes
    # ------------------------------------------------------------------

    def write_agent_activity(
        self,
        agent,
        action: str,
        location: str,
        started_at: int,
        ended_at: int,
        duration_seconds: int,
    ) -> None:
        handle = self._agent_activities.get(int(agent.unique_id))
        if handle is None:
            return
        line = {
            "action": action,
            "location": location,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": duration_seconds,
        }
        handle.write(json.dumps(line, separators=(",", ":")) + "\n")
        handle.flush()

    # ------------------------------------------------------------------
    # Day boundary
    # ------------------------------------------------------------------

    def on_day_changed(self, day: int) -> None:
        # Close previous day handles
        self._close_handles()
        self._current_day = day
        # Create directories and open handles for new day
        agents_dir = self.run_dir / "agents"
        for agent in self._model.students:
            day_dir = agents_dir / _agent_dir_name(agent) / f"day_{day}"
            day_dir.mkdir(parents=True, exist_ok=True)
        self._open_handles(day=day)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self, final_metadata: dict[str, Any]) -> None:
        self._close_handles()
        self._write_metadata(final_metadata)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _close_handles(self) -> None:
        if self._pop_handle:
            self._pop_handle.close()
            self._pop_handle = None
        if self._social_handle:
            self._social_handle.close()
            self._social_handle = None
        for h in self._agent_metrics.values():
            h.close()
        self._agent_metrics.clear()
        for h in self._agent_activities.values():
            h.close()
        self._agent_activities.clear()

    def _write_metadata(self, meta: dict[str, Any]) -> None:
        path = self.run_dir / "metadata.json"
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        existing.update(meta)
        path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
