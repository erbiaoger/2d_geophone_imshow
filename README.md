# 2D Geophone Imshow

这个项目用于从 SAC 地震波形数据中提取检波器/台站坐标，并输出坐标表、阵列图和可选地图叠加 HTML。默认按“一个数字文件夹=一台检波器”处理，所以这批数据会输出 60 个点。

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
