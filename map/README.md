# SiameseBH 校园标注工具

这个目录包含一套本地校园地图标注流程，用于从 `BHmap.png` 生成 terrain 标注、region 信息，以及与原始图片解耦的汇总数据和独立展示页面。

## 文件说明

- `BHmap.png`：原始校园示意图。
- `index.html`：terrain 网格标注页面。
- `annotations.json`：terrain 标注结果。
- `terrain_mask.png`：terrain 彩色遮罩图。
- `region.html`：region 信息标注页面。
- `regions.json`：region 标注结果。
- `build_summary.py`：把 `annotations.json` 和 `regions.json` 合并为相对坐标汇总文件。
- `summary.json`：与原始 `BHmap.png` 解耦的汇总数据。
- `render_summary_html.py`：把 `summary.json` 渲染为独立 HTML。
- `summary_view.html`：不依赖 `BHmap.png` 的标注数据展示页面。

## 启动本地服务

建议通过本地 HTTP 服务打开页面，避免浏览器本地文件限制：

```powershell
cd C:\Users\32434\Desktop\SiameseBH
python -m http.server 8788 --bind 127.0.0.1 --directory .
```

然后打开：

- terrain 标注页：http://127.0.0.1:8788/index.html
- region 标注页：http://127.0.0.1:8788/region.html
- 汇总展示页：http://127.0.0.1:8788/summary_view.html

## Terrain 标注

打开 `index.html` 后，可以在 25px 网格上标注 terrain。

当前 terrain 类型：

- `road`
- `building`
- `grass`
- `water`
- `sports_field`
- `open_ground`
- `gate`
- `fence`

操作：

- 鼠标左键拖动：按当前 brush size 标注空白格。
- 已有标注格不会被其他类别覆盖，必须先擦除。
- `Erase terrain` / `Erase cell`：擦除已有标注。
- 鼠标滚轮：缩放。
- 按住 `Space` 或鼠标右键拖动：平移。
- `Export JSON`：导出 `annotations.json`。
- `Export Terrain PNG`：导出 `terrain_mask.png`。

`annotations.json` 只保存已标注格子，不保存全图空白格。

## Region 标注

打开 `region.html` 后，页面会读取 `annotations.json`，自动从 terrain 中生成 region。

生成规则：

- 只从 `building`、`sports_field`、`gate` 生成 region。
- 使用 4 邻接，即上下左右相连才算同一连通区域。
- `area` 等于 region 覆盖的网格数量，也就是 `cellCount`。

每个 region 可填写：

- `name`
- `function`
- `available`
- `open_time`
- `close_time`
- `entrances`

默认时间：

- `open_time = 00:00`
- `close_time = 23:59`

入口标注：

- 点击 `Entrance Mode` 进入入口标注模式。
- 只能点击当前 region 内部格子作为入口。
- 再次点击同一入口格可以取消。

导出：

- 点击 `Export Regions JSON` 导出 `regions.json`。

## 生成解耦汇总文件

`summary.json` 不依赖原始图片，不保存 `BHmap.png`、`imageName`、`imageSize` 等原图字段。

生成命令：

```powershell
python .\build_summary.py .\annotations.json .\regions.json .\summary.json
```

坐标规则：

- 所有 `row` / `col` 都是相对网格坐标。
- 相对原点为所有 terrain 标注格子的最小外接框左上角。
- 原始偏移保存在：

```json
"origin": {
  "rowMin": 84,
  "colMin": 49
}
```

主要字段：

- `gridSize`
- `origin`
- `size`
- `terrainLabels`
- `terrainPalette`
- `terrainCells`
- `regions`

## 生成独立展示页面

生成命令：

```powershell
python .\render_summary_html.py .\summary.json .\summary_view.html
```

`summary_view.html` 会把 `summary.json` 数据内嵌到 HTML 中，因此打开时不需要 `BHmap.png`，也不需要额外加载 JSON。

展示能力：

- Canvas 绘制所有 terrain。
- 高亮 region。
- 显示入口点。
- 支持 terrain 筛选。
- 支持 region 筛选。
- 支持在线修改 terrain 配色。
- 点击 region 查看详情。
- 鼠标滚轮缩放。
- 按住 `Space` 或右键拖动平移。

### 修改并保存展示配色

在 `summary_view.html` 左侧 `Palette` 区域可以直接修改各类 terrain 的颜色。颜色修改会立即应用到 Canvas。

保存默认配色时需要同时保存两个文件：

- 点击 `Save JSON`：保存更新后的 `summary.json`。
- 点击 `Save HTML`：保存更新后的 `summary_view.html`。

浏览器如果支持文件保存对话框，会提示选择保存位置；否则会下载同名文件。建议覆盖当前目录下的 `summary.json` 和 `summary_view.html`。

## 推荐完整流程

1. 打开 `index.html` 标注 terrain。
2. 导出 `annotations.json` 和 `terrain_mask.png`。
3. 打开 `region.html` 自动生成 region。
4. 填写 region 信息和入口。
5. 导出 `regions.json`。
6. 运行：

```powershell
python .\build_summary.py .\annotations.json .\regions.json .\summary.json
python .\render_summary_html.py .\summary.json .\summary_view.html
```

7. 打开 `summary_view.html` 检查最终结果。
