# SiameseBH — Agent Guide

Agent-based modeling (ABM) workspace simulating campus student daily behavior, built on [Mesa](https://mesa.readthedocs.io/) and driven by the annotated campus map in `map/summary.json`. The repo contains two largely independent parts: the Python simulation (`abm/`, `tests/`) and the browser-based map annotation toolchain (`map/`).

There is **no build system and no dependency manifest** (no `pyproject.toml`, `requirements.txt`, or `package.json`). The only runtime dependency is `mesa`; everything else is the Python standard library. Tests use `pytest`.

## Setup

```bash
pip install mesa pytest
```

Note: verify `mesa` is importable before running anything (`python -c "import mesa"`); it is not vendored.

## Run

```bash
# Start the realtime viewer server (default: 100 students, 80 male, start 07:00:00, 1 simulated second per step)
python -m abm.visual_server
# then open http://127.0.0.1:8789/

python -m abm.visual_server --students 30 --start-time 07:30:00 --seconds-per-step 5
python -m abm.visual_server --resume runs/<run_folder>/   # resume from a checkpointed run
```

`abm/visual_server.py` is a stdlib `ThreadingHTTPServer` that runs a `StudentDailyModel` in a background thread, serves `abm/viewer_template.html`, and exposes a JSON HTTP API (`/api/summary`, `/api/state`, `/api/metrics_history`, `/api/agent/metrics`, plus `/api/control` for play/pause/step/reset/speed). It also serves the bundled handwriting font at `/assets/fonts/mvboli.ttf`. Each run creates a directory `runs/<timestamp>_n<students>_t<start>/` (git-ignored) containing `checkpoint.json`, `metadata.json`, `population_metrics.jsonl`, `social_graph.jsonl`, and per-agent `agents/<gender>_<name>/day_N/{metrics,activities}.jsonl` written by `abm/output.py` (`RunOutputManager`). Checkpoints are auto-saved (every 100 steps and on shutdown) and allow resume.

Map annotation workflow (see `map/README.md`, in Chinese): serve the repo root with `python -m http.server 8788`, annotate terrain in `map/index.html` and regions in `map/region.html`, then regenerate derived data:

```bash
python map/build_summary.py map/annotations.json map/regions.json map/summary.json
python map/render_summary_html.py map/summary.json map/summary_view.html
```

## Test

```bash
python -m pytest tests/ -v          # all tests
python -m pytest tests/test_student_policy.py -v   # single file
```

- Tests are `unittest.TestCase` classes run under pytest; they import the `abm` package from the repo root (run pytest from the project root).
- `tests/helpers.py` provides shared factories — `make_profile`, `make_trait`, `make_state`, `make_variable`, `FakeAgent` — use them when adding tests.
- `tests/trace_animation.py`, `tests/trace_animation2.py`, and `tests/diagnose_motion_timing.py` are **standalone diagnostic scripts, not pytest tests** (they contain no `test_` functions; `diagnose_motion_timing.py` expects a running viewer server).
- Test files and what they cover: `test_student_policy.py` (policy scoring/decisions, metrics bucketing in `visual_server`, checkpoint round-trip), `test_material.py` (`MaterialDynamics`: eating, sleeping, walking, health drift), `test_inner_mind.py` (`InnerMindDynamics`: satisfaction, skills, PAD emotion, mental health), `test_outer_mind.py` (`OuterMindDynamics`: social exchange, closeness, wellbeing), `test_environment_dynamics.py` (compatibility re-export surface), `test_physiopsychological.py`, `test_temporal_academic.py` (course schedule generation/attendance), `test_social_graph.py`, `test_animation_timing.py` (pure-Python reimplementation of the viewer's JS animation timing).
- **Known failures on master** (pre-existing, not regressions): `test_environment_dynamics.py`, `test_physiopsychological.py`, and `test_temporal_academic.py` fail at collection (they import names like `INVITE_TO_EAT`, `update_physiopsychological_state`, `sleep_energy_gain_per_hour` that no longer exist in `abm/environment_dynamics.py`), and `test_inner_mind.py` has 2 failing cases (`test_idle_intrinsic_satisfaction_decays_to_boredom`, `test_pad_projection_uses_intrinsic_activity_and_skill`). The rest of the suite passes.

## Architecture

### `abm/core/` — spatial infrastructure, deliberately no Mesa dependency

- `types.py` — shared dataclasses: `StudentProfile` (identity, home/workplace region ids, meal/walk speeds), `StudentTrait` (Big-Five `personality`, `interests`, `skills`, `physical_health`, `mental_health`, `wellbeing`), `StudentState` (dynamic: `energy`, `satiety`, `emotion` PAD dict, intrinsic/extrinsic satisfaction, social contribution/return), `StudentContext` (runtime: `pos`, `phase` IDLE/MOVING/ACTIVITY, path, current action/intention, activity history). Plus time helpers (`parse_time_to_seconds`, `format_seconds_as_time`) and `pos_payload`.
- `map.py` — `CampusMap` loads `map/summary.json` and exposes terrain/region/entrance lookups, `is_walkable`, cached 4-/8-neighbor caches, `nearest_entrance`.
- `pathfinding.py` — A* (`astar`, `path_to_region`) over walkable cells; `routing.py` — BFS routing helpers; `movement.py` — `step_distance`.

### `abm/agent/` — Mesa-dependent behavior layer

- `student.py` — `DailyStudentAgent` (Mesa `Agent`): per-step update (needs → move along path / run activity / decide next action), metrics recording, snapshot serialization.
- `rules.py` — deterministic rules: candidate region building per activity, fixed `ACTIVITY_DURATIONS`, need updates, activity interruption (e.g. medical).
- `policy.py` — `RuleBasedStudentPolicy`: scores the fixed action space `ACTIONS = ("sleep", "rest", "eat", "study", "exercise", "social", "service")` from profile + trait + state + context + time-of-day and picks a legal action; also handles social invitation accept/reject.

### `abm/model/` — simulation model

- `daily.py` — `StudentDailyModel` (Mesa `Model` + `MultiGrid`). Key conventions: seeded determinism via per-agent RNG streams derived with blake2b from `global_seed:agent_id:stream`; students are gender-split into east/west dormitories by campus midpoint; each `step()` advances all agents, advances the shared `OuterMindDynamics`, appends population metrics (trimmed to the last 13 simulated hours), and compresses completed hours into an hourly archive.
- `schedule.py` — `AcademicScheduleBook` generates stable per-student-per-day course sessions from 5 fixed slots (`COURSE_SLOT_TIMES`, 08:00 through 20:35); attendance is checked once per (student, slot) per day.
- `checkpoint.py` — JSON save/resume of full model state (`save_checkpoint` / `StudentDailyModel.from_checkpoint`); hourly archives in checkpoints are capped at 14 days.

### `abm/environment/` — dynamics equations (the "three minds" split)

Each module defines a frozen `*Config` dataclass of tunable per-hour rates, a frozen `*Delta` dataclass describing what changed, and a `*Dynamics` class whose `advance(...)` mutates `StudentState`/`StudentTrait` in place and returns the delta. Module-level defaults: `DEFAULT_MATERIAL_DYNAMICS`, `DEFAULT_INNER_MIND_DYNAMICS`.

- `material.py` — body: awake energy/satiety drain, sleep recovery, eating (exponential approach to target satiety, per-profile `meal_speed`), walking energy cost, physical health damage/recovery from low/high energy+satiety.
- `inner_mind.py` — single-agent psychology for `study`/`exercise`/`music`/`game` actions: intrinsic satisfaction flow toward `interest × mental_health`, skill growth, energy costs, mental-health recovery/damage (neuroticism-scaled), PAD emotion projection.
- `outer_mind.py` — directed social exchange: per-(source, target) closeness that grows with interest-compatibility (cosine similarity) and decays without interaction, cognitive-dissonance cooling of asymmetric ties, social contribution/return memory, extrinsic satisfaction, and slow wellbeing blending.

`abm/environment_dynamics.py` is a thin compatibility re-export (`from .environment import *`); new code should import from `abm.environment`.

### Viewer frontend (`abm/viewer_template.html`)

- The map and both side panels are fitted as **one composition** ("scene"), not the map alone: `PANEL_DESIGN_HEIGHT = 852` reproduces the canonical pre-redesign composition (2736×2504 map + two 340px panels → 1.8906:1 sheet) regardless of viewport size or platform. `panelBaseScale` derives from it; auto-fit only applies until the user manually zooms/pans (`viewUsesAutoFit`).
- Handwriting typography is bundled for cross-platform consistency: `@font-face "SiameseBH MV Boli"` prefers `local("MV Boli")` (Windows) and falls back to `/assets/fonts/mvboli.ttf` (served by `visual_server.py`), with `Kalam` from Google Fonts and generic `cursive` as further fallbacks (`--handwritten-font` / `HANDWRITING_FONT`).
- **Font licensing**: `abm/assets/fonts/mvboli.ttf` is a Microsoft-copyrighted font included for private use only (see `abm/assets/fonts/README.md`). It must be removed before the repository is made public or redistributed.

## Coordinate system — read this before touching spatial code

- `map/summary.json` cells use `{ "row": int, "col": int }` (relative grid, origin stored under `origin`).
- Mesa/simulation positions are `Pos = tuple[int, int]` with **`(x, y) = (col, row)`** (`CampusMap.cell_to_pos` / `pos_to_cell` convert).
- Current map: 342 × 313 cells, ~103k terrain cells, 66 regions.
- Walkable: `road`, `open_ground`, `gate` cells of `available` regions, and entrance cells of available regions. Blocked: `grass`, `water`, `fence`, unavailable gates, and non-entrance `building`/`sports_field` cells — buildings are entered exclusively through their `entrances`.

## Conventions

- Time is modeled in integer seconds; per-step updates scale rates by `seconds_per_step / 3600` (rates are per hour). `second_of_day` wraps at 86400; `day` starts at 1.
- All scalar state values are clamped to [0, 1] via a local `_clamp01`.
- Style: `from __future__ import annotations` at the top of every module, stdlib type hints (`str | None`, `dict[str, float]`), dataclasses for data containers, f-strings. Match the surrounding code.
- Simulations must stay deterministic for a given `rng` seed — derive randomness from the model's seeded RNG streams, never from global `random` or wall-clock.
- The model asserts every student stays on a walkable cell each step (`RuntimeError` otherwise); preserve that invariant when changing movement.
- Do not commit `runs/`, `debug/`, or `__pycache__/` (git-ignored). The viewer HTML is `abm/viewer_template.html`; the server refuses to write the legacy copy at `debug/agent_viewer.html`.

## Documentation caveat

`README.md` / `README_zh.md` are partly **out of date**: they describe an `abm/environment/` split into `physiology.py`, `resource_queueing.py`, `social_dynamics.py`, `spatial_traffic.py`, `temporal_academic.py`, `weather.py` and test files like `test_resource_queueing.py` that no longer exist. The actual layout is the material / inner-mind / outer-mind split documented above — trust the code and this file over the READMEs on those points.
