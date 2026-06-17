#!/usr/bin/env python3
"""Render HTML maps and figures from a station coordinate CSV.

用途:
    第二步脚本。读取标准台站 CSV，生成平面分布 PNG、静态底图 PNG、
    离线 HTML 地图和 live HTML 地图。

标准输入 CSV:
    建议直接使用 scripts/extract_station_csv_from_sac.py 生成的 CSV。
    也兼容常见列名，如 station/row/x/y/lat/lon/elevation/path/file_name。

常用运行方式:
    uv run --no-sync python scripts/plot_station_maps_from_csv.py \
      --station-csv outputs/changbaishan_second/stations.csv \
      --output-dir outputs/changbaishan_second

如果 CSV 只有平面坐标，没有真实经纬度，可在出图前做投影:
    uv run --no-sync python scripts/plot_station_maps_from_csv.py \
      --station-csv outputs/stations.csv \
      --output-dir outputs/from_csv \
      --origin-lat 40.0 --origin-lon 116.0 \
      --x-spacing-m 5 --y-spacing-m 5

输出:
    geophone_array_coordinates.csv
    geophone_array.png
    geophone_basemap.png
    geophone_map.html
    geophone_map_live.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from geophone_map.georeference import project_array_points
from geophone_map.sac_coordinates import load_points_from_csv
from geophone_map.workflows import render_point_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render station maps and figures from a coordinate CSV.")
    parser.add_argument("--station-csv", type=Path, required=True, help="输入台站 CSV 路径。")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录。")
    parser.add_argument(
        "--basemap-provider",
        default="Esri.WorldImagery",
        help="底图瓦片源。默认 Esri.WorldImagery。",
    )
    parser.add_argument(
        "--basemap-margin-factor",
        type=float,
        default=0.18,
        help="静态底图范围扩展系数，默认 0.18。",
    )
    parser.add_argument(
        "--html-map-margin-factor",
        type=float,
        default=1.2,
        help="HTML 地图范围扩展系数，默认 1.2。",
    )
    parser.add_argument(
        "--html-basemap-zoom",
        type=int,
        default=14,
        help="HTML 离线底图瓦片缩放级别，默认 14。",
    )
    parser.add_argument("--title", default="Geophone Station Coordinates", help="图标题。")
    parser.add_argument("--origin-lat", type=float, help="阵列原点纬度。")
    parser.add_argument("--origin-lon", type=float, help="阵列原点经度。")
    parser.add_argument("--x-spacing-m", type=float, default=1.0, help="列方向相邻检波器间距，单位 m。")
    parser.add_argument("--y-spacing-m", type=float, default=1.0, help="行方向相邻检波器间距，单位 m。")
    parser.add_argument("--x-bearing-deg", type=float, default=90.0, help="列方向方位角，单位度。")
    parser.add_argument("--y-bearing-deg", type=float, default=0.0, help="行方向方位角，单位度。")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    points = load_points_from_csv(args.station_csv)
    if not points:
        raise SystemExit(f"No usable station coordinates found in {args.station_csv}")

    if args.origin_lat is not None or args.origin_lon is not None:
        if args.origin_lat is None or args.origin_lon is None:
            raise SystemExit("--origin-lat and --origin-lon must be provided together")
        points = project_array_points(
            points,
            origin_latitude=args.origin_lat,
            origin_longitude=args.origin_lon,
            x_spacing_m=args.x_spacing_m,
            y_spacing_m=args.y_spacing_m,
            x_bearing_deg=args.x_bearing_deg,
            y_bearing_deg=args.y_bearing_deg,
        )

    outputs = render_point_outputs(
        points,
        args.output_dir,
        title=args.title,
        basemap_provider=args.basemap_provider,
        basemap_margin_factor=args.basemap_margin_factor,
        html_map_margin_factor=args.html_map_margin_factor,
        html_basemap_zoom=args.html_basemap_zoom,
    )
    print(f"Collected points: {len(points)}")
    print(f"CSV: {outputs['csv_path']}")
    print(f"PNG: {outputs['png_path']}")
    if outputs["basemap_count"]:
        print(f"Basemap PNG: {outputs['basemap_path']} ({outputs['basemap_count']} points)")
    else:
        print("Basemap PNG: skipped because no real/projected longitude-latitude coordinates are available")
    if outputs["mapped_count"]:
        print(f"HTML map: {outputs['html_path']} ({outputs['mapped_count']} points)")
        print(f"HTML live map: {outputs['live_html_path']} ({outputs['live_mapped_count']} points)")
    else:
        print("HTML map: skipped because no real/projected longitude-latitude coordinates are available")


if __name__ == "__main__":
    main()
