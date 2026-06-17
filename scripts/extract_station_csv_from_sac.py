#!/usr/bin/env python3
"""Extract station coordinates from SAC files into a standard CSV.

用途:
    第一步脚本。扫描 SAC 数据目录，提取每个台站的编号、经纬度、海拔、平面索引等信息，
    生成后续绘图可直接复用的标准 CSV。

支持的 SAC 组织方式:
    1. 一个数字文件夹 = 一台站，每个文件夹取一个代表 SAC 文件
    2. 平铺 SAC 文件，台站编号在文件名前缀

常用运行方式:
    uv run --no-sync python scripts/extract_station_csv_from_sac.py \
      --data-root "/Volumes/CSIM_LAB/DATA/chaoyang/数据" \
      --output-csv outputs/stations.csv

平铺台站 + GPS 数据库:
    uv run --no-sync python scripts/extract_station_csv_from_sac.py \
      --data-root "/Volumes/CSIM_LAB/DATA/长白山数据/长白山第二次采集数据(20240822~20250622)/SAC格式/z_component" \
      --output-csv outputs/changbaishan_second/stations.csv

如果 SAC 没有真实经纬度，但你知道阵列原点与间距，也可以在导出 CSV 前完成投影:
    uv run --no-sync python scripts/extract_station_csv_from_sac.py \
      --data-root "/path/to/sac_root" \
      --output-csv outputs/stations.csv \
      --origin-lat 40.0 --origin-lon 116.0 \
      --x-spacing-m 5 --y-spacing-m 5

输出:
    一个标准 CSV，包含:
      file_name, path, row, column, x, y, latitude, longitude, elevation_m, coordinate_source
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from geophone_map.workflows import collect_points_from_sac_source
from geophone_map.plotting import save_points_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract station coordinate CSV from SAC files.")
    parser.add_argument("--data-root", type=Path, required=True, help="SAC 数据根目录。")
    parser.add_argument("--output-csv", type=Path, required=True, help="输出 CSV 路径。")
    parser.add_argument(
        "--coordinate-mode",
        choices=["array", "auto", "sac"],
        default="auto",
        help="坐标读取模式。默认 auto。",
    )
    parser.add_argument(
        "--group-by",
        choices=["auto", "station-folder", "filename-prefix", "file"],
        default="auto",
        help="点位分组方式。默认 auto。",
    )
    parser.add_argument(
        "--gps-db",
        default="auto",
        help="SOLOLITE dccigugps.db 路径。默认 auto 自动查找；设为 none 可禁用。",
    )
    parser.add_argument("--origin-lat", type=float, help="阵列原点纬度。")
    parser.add_argument("--origin-lon", type=float, help="阵列原点经度。")
    parser.add_argument("--x-spacing-m", type=float, default=1.0, help="列方向相邻检波器间距，单位 m。")
    parser.add_argument("--y-spacing-m", type=float, default=1.0, help="行方向相邻检波器间距，单位 m。")
    parser.add_argument("--x-bearing-deg", type=float, default=90.0, help="列方向方位角，单位度。")
    parser.add_argument("--y-bearing-deg", type=float, default=0.0, help="行方向方位角，单位度。")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        points, gps_db, group_by = collect_points_from_sac_source(
            args.data_root,
            coordinate_mode=args.coordinate_mode,
            group_by=args.group_by,
            gps_db=args.gps_db,
            origin_lat=args.origin_lat,
            origin_lon=args.origin_lon,
            x_spacing_m=args.x_spacing_m,
            y_spacing_m=args.y_spacing_m,
            x_bearing_deg=args.x_bearing_deg,
            y_bearing_deg=args.y_bearing_deg,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if not points:
        raise SystemExit(f"No usable station coordinates found under {args.data_root}")

    save_points_csv(points, args.output_csv)
    print(f"Collected points: {len(points)}")
    print(f"Group by: {group_by}")
    print(f"CSV: {args.output_csv}")
    if gps_db is not None:
        print(f"GPS DB: {gps_db}")


if __name__ == "__main__":
    main()
