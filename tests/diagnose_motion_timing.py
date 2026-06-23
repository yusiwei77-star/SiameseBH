"""Diagnose agent movement timing issues.

Measures:
1. The gap between render_motion prediction completion and next state arrival
2. Animation duration vs actual tick interval at various speeds
3. Play/pause animation speed difference
"""
from __future__ import annotations

import json
import math
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


BASE = "http://127.0.0.1:8789"
CELL = 8  # pixels per grid cell
STATE_REFRESH_INTERVAL_MS = 150
RENDER_MOTION_REFRESH_SLACK_MS = STATE_REFRESH_INTERVAL_MS * 1.2  # 180ms


def fetch(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_control(action: str, value: float | None = None) -> dict[str, Any]:
    payload = {"action": action}
    if value is not None:
        payload["value"] = value
    req = urllib.request.Request(
        f"{BASE}/api/control",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def step_distance(a: dict, b: dict) -> float:
    return math.hypot(b["col"] - a["col"], b["row"] - a["row"])


def cumulative_distances(path: list[dict]) -> list[float]:
    if not path:
        return []
    dists = [0.0]
    for i in range(1, len(path)):
        dists.append(dists[-1] + step_distance(path[i - 1], path[i]))
    return dists


@dataclass
class MotionSample:
    agent_id: int
    phase: str
    path_len: int
    path_idx: int
    movement_progress: float
    speed: float
    render_motion: dict | None


def sample_moving_agents(state: dict) -> list[MotionSample]:
    samples = []
    for agent in state.get("agents", []):
        ctx = agent.get("context", {})
        profile = agent.get("profile", {})
        phase = ctx.get("phase", "IDLE")
        if phase not in ("MOVING",):
            continue
        rm = ctx.get("render_motion")
        samples.append(
            MotionSample(
                agent_id=agent["id"],
                phase=phase,
                path_len=len(ctx.get("path", [])),
                path_idx=ctx.get("path_index", 0),
                movement_progress=ctx.get("movement_progress", 0),
                speed=profile.get("normal_walk_speed_cells_per_step", 1.0),
                render_motion=rm,
            )
        )
    return samples


def compute_new_duration(tick_interval_ms: float, route_distance_px: float, walk_speed: float) -> float:
    """New unified durationForRoute formula with proportional slack."""
    base = tick_interval_ms * (route_distance_px / CELL) / walk_speed
    slack = min(STATE_REFRESH_INTERVAL_MS * 1.2, base * 0.30)
    return base + slack


def analyze_timing(state: dict, speed: float) -> dict:
    """Analyze timing mismatch for current state."""
    seconds_per_step = state.get("seconds_per_step", 1)
    sync_interval = state.get("server", {}).get("sync_interval_seconds", 1)
    playing = state.get("server", {}).get("playing", False)

    # Server tick interval in wall-clock ms
    tick_interval_ms = (seconds_per_step / speed) * 1000

    # OLD animation duration (before fix) - for comparison
    old_playing_duration = (seconds_per_step / speed) * 1000 + RENDER_MOTION_REFRESH_SLACK_MS

    # NEW unified animation duration for 1 cell (8px) at walk speed 1.0
    new_duration_1cell = compute_new_duration(tick_interval_ms, CELL, 1.0)

    # Old paused duration (no slack) - for comparison
    old_paused_duration = tick_interval_ms * (CELL / CELL) / 1.0

    # Prediction completion time (when extrapolation hits t=1.0)
    prediction_completion_ms = seconds_per_step / speed * 1000

    # Freeze window: worst case after prediction completes
    freeze_ms = max(0, STATE_REFRESH_INTERVAL_MS - prediction_completion_ms)

    moving = sample_moving_agents(state)

    return {
        "speed": speed,
        "playing": playing,
        "seconds_per_step": seconds_per_step,
        "sync_interval_s": sync_interval,
        "tick_interval_ms": tick_interval_ms,
        "prediction_completion_ms": prediction_completion_ms,
        "poll_interval_ms": STATE_REFRESH_INTERVAL_MS,
        "freeze_window_ms": freeze_ms,
        "freeze_window_pct": round(freeze_ms / max(tick_interval_ms, 1) * 100, 1),
        "old_playing_ms": old_playing_duration,
        "new_unified_ms": new_duration_1cell,
        "old_paused_ms": old_paused_duration,
        "old_slack_pct": round(
            (old_playing_duration - tick_interval_ms) / max(tick_interval_ms, 1) * 100, 1
        ),
        "new_slack_pct": round(
            (new_duration_1cell - tick_interval_ms) / max(tick_interval_ms, 1) * 100, 1
        ),
        "old_play_pause_ratio": round(old_playing_duration / max(old_paused_duration, 1), 2),
        "new_play_pause_ratio": 1.0,  # Unified! Same formula for both.
        "moving_agents": len(moving),
        "sample_agent": moving[0].__dict__ if moving else None,
    }


def print_analysis(results: dict) -> None:
    print(f"""
{'='*70}
SPEED = {results['speed']}x  |  Playing: {results['playing']}  |  Moving agents: {results['moving_agents']}
{'='*70}

Server timing:
  tick interval (wall):    {results['tick_interval_ms']:.0f}ms
  poll interval:           {results['poll_interval_ms']}ms
  freeze window (worst):   {results['freeze_window_ms']:.0f}ms ({results['freeze_window_pct']}% of tick)

Animation duration (1-cell move):
  OLD playing:             {results['old_playing_ms']:.0f}ms  (slack +{results['old_slack_pct']}%)
  OLD paused:              {results['old_paused_ms']:.0f}ms
  >>> NEW unified:         {results['new_unified_ms']:.0f}ms  (slack +{results['new_slack_pct']}%)

Play/pause speed ratio:
  OLD:                     {results['old_play_pause_ratio']}x  (different formulas)
  >>> NEW:                 {results['new_play_pause_ratio']}x  (unified formula!)
""")
    if results["sample_agent"]:
        sa = results["sample_agent"]
        rm = sa.get("render_motion") or {}
        print(f"""Sample moving agent #{sa['agent_id']}:
  path_len={sa['path_len']}  path_idx={sa['path_idx']}
  movement_progress={sa['movement_progress']:.3f}  speed={sa['speed']}
  render_motion: start={rm.get('start_distance', 'N/A'):.3f}
    end={rm.get('end_distance', 'N/A'):.3f}
    total={rm.get('total_distance', 'N/A'):.3f}
""")


def main() -> None:
    print("Diagnosing agent movement timing issues...")
    print(f"Server: {BASE}")

    # Ensure playing and set speed to 1x
    print("\n--- Setting speed=1x, play ---")
    state = post_control("speed", 1.0)
    state = post_control("play", None)
    time.sleep(1.0)  # let simulation run a bit
    state = fetch(f"{BASE}/api/state?paths=1")

    for speed in [1, 2, 5, 10, 20]:
        post_control("speed", float(speed))
        time.sleep(2.0)  # let simulation stabilize at this speed
        state = fetch(f"{BASE}/api/state?paths=1")
        results = analyze_timing(state, float(speed))
        print_analysis(results)

    # Also check paused mode
    print("\n--- Paused mode analysis ---")
    post_control("pause", None)
    time.sleep(0.5)
    state = fetch(f"{BASE}/api/state?paths=1")
    results = analyze_timing(state, 1.0)
    print_analysis(results)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY: OLD vs NEW animation timing")
    print("=" * 70)
    print("""
Fix applied: Unified distance-aware animation duration with proportional slack.

OLD formula (playing):  duration = tick_ms + 180ms_constant
OLD formula (paused):   duration = tick_ms * (distance/CELL) / speed
NEW formula (unified):  duration = tick_ms * (distance/CELL) / speed + proportional_slack
                         where slack = min(180ms, base_duration * 30%)

Key improvements:
  1. Animation duration now scales with actual pixel distance (no more
     fixed duration for variable distances).
  2. Slack is proportional (capped at 30% of base) instead of a flat 180ms,
     preventing absurd overhead at high speeds (was +360% at 20x).
  3. Play and pause modes use the SAME formula → no speed shift when toggling.
""")


if __name__ == "__main__":
    main()
