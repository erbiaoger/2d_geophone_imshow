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
