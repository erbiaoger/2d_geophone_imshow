#!/usr/bin/env python3
"""Plot 2D geophone coordinates from SAC files.

用途:
    扫描一个包含 SAC 文件的目录。默认自动识别两种结构:
    1. 一个数字文件夹=一台检波器/台站，每个文件夹只取一个代表 SAC 文件，例如:
        数据/12/S12_Z_1.sac -> station=12
    2. 平铺 SAC 文件，台站编号在文件名前缀，例如:
        453010490.00000001.2024.08.14.06.55.20.000.z.sac -> station=453010490

常用运行方式:
    uv run --no-sync python scripts/plot_geophone_coordinates.py \
        --data-root "/Volumes/CSIM_LAB/DATA/chaoyang/数据"

生成地图叠加 HTML 的运行方式:
    如果 SAC 没有真实经纬度，需要提供阵列左下/起点的经纬度与检波器间距:
    uv run --no-sync python scripts/plot_geophone_coordinates.py \
        --data-root "/Volumes/CSIM_LAB/DATA/chaoyang/数据" \
        --origin-lat 40.0 --origin-lon 116.0 \
        --x-spacing-m 5 --y-spacing-m 5

主要输出:
    outputs/geophone_array_coordinates.csv  坐标明细表
    outputs/geophone_array.png              阵列坐标 PNG 图
    outputs/geophone_map.html               有经纬度时生成的 OpenStreetMap 叠加地图
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
from geophone_map.plotting import save_folium_map, save_points_csv, save_static_plot
from geophone_map.sac_coordinates import collect_sac_points, collect_station_points
from geophone_map.sac_coordinates import (
    collect_filename_station_points,
    find_default_gps_db,
    load_igu_gps_coordinates,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot 2D geophone SAC coordinates and optionally overlay them on OpenStreetMap.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("/Volumes/CSIM_LAB/DATA/chaoyang/数据"),
        help="SAC 数据根目录，默认是 /Volumes/CSIM_LAB/DATA/chaoyang/数据。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="输出目录，默认 outputs。",
    )
    parser.add_argument(
        "--coordinate-mode",
        choices=["array", "auto", "sac"],
        default="auto",
        help=(
            "坐标读取模式: array 只按目录/文件名推断阵列坐标；"
            "auto 优先读 SAC 经纬度再回退阵列坐标；sac 只使用 SAC 经纬度。默认 array。"
        ),
    )
    parser.add_argument(
        "--group-by",
        choices=["auto", "station-folder", "filename-prefix", "file"],
        default="auto",
        help=(
            "点位分组方式: auto 自动判断；station-folder 每个数字文件夹只画一个点；"
            "filename-prefix 按平铺文件名前缀分组；file 每个 SAC 文件都画一个点。默认 auto。"
        ),
    )
    parser.add_argument(
        "--gps-db",
        default="auto",
        help=(
            "SOLOLITE dccigugps.db 路径，用于给平铺台站文件补经纬度。"
            "默认 auto，会在数据目录上级自动查找；设为 none 可禁用。"
        ),
    )
    parser.add_argument(
        "--origin-lat",
        type=float,
        help="阵列原点纬度。SAC 无经纬度但需要地图叠加时必填。",
    )
    parser.add_argument(
        "--origin-lon",
        type=float,
        help="阵列原点经度。SAC 无经纬度但需要地图叠加时必填。",
    )
    parser.add_argument(
        "--x-spacing-m",
        type=float,
        default=1.0,
        help="列方向相邻检波器间距，单位 m，默认 1。",
    )
    parser.add_argument(
        "--y-spacing-m",
        type=float,
        default=1.0,
        help="行方向相邻检波器间距，单位 m，默认 1。",
    )
    parser.add_argument(
        "--x-bearing-deg",
        type=float,
        default=90.0,
        help="列方向方位角，单位度，0 为正北，90 为正东，默认 90。",
    )
    parser.add_argument(
        "--y-bearing-deg",
        type=float,
        default=0.0,
        help="行方向方位角，单位度，0 为正北，90 为正东，默认 0。",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    group_by = resolve_group_by(args.data_root, args.group_by)
    gps_coordinates = {}
    gps_db = resolve_gps_db(args.data_root, args.gps_db)
    if gps_db is not None:
        gps_coordinates = load_igu_gps_coordinates(gps_db)

    if group_by == "station-folder":
        points = collect_station_points(args.data_root, coordinate_mode=args.coordinate_mode)
    elif group_by == "filename-prefix":
        points = collect_filename_station_points(
            args.data_root,
            coordinate_mode=args.coordinate_mode,
            gps_coordinates=gps_coordinates,
        )
    else:
        points = collect_sac_points(args.data_root, coordinate_mode=args.coordinate_mode)
    if not points:
        raise SystemExit(f"No usable SAC coordinates found under {args.data_root}")

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

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "geophone_array_coordinates.csv"
    png_path = args.output_dir / "geophone_array.png"
    html_path = args.output_dir / "geophone_map.html"

    save_points_csv(points, csv_path)
    title = "Geophone Station Coordinates" if group_by != "file" else "2D Geophone Array Coordinates"
    save_static_plot(points, png_path, title=title)
    mapped_count = save_folium_map(points, html_path)

    print(f"Collected points: {len(points)}")
    print(f"CSV: {csv_path}")
    print(f"PNG: {png_path}")
    if mapped_count:
        print(f"HTML map: {html_path} ({mapped_count} points)")
    else:
        print("HTML map: skipped because no real/projected longitude-latitude coordinates are available")
    if gps_db is not None:
        print(f"GPS DB: {gps_db}")


def resolve_group_by(data_root: Path, group_by: str) -> str:
    if group_by != "auto":
        return group_by
    has_station_dirs = any(path.is_dir() and path.name.isdigit() for path in data_root.iterdir())
    if has_station_dirs:
        return "station-folder"
    return "filename-prefix"


def resolve_gps_db(data_root: Path, gps_db: str) -> Path | None:
    if gps_db.lower() in {"none", "no", "false", "0"}:
        return None
    if gps_db != "auto":
        path = Path(gps_db)
        return path if path.exists() else None
    return find_default_gps_db(data_root)


if __name__ == "__main__":
    main()
