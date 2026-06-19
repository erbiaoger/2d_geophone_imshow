# 2D Geophone Imshow

![geophone_basemap](https://raw.githubusercontent.com/erbiaoger/PicGo/main/260407geophone_basemap.png)

这个项目用于从 SAC 地震波形数据中提取检波器/台站坐标，并输出坐标表、阵列图和可选地图叠加 HTML。默认按“一个数字文件夹=一台检波器”处理，所以这批数据会输出 60 个点。

![CleanShot 2026-06-18 at 14.20.09](https://raw.githubusercontent.com/erbiaoger/PicGo/main/260407CleanShot%202026-06-18%20at%2014.20.09.png)

推荐流程现在是两步:

1. 从 SAC 提取标准台站 CSV
2. 从这个 CSV 生成图片和 HTML 地图

## 文件夹

- `src/geophone_map/`: 核心 Python 模块，负责 SAC 头段读取、台站/阵列索引解析、坐标投影和绘图。
- `scripts/`: 可直接运行的 CLI 脚本。
- `tests/`: 核心解析和投影逻辑的自动测试。
- `docs/`: 方法说明文档。
- `outputs/`: 运行脚本后生成的 CSV、PNG 和 HTML 结果。

## 环境

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e . pytest psutil
```

## 直接绘制 60 台坐标

```bash
uv run --no-sync python scripts/plot_geophone_coordinates.py \
  --data-root "/Volumes/CSIM_LAB/DATA/chaoyang/数据"
```

输出:

- `outputs/geophone_array_coordinates.csv`
- `outputs/geophone_array.png`

## 两步流程

### 第一步: 从 SAC 提取标准台站 CSV

```bash
uv run --no-sync python scripts/extract_station_csv_from_sac.py \
  --data-root "/Volumes/CSIM_LAB/DATA/长白山数据/长白山第二次采集数据(20240822~20250622)/SAC格式/z_component" \
  --output-csv outputs/changbaishan_second/stations.csv
```

这一步会生成一个标准 CSV，包含:

- `file_name`
- `path`
- `row`
- `column`
- `x`
- `y`
- `latitude`
- `longitude`
- `elevation_m`
- `coordinate_source`

### 第二步: 从标准台站 CSV 绘图

```bash
uv run --no-sync python scripts/plot_station_maps_from_csv.py \
  --station-csv outputs/changbaishan_second/stations.csv \
  --output-dir outputs/changbaishan_second
```

输出:

- `outputs/changbaishan_second/geophone_array_coordinates.csv`
- `outputs/changbaishan_second/geophone_array.png`
- `outputs/changbaishan_second/geophone_basemap.png`
- `outputs/changbaishan_second/geophone_map.html`
- `outputs/changbaishan_second/geophone_map_live.html`

## 直接从台站索引 CSV 绘图

如果你已经有台站索引 CSV，或长白这种无表头 TXT 坐标表，可直接运行:

```bash
uv run --no-sync python scripts/plot_geophone_coordinates.py \
  --station-csv "/path/to/stations.csv" \
  --output-dir outputs/from_csv
```

常见可识别列名包括:

- 台站编号: `station`, `station_id`, `row`, `index`, `id`
- 阵列坐标: `x`, `y`, `column`, `row`
- 经纬度: `lat`, `latitude`, `lon`, `longitude`
- 海拔: `elevation`, `elev`, `elevation_m`
- 文件信息: `path`, `file_name`, `name`

长白无表头 TXT 兼容列顺序为:

- `name, utm_northing, utm_easting, elevation_m, latitude, longitude, elevation_m_copy`

如果 CSV 里有 `lat/lon`，会直接生成地图底图和 HTML；如果只有 `x/y` 或 `row/column`，则先画平面分布图，也可以再配合 `--origin-lat/--origin-lon` 做投影。

## 叠加地图

当前 SAC 文件里的 `stla/stlo` 多数为空值，不能直接叠加真实地图。如果知道阵列原点经纬度和检波器间距，可以这样生成 OpenStreetMap HTML:

```bash
uv run --no-sync python scripts/plot_geophone_coordinates.py \
  --data-root "/Volumes/CSIM_LAB/DATA/chaoyang/数据" \
  --origin-lat 40.0 \
  --origin-lon 116.0 \
  --x-spacing-m 5 \
  --y-spacing-m 5
```

这会额外输出:

- `outputs/geophone_map.html`
- `outputs/geophone_map_live.html`

## 长白山第二次平铺 SAC 数据

对于 `z_component` 这种平铺文件结构，脚本会自动按文件名前缀识别台站，并自动查找同一采集目录里的 `dccigugps.db`:

```bash
uv run --no-sync python scripts/plot_geophone_coordinates.py \
  --data-root "/Volumes/CSIM_LAB/DATA/长白山数据/长白山第二次采集数据(20240822~20250622)/SAC格式/z_component" \
  --output-dir outputs/changbaishan_second
```

输出:

- `outputs/changbaishan_second/geophone_array_coordinates.csv`
- `outputs/changbaishan_second/geophone_array.png`
- `outputs/changbaishan_second/geophone_basemap.png`: 默认卫星底图，点颜色代表海拔高度。
- `outputs/changbaishan_second/geophone_map.html`
- `outputs/changbaishan_second/geophone_map_live.html`

其中:

- `geophone_map.html`: 离线版，双击即可打开，但底图放大后会逐渐变糊。
- `geophone_map_live.html`: 在线瓦片版，需要通过 `localhost` 打开，缩放时会继续请求更高分辨率底图。

可用本地服务脚本打开在线高精度缩放版:

```bash
uv run --no-sync python scripts/serve_map.py \
  --directory outputs/changbaishan_second
```

如果想换底图风格，可以加 `--basemap-provider`:

```bash
uv run --no-sync python scripts/plot_geophone_coordinates.py \
  --data-root "/Volumes/CSIM_LAB/DATA/长白山数据/长白山第二次采集数据(20240822~20250622)/SAC格式/z_component" \
  --output-dir outputs/changbaishan_second \
  --basemap-provider Esri.WorldImagery
```

可选值包括 `Esri.WorldImagery`, `Esri.WorldTopoMap`, `Esri.WorldPhysical`, `OpenTopoMap`。

## DAS 测线 10 m 插值

如果已有坐标点沿光纤/道路顺序排列，可沿道路插值出约每 10 m 一个坐标点，并可继续延伸到指定总长度:

```bash
uv run --no-sync python scripts/interpolate_fiber_route.py \
  --station-csv "/Volumes/SanDisk2T4/data/dasQt-other/ChangBai/txt_0611_084816.txt" \
  --output-dir outputs/changbai_fiber_s509_10km_10m \
  --spacing-m 10 \
  --road-ref S509 \
  --target-length-m 10000
```

输出:

- `fiber_10m_coordinates.csv`: 每 10 m 点的经纬度、累计距离和所在原始线段。
- `fiber_10m_plan.png`: 原始点、插值测线和 10 m 点平面图。
- `fiber_10m_map.html`: 可交互 HTML 地图，显示 10 m 点，并每 100 m 标一个里程点。
- `fiber_summary.txt`: 光纤总长度和点数摘要。

高程说明: 实测范围内按原始测点高程沿道路累计距离线性插值；超过最后一个实测点的延伸段保持最后一个实测高程。
