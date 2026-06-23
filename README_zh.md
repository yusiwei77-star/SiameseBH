# SiameseBH 校园ABM仿真工作区

基于Mesa的校园学生行为Agent-Based Modeling仿真工作区，使用 `map/summary.json` 中的标注地图数据驱动。

## 目录结构

- `map/` — 标注工具、原始地图文件、`summary.json` 以及独立地图查看器。详见 [map/README.md](map/README.md)。
- `abm/` — 仿真核心模块：
  - `abm/visual_server.py` — 通过本地HTTP API提供实时ABM智能体可视化。
  - `abm/core/` — 数据类型与空间基础设施（无Mesa依赖）：
    - `types.py` — 共享数据类型（`StudentProfile`、`StudentState`、`StudentTrait`、`StudentContext`）及时间工具函数。
    - `map.py` — 加载 `map/summary.json`，提供地形、区域、入口及移动辅助函数。
    - `pathfinding.py` — 校园可行走网格上的A*路径规划（`astar`、`path_to_region`）。
    - `routing.py` — BFS路由辅助函数，用于学生活动候选生成。
  - `abm/agent/` — 学生智能体与行为规则（依赖Mesa + core）：
    - `student.py` — `DailyStudentAgent`（Mesa Agent），包含步进逻辑与快照序列化。
    - `rules.py` — 确定性过滤器、候选目标构建、需求更新及活动中断规则。
    - `policy.py` — 共享的基于规则的行为策略网络（`RuleBasedStudentPolicy`），将 profile + state 映射为日常行为。
  - `abm/model/` — 仿真模型与支撑基础设施：
    - `daily.py` — 无课表驱动的日常行为模型（`StudentDailyModel`）。
    - `schedule.py` — 确定性每日课程表生成。
    - `checkpoint.py` — 模型状态序列化，支持存档与恢复。
  - `abm/environment/` — 环境动态子包：
    - `physiology.py` — 生理心理状态更新（精力、饱腹、压力、健康、幸福感）。
    - `resource_queueing.py` — 食堂排队与就餐时长计算。
    - `social_dynamics.py` — 社交邀请、关系层级、情绪传染。
    - `spatial_traffic.py` — 空间移动、拥挤、事故、天气影响。
    - `temporal_academic.py` — 昼夜睡眠节律、课程出勤、学业压力。
    - `weather.py` — 天气状况调度。
    - `_helpers.py` — 内部数学工具（压力钳制、时间窗口）。
  - `abm/environment_dynamics.py` — 所有环境动态的重新导出，用于向后兼容。
- `tests/` — 单元测试，覆盖策略决策、资源排队、时间/学业动态、环境动态及生理心理状态更新。
- `debug/` — 生成的调试输出。实时查看器HTML位于 `abm/viewer_template.html`。

## 坐标系统

地图汇总数据使用相对网格坐标：

```json
{ "row": 17, "col": 128 }
```

Mesa使用 `(x, y)` 坐标：

```python
(x, y) = (col, row)
```

当前地图参数：

- 宽度：`342`
- 高度：`313`
- 地形格数：`103485`
- 区域数：`66`

## 移动规则

默认可通行格：

- `road`（道路）
- `open_ground`（空地）
- `gate`（大门）所在区域 `available=true` 的格子
- 可用区域的入口格

默认阻挡格：

- `grass`（草地）
- `water`（水域）
- `fence`（围栏）
- 不可用区域的 `gate`
- 非入口的普通 `building`（建筑）和 `sports_field`（运动场）格子

建筑和运动场区域不被视为普通可行走地形，其 `entrances`（入口）是行为逻辑的合法访问点。

## 快速开始

安装依赖并启动可视化服务：

```powershell
pip install mesa
python -m abm.visual_server
```

然后打开：

```text
http://127.0.0.1:8789/
```

这会启动包含10名学生的日常行为模型。查看器会实时展示智能体在校园地图上的移动。

常用参数：

```powershell
python -m abm.visual_server --port 8789
python -m abm.visual_server --students 30 --start-time 07:30:00
python -m abm.visual_server --students 50 --seconds-per-step 5
```

## 实时智能体查看器

启动可复用的ABM可视化服务：

```powershell
python -m abm.visual_server
```

打开 `http://127.0.0.1:8789/`。

查看器功能：

- 在本地Python服务器中运行 `StudentDailyModel`。
- 以低透明度羊皮纸风格分层渲染 `map/summary.json` 底图。
- 智能体以高对比度圆点绘制，按状态着色。
- 在离散网格步之间插值绘制智能体，使移动看起来连续，而模型状态仍保持网格化。
- 鼠标悬停时在智能体附近显示工具提示。
- 点击智能体可锁定选择并渲染其完整路径。
- 支持 `播放/暂停`、`单步`、`重置`，以及 `0.5x/1x/2x/5x/10x` 播放速度。
- 显示群体平均指标（精力、饱腹、压力、健康、社交联系、专注力、幸福感），配有实时折线图。
- 右侧面板渲染社交网络图；点击节点可在地图上选中对应智能体。
- 地图图层（纸纹、地形、水域、道路、建筑、边框）可独立开关。

`1x` 速度下，播放与模型时间同步：默认 `seconds_per_step=1`，服务端每1真秒推进1个模型步。浏览器显示服务端返回的权威 `current_time`。

## 学生日常行为模型

`StudentDailyModel` 实现了无课表驱动的日常行为仿真。学生以COM-B状态建模，通过共享的基于规则的策略选择活动。每个学生保留独立的 `profile`，所有智能体使用模型共享的 `RuleBasedStudentPolicy` 实例将 `profile + state + time` 映射为行为。

已实现的活动：

