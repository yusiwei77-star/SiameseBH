# SiameseBH ABM Workspace

Agent-based modeling workspace for campus student behavior simulation, built on Mesa and powered by the annotated map data in `map/summary.json`.

## Layout

- `map/` — annotation tools, source map files, `summary.json`, and standalone map viewer. See [map/README.md](map/README.md) for details.
- `abm/` — simulation source modules:
  - `abm/visual_server.py` — realtime ABM agent viewer served through a local HTTP API.
  - `abm/core/` — types and spatial infrastructure (no Mesa dependency):
    - `types.py` — shared data types (`StudentProfile`, `StudentState`, `StudentTrait`, `StudentContext`) and time utilities.
    - `map.py` — loads `map/summary.json` and exposes terrain, region, entrance, and movement helpers.
    - `pathfinding.py` — A* path planning over campus walkable cells (`astar`, `path_to_region`).
    - `routing.py` — BFS routing helpers for student activity candidate generation.
  - `abm/agent/` — student agent and behavior rules (depends on Mesa + core):
    - `student.py` — `DailyStudentAgent` (Mesa Agent) with step logic and snapshot serialization.
    - `rules.py` — deterministic filters, candidate building, need updates, and activity interruption.
    - `policy.py` — shared rule-based policy network (`RuleBasedStudentPolicy`) mapping profile + state to daily actions.
  - `abm/model/` — simulation model and supporting infrastructure:
    - `daily.py` — schedule-free daily behavior model (`StudentDailyModel`).
    - `schedule.py` — deterministic daily course schedule generation.
    - `checkpoint.py` — model state serialization for save/resume.
  - `abm/environment/` — environment dynamics subpackage:
    - `physiology.py` — physio-psychological state updates (energy, satiety, stress, health, wellbeing).
    - `resource_queueing.py` — canteen queueing and meal duration calculations.
    - `social_dynamics.py` — social invitations, relationship tiers, emotional contagion.
    - `spatial_traffic.py` — spatial movement, congestion, accidents, weather effects.
    - `temporal_academic.py` — circadian sleep cycles, course attendance, academic stress.
    - `weather.py` — weather condition schedule.
    - `_helpers.py` — internal math utilities (stress clamping, time windows).
  - `abm/environment_dynamics.py` — re-export of all environment dynamics for backward compatibility.
- `tests/` — unit tests covering policy decisions, resource queueing, temporal/academic dynamics, environment dynamics, and physio-psychological state updates.
- `debug/` — generated debug outputs. The live viewer HTML is `abm/viewer_template.html`.

## Coordinates

The map summary uses relative grid cells:

```json
{ "row": 17, "col": 128 }
```

Mesa uses `(x, y)` positions:

```python
(x, y) = (col, row)
```

For the current map:

- width: `342`
- height: `313`
- terrain cells: `103485`
- regions: `66`

## Movement Rules

Default passable cells:

- `road`
- `open_ground`
- `gate` cells whose gate region has `available=true`
- region entrance cells for available regions

Default blocked cells:

- `grass`
- `water`
- `fence`
- unavailable `gate`
- ordinary `building` and `sports_field` cells that are not entrances

Building and sports-field regions are not treated as ordinary walkable terrain. Their `entrances` are the legal access points for behavior logic.

## Quick Start

Install dependencies and run the visual server:

```powershell
pip install mesa
python -m abm.visual_server
```

Then open:

```text
http://127.0.0.1:8789/
```

This launches the daily behavior model with 10 students. The viewer shows agents moving across the campus map in real time.

Useful options:

```powershell
python -m abm.visual_server --port 8789
python -m abm.visual_server --students 30 --start-time 07:30:00
python -m abm.visual_server --students 50 --seconds-per-step 5
```

## Realtime Agent Viewer

Start the reusable ABM visualization server:

```powershell
python -m abm.visual_server
```

Open `http://127.0.0.1:8789/`.

The viewer:

- Runs a `StudentDailyModel` in the local Python server.
- Uses `map/summary.json` as a layered, low-opacity parchment-style base map.
- Draws agents as high-contrast points colored by state.
- Interpolates agent drawing between discrete grid steps, so movement appears continuous while the model state remains grid-based.
- Shows an agent tooltip near the mouse on hover.
- Locks an agent selection on click and renders that agent's full route.
- Supports `Play/Pause`, `Step`, `Reset`, and playback speeds `0.5x/1x/2x/5x/10x`.
- Displays average population metrics (energy, satiety, stress, health, social connection, focus, wellbeing) with live time-series charts.
- Renders a social network graph in the right panel; click a node to select that agent on the map.
- Map layers (paper, terrain, water, roads, buildings, border) can be toggled individually.

At `1x`, playback is synchronized to model time: with the default `seconds_per_step=1`, the server advances one model step every 1 real second. The browser displays the authoritative `current_time` returned by the server.

## Student Daily Behavior Model

The `StudentDailyModel` implements a schedule-free daily behavior simulation. Students are modeled with COM-B state and choose activities through a shared rule-based policy. Each student keeps an individual `profile`, and every agent uses the model's shared `RuleBasedStudentPolicy` instance to map `profile + state + time` to an action.

Implemented activities:

- `sleep` — home dormitory.
- `rest` — home dormitory fallback.
- `eat` — `canteen` regions.
- `study` — `library`, `teaching`, and `laboratory` regions.
- `exercise` — sports fields, gym, playground, and ball-court regions.
- `social` — halls, dormitory, and sports/social spaces.
- `service` — service point or hospital.

