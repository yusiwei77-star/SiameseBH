"""Trace animation loop over server ticks to find caterpillar root cause."""
from __future__ import annotations
import math

CELL = 8
POLL_MS = 150

def seg_dist(a, b):
    return math.hypot(b[0]-a[0], b[1]-a[1])

def cum_dists(path):
    d = [0.0]
    for i in range(1, len(path)): d.append(d[-1] + seg_dist(path[i-1], path[i]))
    return d

def point_at_dist(path, dists, target):
    target = max(0, min(dists[-1], target))
    for i in range(len(path)-1):
        seg = dists[i+1] - dists[i]
        if seg <= 0: continue
        if target <= dists[i+1] + 1e-9:
            t = (target - dists[i]) / seg
            return (path[i][0] + (path[i+1][0]-path[i][0])*t, path[i][1] + (path[i+1][1]-path[i][1])*t)
    return path[-1]

def cell_center(p):
    return (p[0]*CELL + CELL/2, p[1]*CELL + CELL/2)

def px_dist(a, b):
    return math.hypot(b[0]-a[0], b[1]-a[1])

def duration_for_route(state, route_px, walk_speed=1.0, point_count=2):
    speed = max(0.01, state.get("speed", 1))
    secs = state.get("seconds_per_step", 1)
    tick_ms = (secs / speed) * 1000
    base = tick_ms * (route_px / CELL) / max(0.01, walk_speed)
    slack = min(POLL_MS * 1.2, base * 0.30)
    dur = base + slack
    vm = min(360, max(40, (point_count-1)*24))
    return max(vm, min(6000, dur))

def simulate_ticks(speed, num_ticks=20):
    """Simulate animation loop for num_ticks server steps."""
    tick_ms = 1000 / speed  # wall-clock ms per server tick

    # A path with alternating diagonal and orthogonal segments (typical BFS zigzag)
    # Simulate a path from (0,0) going down-right
    path_cells = []
    x, y = 0, 0
    for i in range(50):
        path_cells.append((x, y))
        if i % 3 == 0:
            x += 1; y += 1  # diagonal
        elif i % 3 == 1:
            y += 1  # down
        else:
            x += 1  # right

    path_dists = cum_dists(path_cells)
    total_grid_dist = path_dists[-1]

    state = {"seconds_per_step": 1, "speed": speed, "playing": True}

    # Animation state
    current_anim = {
        "from_px": cell_center(path_cells[0]),
        "to_px": None,
        "duration": 0,
        "start_time": 0,
        "route_px": 0,
    }

    now = 0.0  # wall-clock time in ms
    sim_time = 0.0  # simulation elapsed seconds
    dist_traveled_grid = 0.0  # agent's grid distance (simulation)
    sim_tick = 0

    history = []  # (now, px_per_s, grid_dist, px_dist_this_tick)

    # Simulate play loop
    poll_interval = POLL_MS  # ms between polls
    last_poll = -poll_interval
    state_received_count = 0

    while sim_tick < num_ticks:
        now += poll_interval  # next poll

        # Server advances
        elapsed_sim = (now / 1000) * speed
        new_sim_tick = int(elapsed_sim / state["seconds_per_step"])
        sim_step_changed = new_sim_tick > sim_tick

        if sim_step_changed:
            sim_tick = new_sim_tick
            # Agent advances 1 grid unit per tick
            dist_traveled_grid += 1.0  # speed=1.0 cells/tick
            state_received_count += 1

            # Build new render_motion data
            start_dist = min(dist_traveled_grid, total_grid_dist - 1.0)
            end_dist = min(start_dist + 1.0, total_grid_dist)

            # New target from render_motion
            target_px = point_at_dist(path_cells, path_dists, end_dist)

            # "from" = current interpolated position
            if current_anim["duration"] > 0:
                raw = (now - current_anim["start_time"]) / current_anim["duration"]
                raw = max(0, min(1, raw))
                from_px = (
                    current_anim["from_px"][0] + (current_anim["to_px"][0] - current_anim["from_px"][0]) * raw,
                    current_anim["from_px"][1] + (current_anim["to_px"][1] - current_anim["from_px"][1]) * raw,
                )
            else:
                from_px = target_px

            # Build polyline from from_px to target_px
            # Simplified: just from->to (with intermediate cell centers)
            route_px = px_dist(from_px, target_px)
            dur = duration_for_route(state, route_px)

            current_anim = {
                "from_px": from_px,
                "to_px": target_px,
                "duration": dur,
                "start_time": now,
                "route_px": route_px,
            }

            # Calculate instantaneous speed this tick
            if route_px > 0.01 and dur > 0:
                px_per_s = route_px / dur * 1000
            else:
                px_per_s = 0

            # Distance agent SHOULD be at (from simulation)
            expected_px = point_at_dist(path_cells, path_dists, dist_traveled_grid)
            rendered_px = from_px  # where animation starts from
            lag_px = px_dist(expected_px, rendered_px)

            history.append((now, px_per_s, dist_traveled_grid, route_px, lag_px, dur))

    # Analyze results
    print(f"\n{'='*70}")
    print(f"Speed={speed}x  tick={tick_ms:.0f}ms  ticks={num_ticks}  polls_per_tick={tick_ms/POLL_MS:.1f}")
    print(f"{'='*70}")
    print(f"{'tick':>5} {'time':>8} {'dur':>8} {'route_px':>10} {'speed':>10} {'lag_px':>10} {'grid_dist':>12}")
    print(f"{'':>5} {'(ms)':>8} {'(ms)':>8} {'(px)':>10} {'(px/s)':>10} {'(px)':>10} {'(grid)':>12}")

    speeds = []
    lags = []
    for i, (t, spd, gd, rp, lp, dur) in enumerate(history):
        speeds.append(spd)
        lags.append(lp)
        print(f"{i+1:>5} {t:>8.0f} {dur:>8.0f} {rp:>10.2f} {spd:>10.1f} {lp:>10.2f} {gd:>12.3f}")

    if speeds:
        avg_speed = sum(speeds) / len(speeds)
        deviations = [abs(s - avg_speed) / avg_speed * 100 for s in speeds]
        print(f"\nSpeed stats: avg={avg_speed:.1f} px/s  max_dev={max(deviations):.1f}%  min={min(speeds):.1f}  max={max(speeds):.1f}")
        print(f"Lag stats: avg={sum(lags)/len(lags):.2f}px  max={max(lags):.2f}px  growing={lags[-1] > lags[0] + 1}")

    return avg_speed, max(deviations) if speeds else 0


print("TRACING ANIMATION LOOP (NEW FORMULA: 30% slack cap)")
print("=" * 70)

for speed in [1, 2, 5, 10]:
    simulate_ticks(speed, num_ticks=15)

