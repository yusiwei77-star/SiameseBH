"""Trace animation loop — CORRECTED pixel coordinate conversion."""
from __future__ import annotations
import math

CELL = 8
POLL_MS = 150

def seg_dist(a, b): return math.hypot(b[0]-a[0], b[1]-a[1])

def cum_dists(path):
    d = [0.0]
    for i in range(1, len(path)): d.append(d[-1] + seg_dist(path[i-1], path[i]))
    return d

def cell_center(p):
    return (p[0]*CELL + CELL/2, p[1]*CELL + CELL/2)

def point_at_dist_px(path_cells, cum_dists_grid, target_grid_dist):
    """Find PIXEL position at grid-unit distance along path."""
    target = max(0, min(cum_dists_grid[-1], target_grid_dist))
    for i in range(len(path_cells)-1):
        seg = cum_dists_grid[i+1] - cum_dists_grid[i]
        if seg <= 0: continue
        if target <= cum_dists_grid[i+1] + 1e-9:
            t = (target - cum_dists_grid[i]) / seg
            a = cell_center(path_cells[i])
            b = cell_center(path_cells[i+1])
            return (a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t)
    return cell_center(path_cells[-1])

def px_dist(a, b): return math.hypot(b[0]-a[0], b[1]-a[1])

def duration_for_route(state, route_px, walk_speed=1.0, point_count=2):
    speed = max(0.01, state.get("speed", 1))
    secs = state.get("seconds_per_step", 1)
    tick_ms = (secs / speed) * 1000
    base = tick_ms * (route_px / CELL) / max(0.01, walk_speed)
    slack = min(POLL_MS * 1.2, base * 0.30)
    dur = base + slack
    vm = min(360, max(40, (point_count-1)*24))
    return max(vm, min(6000, dur))


def duration_for_route_v2(state, route_px, walk_speed=1.0, point_count=2):
    """NEW: minimal slack (5% cap, max 50ms)."""
    speed = max(0.01, state.get("speed", 1))
    secs = state.get("seconds_per_step", 1)
    tick_ms = (secs / speed) * 1000
    base = tick_ms * (route_px / CELL) / max(0.01, walk_speed)
    slack = min(50, min(POLL_MS * 0.5, base * 0.05))
    dur = base + slack
    vm = min(360, max(40, (point_count-1)*24))
    return max(vm, min(6000, dur))


def simulate(speed, num_ticks=20, dur_fn=duration_for_route):
    tick_ms = 1000 / speed

    # Path: alternating zigzag (typical BFS output)
    path_cells = []
    x, y = 0, 0
    for i in range(80):
        path_cells.append((x, y))
        if i % 4 == 0:
            x += 1; y += 1
        elif i % 4 == 1:
            y += 1
        elif i % 4 == 2:
            x += 1; y += 1
        else:
            x += 1

    path_dists = cum_dists(path_cells)
    total_dist = path_dists[-1]

    state = {"seconds_per_step": 1, "speed": speed, "playing": True}

    current_anim = {"from_px": cell_center(path_cells[0]), "to_px": cell_center(path_cells[0]),
                     "duration": 0, "start_time": 0, "route_px": 0}

    now = 0.0
    sim_grid_dist = 0.0
    sim_tick = 0
    history = []

    while sim_tick < num_ticks:
        now += POLL_MS
        elapsed_sim = (now / 1000) * speed
        new_tick = int(elapsed_sim / state["seconds_per_step"])

        if new_tick > sim_tick:
            sim_tick = new_tick
            sim_grid_dist = min(sim_tick * 1.0, total_dist - 0.01)

            # New render_motion target (in pixel coords)
            end_grid = min(sim_grid_dist + 1.0, total_dist)
            target_px = point_at_dist_px(path_cells, path_dists, end_grid)

            # Current interpolated position (from old animation)
            if current_anim["duration"] > 0:
                raw = (now - current_anim["start_time"]) / current_anim["duration"]
                raw = max(0, min(1, raw))
                old_from = current_anim["from_px"]
                old_to = current_anim["to_px"]
                from_px = (old_from[0] + (old_to[0]-old_from[0])*raw,
                           old_from[1] + (old_to[1]-old_from[1])*raw)
            else:
                from_px = target_px

            route_px = px_dist(from_px, target_px)
            dur = dur_fn(state, route_px)

            current_anim = {
                "from_px": from_px,
                "to_px": target_px,
                "duration": dur,
                "start_time": now,
                "route_px": route_px,
            }

            # Where the agent SHOULD be (simulation ground truth)
            expected_px = point_at_dist_px(path_cells, path_dists, sim_grid_dist)
            lag_px = px_dist(expected_px, from_px)

            if route_px > 0.01 and dur > 0:
                px_per_s = route_px / dur * 1000
            else:
                px_per_s = 0

            history.append((now, px_per_s, sim_grid_dist, route_px, lag_px, dur))

    speeds = [h[1] for h in history]
    lags = [h[4] for h in history]

    print(f"\nSpeed={speed}x tick={tick_ms:.0f}ms")
    print(f"{'tick':>5} {'time':>8} {'dur':>8} {'route_px':>8} {'speed':>10} {'lag':>8} {'lag_cells':>10}")
    for i, (t, spd, gd, rp, lp, dur) in enumerate(history):
        print(f"{i+1:>5} {t:>8.0f} {dur:>8.0f} {rp:>8.1f} {spd:>10.1f} {lp:>8.1f} {lp/CELL:>10.2f}")

    if speeds:
        valid = [s for s in speeds if s > 0.1]
        avg = sum(valid)/len(valid) if valid else 0
        devs = [abs(s-avg)/avg*100 for s in valid]
        print(f"  avg_speed={avg:.1f} px/s  max_dev={max(devs) if devs else 0:.1f}%  "
              f"lag: avg={sum(lags)/len(lags):.1f}px  max={max(lags):.1f}px  "
              f"growing={lags[-1] > lags[0] + 2 if len(lags) > 1 else False}")
    return avg, max(devs) if devs else 0


print("=" * 70)
print("OLD FORMULA (30% slack cap)")
print("=" * 70)
for speed in [1, 2, 5, 10]:
    simulate(speed, 15, duration_for_route)

print("\n\n" + "=" * 70)
print("NEW FORMULA (5% slack cap, max 50ms)")
print("=" * 70)
for speed in [1, 2, 5, 10]:
    simulate(speed, 15, duration_for_route_v2)