- `sleep`（睡眠）— 所在宿舍。
- `rest`（休息）— 所在宿舍的备用行为。
- `eat`（就餐）— `canteen`（食堂）区域。
- `study`（学习）— `library`（图书馆）、`teaching`（教学楼）和 `laboratory`（实验室）区域。
- `exercise`（锻炼）— 运动场、健身房、操场和球场区域。
- `social`（社交）— 大厅、宿舍及运动/社交空间。
- `service`（服务）— 服务点或医院。

### 决策顺序

1. 确定性过滤器移除关闭、不可用、无入口、不可达或不可行走的目标。
2. 候选集刷新 `state.status`（COM-B容器，包含 `capability`、`opportunity`、`motivation` 值）。
3. `mood`（情绪）由需求、COM-B值、当前阶段和活动上下文推导得出。即时 `reward` 即为当前情绪。
4. 共享策略对固定动作空间 `sleep/rest/eat/study/exercise/social/service` 打分，并在合法动作中选择。选定动作随后使用已有的路径和活动规则执行。

### 运行时变量

每步使用 `seconds_per_step / 3600` 更新：

- `satiety`（饱腹）— 清醒时下降，在食堂排队等待时下降更快，就餐时回升。
- `energy`（精力）— 清醒时下降，`study` 和 `exercise` 期间下降更快，就餐时不下降，`rest` 和 `sleep` 期间恢复。
- `stress`（压力）— 学习、低饱腹和长时间排队时上升；休息、锻炼、社交和睡眠时下降。
- `social_need`（社交需求）— 独处活动时上升，社交活动时下降。
- `phase`（阶段）— 记录运行时执行状态（`IDLE`、`MOVING`、`ACTIVITY`）。

### 食堂资源与排队动态

- `eat` 活动分为 `activity_phase=waiting`（等待）和 `activity_phase=eating`（就餐）。
- 进入食堂时记录该食堂当前排队人数。
- 排队等待时间在免费排队阈值内为 `0`，之后随额外排队人数线性增长。
- 等待期间 `satiety` 下降更快；排队较长时 `stress` 缓慢上升。
- 就餐期间 `energy` 不变，`satiety` 以每位学生不同的 `meal_speed` 速率上升直至达到 `0.8`。

### 时间与学业周期动态

- 睡眠精力恢复具有昼夜节律：夜间睡眠恢复最快，晨昏时段恢复较少，白天睡眠恢复大幅减少。
- 每个学生获得一份稳定的随机每日课表，由固定时段生成：`08:00-09:35`、`09:50-11:25`、`14:00-15:35`、`15:50-17:25`、`19:00-20:35`。
- 若上课期间学生在任意检查时刻不在排定的教学区域，`stress` 立即上升。
- 每门课最多触发一次缺课压力增长。

### 生理心理动态

- `health`（健康）— 当 `energy` 或 `satiety` 长期处于近零水平时下降；健康值归零时状态标记为强制就医。
- `social_connection`（社交联系）— 独处活动时衰减，`social` 时增强；`social_need` 为其反向推导。
- `academic_competence`（学业能力）— 在 `study` 期间提升，但增幅受 `focus` 控制。
- `focus = min(1, (energy + satiety) / 2) * (1 - stress)` — 疲惫、饥饿或高压下的学生学习效率降低。
- `stress` — 向非线性目标值平滑收敛，该目标由低饱腹、低精力、学业压力和低社交联系综合决定。
- 高 `stress` 会降低睡眠恢复效率——焦虑的学生在相同睡眠时间内恢复的精力更少。
- `wellbeing`（幸福感）— 由精力、饱腹、压力、社交联系、学业能力和健康的慢速移动平均计算。

### 社交动态

- 智能体可发送、接收、接受和拒绝社交邀请。
- 社交关系通过亲密度层级演化（`acquaintance` 相识 → `friend` 朋友 → `intimate` 亲密）。
- 联合活动通过共享策略驱动的邀请接受/拒绝逻辑实现。

## 编程接口

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

# 加载校园地图
campus_map = CampusMap.from_file("map/summary.json")
print(campus_map.is_walkable((128, 17)))
print(campus_map.nearest_entrance((100, 100)))

# 路径规划
path = astar(campus_map, (116, 3), (277, 2))
print(path.reachable, path.cost, path.path[:3])

to_building = path_to_region(campus_map, (116, 3), "building_001")
print(to_building.goal, to_building.target_kind)

# 运行日常行为仿真
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

# 查看单个智能体
for student in model.students:
    print(
        student.unique_id,
        student.state.phase,
        student.state.current_activity,
        format_seconds_as_time(model.second_of_day),
    )
```

## 测试

运行全部测试：

```powershell
python -m pytest tests/ -v
```

或运行单个测试文件：

```powershell
python -m pytest tests/test_student_policy.py -v
python -m pytest tests/test_resource_queueing.py -v
python -m pytest tests/test_temporal_academic.py -v
python -m pytest tests/test_environment_dynamics.py -v
python -m pytest tests/test_physiopsychological.py -v
```

测试覆盖：

| 测试文件 | 覆盖内容 |
|---|---|
| `test_student_policy.py` | 策略动作打分与决策在不同时段和需求状态下的表现 |
| `test_resource_queueing.py` | 食堂排队等待时间计算、就餐时长、饱腹增长 |
| `test_temporal_academic.py` | 昼夜睡眠精力恢复、课表生成、缺课压力 |
| `test_environment_dynamics.py` | 空间交通、天气影响、社交邀请、关系层级 |
| `test_physiopsychological.py` | 健康衰减、压力平滑、专注力计算、精力/饱腹边界条件 |

## 地图标注工具

`map/` 目录包含基于浏览器的地形与区域标注工具。完整工作流程详见 [map/README.md](map/README.md)。
