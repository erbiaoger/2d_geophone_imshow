# scripts

本文件夹保存可直接运行的命令行脚本。

## plot_geophone_coordinates.py

作用:

- 扫描 SAC 数据目录。
- 或直接读取台站索引 CSV。
- 默认每个数字文件夹只取一个代表 SAC 文件，因此这批数据输出 60 个台站点。
- 可读取代表 SAC 头段的 `stla/stlo`。
- 对平铺 SAC 文件，可按文件名前缀识别台站，并自动读取邻近 `dccigugps.db` 里的 GPS 坐标。
- 如果经纬度为空，则使用文件夹编号作为台站索引坐标。
- 输出坐标 CSV、阵列 PNG；在有真实或投影经纬度时输出静态底图 PNG 和 HTML 地图。

运行:

```bash
uv run --no-sync python scripts/plot_geophone_coordinates.py \
  --data-root "/Volumes/CSIM_LAB/DATA/chaoyang/数据"
```

CSV 运行:

```bash
uv run --no-sync python scripts/plot_geophone_coordinates.py \
  --station-csv "/path/to/stations.csv" \
  --output-dir outputs/from_csv
```

## extract_station_csv_from_sac.py

作用:

- 第一步脚本。
- 扫描 SAC 目录并提取标准台站 CSV。
- 可自动识别数字文件夹模式和平铺文件名前缀模式。
- 可结合 `dccigugps.db` 补经纬度。

运行:

```bash
uv run --no-sync python scripts/extract_station_csv_from_sac.py \
  --data-root "/path/to/sac_root" \
  --output-csv outputs/stations.csv
```

## plot_station_maps_from_csv.py

作用:

- 第二步脚本。
- 读取标准台站 CSV，生成 PNG、静态底图 PNG、离线 HTML 和 live HTML。

运行:

```bash
uv run --no-sync python scripts/plot_station_maps_from_csv.py \
  --station-csv outputs/stations.csv \
  --output-dir outputs/from_csv
```

## interpolate_fiber_route.py

作用:

- 读取已有 DAS 坐标 CSV/TXT。
- 按输入顺序连接原始点，计算测线累计长度。
- 按固定间距输出整条光纤的插值经纬度点。
- 输出坐标 CSV、平面 PNG、HTML 地图和长度摘要。

运行:

```bash
uv run --no-sync python scripts/interpolate_fiber_route.py \
  --station-csv "/path/to/stations_or_changbai.txt" \
  --output-dir outputs/fiber_10m \
  --spacing-m 10 \
  --road-ref S509 \
  --target-length-m 10000 \
  --label-interval-m 100
```

说明:

- `--spacing-m` 控制实际输出 CSV 的插值点间距。
- HTML 里的 `Points` 下拉框可选择每隔 10/20/50/100/200/500/1000 m 显示一个样点。
- `--label-interval-m` 控制 PNG 和 HTML 里程标记间距，通常用 10 m 的倍数。