Decision order:

1. Deterministic filters remove closed, unavailable, entrance-less, unreachable, or non-walkable targets.
2. The candidate set refreshes `state.status`, a COM-B container with `capability`, `opportunity`, and `motivation` values.
3. `mood` is derived from needs, COM-B values, current phase, and activity context. The immediate `reward` is the current mood.
4. The shared policy scores the fixed action space `sleep/rest/eat/study/exercise/social/service` and selects among legal actions. The selected action then uses existing route and activity rules.

### Runtime Variables

Updated every step using `seconds_per_step / 3600`:

- `satiety` — falls while awake, falls faster while waiting in a canteen queue, and rises while eating.
- `energy` — falls while awake, faster during `study` and `exercise`, does not fall while eating, and recovers during `rest` and `sleep`.
- `stress` — rises during study, low satiety, and long canteen queues; falls during rest, exercise, social activity, and sleep.
- `social_need` — rises during isolated activities and falls during social activity.
- `phase` — records runtime execution (`IDLE`, `MOVING`, `ACTIVITY`).

### Canteen Resource & Queueing Dynamics

- `eat` activity is split into `activity_phase=waiting` and `activity_phase=eating`.
- Entering a canteen records the current number of students already waiting in that canteen.
- Queue wait is `0` up to the free queue threshold and then grows linearly per extra waiting student.
- While waiting, `satiety` drops faster; when the queue is long, `stress` rises slowly.
- While eating, `energy` is unchanged and `satiety` rises at a per-profile `meal_speed` rate until it reaches `0.8`.

### Temporal & Academic Cycle Dynamics

- Sleep energy recovery is circadian: night sleep recovers energy fastest, shoulder hours recover less, and daytime sleep recovers much less.
- Each student receives a stable random daily course schedule generated from fixed slots: `08:00-09:35`, `09:50-11:25`, `14:00-15:35`, `15:50-17:25`, and `19:00-20:35`.
- If a student is not in the scheduled teaching region at any checked moment during a course, `stress` rises immediately.
- Each course can trigger the missed-class stress increase at most once.

### Physio-Psychological Dynamics

- `health` — declines when `energy` or `satiety` stays near zero; when health reaches `0`, the state is marked as forced hospitalization.
- `social_connection` — decays during isolated activities and rises during `social`; `social_need` is derived as the inverse.
- `academic_competence` — rises during `study`, but the gain is controlled by `focus`.
- `focus = min(1, (energy + satiety) / 2) * (1 - stress)` — tired, hungry, or stressed students learn inefficiently.
- `stress` — smoothed toward a nonlinear target from low satiety, low energy, academic stress, and low social connection.
- High `stress` reduces sleep recovery efficiency — anxious students recover less energy from the same sleep period.
- `wellbeing` — a slow moving average of energy, satiety, stress, social connection, academic competence, and health.

### Social Dynamics

- Agents can send, receive, accept, and reject social invitations.
- Social relationships evolve through intimacy tiers (`acquaintance` → `friend` → `intimate`).
- Joint activities are supported through invitation accept/reject logic driven by the shared policy.

## Programmatic Use

```python
from abm import (
    CampusMap,
    StudentDailyModel,
    StudentProfile,
    StudentState,
    RuleBasedStudentPolicy,
    astar,
    path_to_region,
    parse_time_to_seconds,
    format_seconds_as_time,
)

# Load the campus map
campus_map = CampusMap.from_file("map/summary.json")
print(campus_map.is_walkable((128, 17)))
print(campus_map.nearest_entrance((100, 100)))

# Pathfinding
path = astar(campus_map, (116, 3), (277, 2))
print(path.reachable, path.cost, path.path[:3])

to_building = path_to_region(campus_map, (116, 3), "building_001")
print(to_building.goal, to_building.target_kind)

# Run a daily behavior simulation
model = StudentDailyModel(
    "map/summary.json",
    student_count=30,
    start_time="07:30:00",
    seconds_per_step=1,
)
for _ in range(3600):
    model.step()

print(model.current_time, model.state_counts(), model.activity_counts())
print(model.average_metrics())

# Inspect individual agents
for student in model.students:
    print(
        student.unique_id,
        student.state.phase,
        student.state.current_activity,
        format_seconds_as_time(model.second_of_day),
    )
```

## Tests

Run all tests:

```powershell
python -m pytest tests/ -v
```

Or run a specific test file:

```powershell
python -m pytest tests/test_student_policy.py -v
python -m pytest tests/test_resource_queueing.py -v
python -m pytest tests/test_temporal_academic.py -v
python -m pytest tests/test_environment_dynamics.py -v
python -m pytest tests/test_physiopsychological.py -v
```

Test coverage:

| Test file | Covers |
|---|---|
| `test_student_policy.py` | Policy action scoring and decision-making across time-of-day and need states |
| `test_resource_queueing.py` | Canteen queue wait-time calculation, meal duration, satiety gain |
| `test_temporal_academic.py` | Circadian sleep energy recovery, course schedule generation, missed-class stress |
| `test_environment_dynamics.py` | Spatial traffic, weather effects, social invitations, relationship tiers |
| `test_physiopsychological.py` | Health decline, stress smoothing, focus calculation, energy/satiety boundary conditions |

## Map Annotation Tools

The `map/` directory contains browser-based annotation tools for terrain and region labeling. See [map/README.md](map/README.md) (Chinese) for the full workflow.
