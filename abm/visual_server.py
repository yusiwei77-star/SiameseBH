"""Realtime ABM visualization server.

Run:
    python -m abm.visual_server
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

from .model.daily import StudentDailyModel


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8789
VIEWER_TEMPLATE = Path(__file__).with_name("viewer_template.html")
LEGACY_VIEWER_OUTPUT = Path("debug/agent_viewer.html")
METRIC_KEYS = (
    "energy",
    "satiety",
    "physical_health",
    "mental_health",
    "wellbeing",
    "intrinsic_satisfaction",
    "extrinsic_satisfaction",
)
METRICS_BUCKET_LIMIT = 12
MAX_STEPS_PER_ADVANCE = 5
BACKGROUND_IDLE_SLEEP_SECONDS = 0.05


def aggregate_metric_buckets(
    source: list[dict[str, object]],
    *,
    bucket_seconds: int,
    current_elapsed: int,
    limit: int = METRICS_BUCKET_LIMIT,
) -> list[dict[str, object]]:
    buckets: dict[int, dict[str, object]] = {}
    for sample in source:
        elapsed = int(sample.get("elapsed_seconds", 0) or 0)
        bucket_index = elapsed // bucket_seconds
        bucket = buckets.get(bucket_index)
        if bucket is None:
            bucket = {
                "bucketIndex": bucket_index,
                "elapsed_seconds": bucket_index * bucket_seconds,
                "count": 0,
                "step": sample.get("step"),
            }
            for key in METRIC_KEYS:
                bucket[key] = 0.0
            buckets[bucket_index] = bucket

        weight = int(sample.get("count", 1) or 1)
        bucket["count"] = int(bucket["count"]) + weight
        bucket["step"] = sample.get("step")
        for key in METRIC_KEYS:
            bucket[key] = float(bucket[key]) + float(sample.get(key, 0) or 0) * weight

    rows = [buckets[key] for key in sorted(buckets)]
    for bucket in rows:
        count = int(bucket.get("count", 0) or 0)
        for key in METRIC_KEYS:
            bucket[key] = float(bucket[key]) / count if count > 0 else 0.0

    current_bucket = current_elapsed // bucket_seconds
    if rows and rows[-1].get("bucketIndex") == current_bucket:
        rows.pop()

    need_lead_in = len(rows) > limit
    return rows[-(limit + 1):] if need_lead_in else rows[-limit:]


@dataclass(frozen=True)
class ModelConfig:
    summary_path: Path
    students: int
    male_count: int | None
    start_time: str
    seconds_per_step: int


class VisualRuntime:
    def __init__(self, config: ModelConfig, checkpoint_path: Path | None = None) -> None:
        self.config = config
        self.checkpoint_path = checkpoint_path
        self.summary = self._load_summary()
        self.model = self._new_model(resume_from_checkpoint=True)
        self.lock = Lock()
        self.playing = False
        self.speed = 1.0
        self.last_wall = time.monotonic()
        self._stop_event = Event()
        self._worker = Thread(target=self._background_loop, name="abm-simulation-worker", daemon=True)
        self._worker.start()

    def _load_summary(self) -> dict[str, Any]:
        with self.config.summary_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _new_model(self, *, resume_from_checkpoint: bool) -> StudentDailyModel:
        if resume_from_checkpoint and self.checkpoint_path and self.checkpoint_path.exists():
            print(f"Resuming from checkpoint: {self.checkpoint_path}")
            model = StudentDailyModel.from_checkpoint(
                self.checkpoint_path,
                summary_path=self.config.summary_path,
                start_time=self.config.start_time,
            )
            print(f"  step={model.campus_steps}  time={model.current_time}  day={model.day}  agents={len(model.students)}")
            return model
        return StudentDailyModel(
            self.config.summary_path,
            student_count=self.config.students,
            male_count=self.config.male_count,
            start_time=self.config.start_time,
            seconds_per_step=self.config.seconds_per_step,
        )

    def save_checkpoint(self) -> None:
        if not self.checkpoint_path:
            return
        self.model.save_checkpoint(self.checkpoint_path)

    def shutdown(self) -> None:
        self._stop_event.set()
        self._worker.join(timeout=5)
        if self.checkpoint_path:
            with self.lock:
                self.save_checkpoint()

    def state(self, *, include_all_paths: bool = False) -> dict[str, Any]:
        with self.lock:
            return self._state_locked(include_all_paths=include_all_paths)

    def control(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        with self.lock:
            if action == "play":
                self.playing = True
                self.last_wall = time.monotonic()
            elif action == "pause":
                self.playing = False
            elif action == "step":
                self.model.step()
                self.last_wall = time.monotonic()
            elif action == "reset":
                self.model = self._new_model(resume_from_checkpoint=False)
                self.playing = False
                self.last_wall = time.monotonic()
                self.save_checkpoint()
            elif action == "speed":
                value = float(payload.get("value", self.speed))
                if value <= 0:
                    raise ValueError("speed must be positive")
                self.speed = value
                self.last_wall = time.monotonic()
            else:
                raise ValueError(f"unknown action: {action!r}")
            return self._state_locked(include_all_paths=True)

    def metrics_history(self, tail: int | None = None) -> dict[str, Any]:
        with self.lock:
            return self.model.metrics_history(tail=tail)

    def agent_metrics(self, agent_id: int) -> dict[str, Any]:
        with self.lock:
            for student in self.model.students:
                if int(student.unique_id) == agent_id:
                    current_elapsed = int(self.model.elapsed_seconds)
                    hourly_source = getattr(student, "metrics_hourly_archive", [])
                    if not hourly_source:
                        hourly_source = getattr(student, "metrics_history", [])
                    hourly = aggregate_metric_buckets(
                        list(hourly_source),
                        bucket_seconds=3600,
                        current_elapsed=current_elapsed,
                    )
                    daily = aggregate_metric_buckets(
                        list(getattr(student, "metrics_hourly_archive", [])),
                        bucket_seconds=86400,
                        current_elapsed=current_elapsed,
                    )
                    return {
                        "agent_id": agent_id,
                        "hourly": hourly,
                        "daily": daily,
                        "metrics_history": hourly,
                    }
            return {
                "agent_id": agent_id,
                "hourly": [],
                "daily": [],
                "metrics_history": [],
                "error": "agent not found",
            }

    def _background_loop(self) -> None:
        while not self._stop_event.is_set():
            with self.lock:
                sleep_seconds = self._advance_locked()
            self._stop_event.wait(sleep_seconds)

    def _advance_locked(self) -> float:
        if not self.playing:
            self.last_wall = time.monotonic()
            return BACKGROUND_IDLE_SLEEP_SECONDS

        interval = self.model.seconds_per_step / self.speed
        now = time.monotonic()
        due_steps = int((now - self.last_wall) // interval)
        steps = min(due_steps, MAX_STEPS_PER_ADVANCE)
        if steps <= 0:
            elapsed = now - self.last_wall
            return max(0.001, min(BACKGROUND_IDLE_SLEEP_SECONDS, interval - elapsed))

        prev_steps = self.model.campus_steps
        for _ in range(steps):
            self.model.step()
        if due_steps > MAX_STEPS_PER_ADVANCE:
            self.last_wall = time.monotonic()
        else:
            self.last_wall += steps * interval

        # Auto-save checkpoint every 100 campus steps
        if self.checkpoint_path and self.model.campus_steps // 100 != prev_steps // 100:
            self.save_checkpoint()
        return 0.0 if due_steps > steps else BACKGROUND_IDLE_SLEEP_SECONDS

    def _state_locked(self, *, include_all_paths: bool = False) -> dict[str, Any]:
        state = self.model.snapshot(
            include_metrics_history=False,
            include_agent_last_paths=include_all_paths,
            include_agent_paths=include_all_paths,
        )
        state["server"] = {
            "model": "daily",
            "playing": self.playing,
            "speed": self.speed,
            "sync_interval_seconds": self.model.seconds_per_step / self.speed,
        }
        return state


class VisualHandler(BaseHTTPRequestHandler):
    runtime: VisualRuntime
    viewer_path: Path = VIEWER_TEMPLATE

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path in {"/", "/agent_viewer.html"}:
                self._send_file(self.viewer_path, "text/html; charset=utf-8")
            elif path == "/api/summary":
                self._send_json(self.runtime.summary)
            elif path == "/api/state":
                query = parse_qs(parsed.query)
                include_paths = query.get("paths", ["0"])[0] in {"1", "true", "yes"}
                self._send_json(self.runtime.state(include_all_paths=include_paths))
            elif path == "/api/metrics_history":
                query = parse_qs(parsed.query)
                tail = int(query.get("tail", ["0"])[0] or 0)
                self._send_json(self.runtime.metrics_history(tail=tail if tail > 0 else None))
            elif path == "/api/agent/metrics":
                query = parse_qs(parsed.query)
                agent_id = int(query.get("id", ["0"])[0] or 0)
                self._send_json(self.runtime.agent_metrics(agent_id))
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "not found")
        except Exception as exc:  # pragma: no cover - keeps server debuggable
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/control":
            self.send_error(HTTPStatus.NOT_FOUND, "not found")
            return

        try:
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(body or "{}")
            self._send_json(self.runtime.control(payload))
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, data: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = file_path.read_bytes()
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-store")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def write_viewer_template(path: Path) -> None:
    """Write the current viewer HTML served by the local HTTP server."""
    if path.resolve() == LEGACY_VIEWER_OUTPUT.resolve():
        raise ValueError(f"Refusing to write legacy viewer copy at {LEGACY_VIEWER_OUTPUT}")
    source = VIEWER_TEMPLATE.read_text(encoding="utf-8")
    if path.exists() and path.read_text(encoding="utf-8") == source:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a realtime ABM agent viewer.")
    parser.add_argument("--summary", type=Path, default=Path("map/summary.json"), help="Path to summary.json.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port.")
    parser.add_argument("--students", type=int, default=100, help="Number of students.")
    parser.add_argument("--male-count", type=int, default=80, help="Number of male students (rest are female).")
    parser.add_argument("--start-time", default="07:00:00", help="Simulation start time, HH:MM or HH:MM:SS.")
    parser.add_argument("--seconds-per-step", type=int, default=1, help="Simulated seconds per step.")
    parser.add_argument("--viewer-out", type=Path, default=None, help="Optionally write a copy of the viewer HTML.")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint if available.")
    parser.add_argument("--checkpoint", type=Path, default=Path(".checkpoint.json"), help="Checkpoint file path.")
    args = parser.parse_args()

    checkpoint_path = args.checkpoint if args.resume else None
    if args.resume and not checkpoint_path.exists():
        print(f"Warning: --resume set but checkpoint not found at {checkpoint_path}, starting fresh.")

    config = ModelConfig(
        summary_path=args.summary,
        students=args.students,
        male_count=args.male_count,
        start_time=args.start_time,
        seconds_per_step=args.seconds_per_step,
    )
    runtime = VisualRuntime(config, checkpoint_path=checkpoint_path)
    if args.viewer_out:
        write_viewer_template(args.viewer_out)

    # Graceful shutdown: save checkpoint on Ctrl+C
    def _shutdown(signum, frame):
        print(f"\nShutting down...")
        runtime.shutdown()
        if runtime.checkpoint_path:
            print(f"Checkpoint saved to {runtime.checkpoint_path}")
        os._exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    handler = type("ConfiguredVisualHandler", (VisualHandler,), {
        "runtime": runtime,
        "viewer_path": VIEWER_TEMPLATE.resolve(),
    })
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"ABM viewer: http://{args.host}:{args.port}/")
    if runtime.checkpoint_path:
        print(f"Checkpoint: {runtime.checkpoint_path}  (auto-save every 100 steps)")
    print(f"Viewer HTML served from {VIEWER_TEMPLATE}")
    if args.viewer_out:
        print(f"Viewer HTML copy written to {args.viewer_out}")
    try:
        server.serve_forever()
    finally:
        runtime.shutdown()

if __name__ == "__main__":
    main()
