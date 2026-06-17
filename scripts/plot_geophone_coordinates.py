#!/usr/bin/env python3
"""Plot 2D geophone coordinates from SAC files.

用途:
    扫描一个包含 SAC 文件的目录，或直接读取台站索引 CSV。SAC 模式默认自动识别两种结构:
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
    outputs/geophone_basemap.png            有经纬度时生成的静态地图底图 PNG
    outputs/geophone_map.html               有经纬度时生成的离线 HTML 地图
    outputs/geophone_map_live.html          有经纬度时生成的在线高精度缩放 HTML 地图

地图范围:
    可用 --basemap-margin-factor 和 --html-map-margin-factor 扩大显示范围。
    数值越大，台站周围预留的地图范围越大。
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
from geophone_map.plotting import save_basemap_plot, save_folium_map, save_points_csv, save_static_plot
from geophone_map.sac_coordinates import load_points_from_csv
from geophone_map.workflows import collect_points_from_sac_source


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
        "--station-csv",
        type=Path,
        help="台站索引 CSV 路径。提供后将直接从 CSV 读取点位，不再扫描 SAC 目录。",
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
        "--basemap-provider",
        default="Esri.WorldImagery",
        help=(
            "静态 PNG 底图瓦片源，默认 Esri.WorldImagery 卫星影像。"
            "也可用 Esri.WorldTopoMap、Esri.WorldPhysical、OpenTopoMap。"
        ),
    )
    parser.add_argument(
        "--basemap-margin-factor",
        type=float,
        default=0.18,
        help="静态底图范围扩展系数，默认 0.18。数值越大，显示范围越大。",
    )
    parser.add_argument(
        "--html-map-margin-factor",
        type=float,
        default=1.2,
        help="HTML 地图范围扩展系数，默认 1.2。数值越大，显示范围越大。",
    )
    parser.add_argument(
        "--html-basemap-zoom",
        type=int,
        default=14,
        help="HTML 离线底图瓦片缩放级别，默认 14。数值越小，覆盖范围越大、生成越快。",
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
    gps_db = None
    if args.station_csv is not None:
        points = load_points_from_csv(args.station_csv)
        group_by = "csv"
    else:
        points, gps_db, group_by = collect_points_from_sac_source(
            args.data_root,
            coordinate_mode=args.coordinate_mode,
            group_by=args.group_by,
            gps_db=args.gps_db,
        )
    if not points:
        source = args.station_csv if args.station_csv is not None else args.data_root
        raise SystemExit(f"No usable station coordinates found under {source}")

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
    basemap_path = args.output_dir / "geophone_basemap.png"
    html_path = args.output_dir / "geophone_map.html"
    live_html_path = args.output_dir / "geophone_map_live.html"

    save_points_csv(points, csv_path)
    title = "Geophone Station Coordinates" if group_by != "file" else "2D Geophone Array Coordinates"
    save_static_plot(points, png_path, title=title)
    basemap_count = save_basemap_plot(
        points,
        basemap_path,
        title=title,
        provider_name=args.basemap_provider,
        margin_factor=args.basemap_margin_factor,
    )
    mapped_count = save_folium_map(
        points,
        html_path,
        provider_name=args.basemap_provider,
        margin_factor=args.html_map_margin_factor,
        basemap_zoom=args.html_basemap_zoom,
        map_mode="embedded",
    )
    live_mapped_count = save_folium_map(
        points,
        live_html_path,
        provider_name=args.basemap_provider,
        margin_factor=args.html_map_margin_factor,
        basemap_zoom=args.html_basemap_zoom,
        map_mode="live",
    )

    print(f"Collected points: {len(points)}")
    print(f"CSV: {csv_path}")
    print(f"PNG: {png_path}")
    if basemap_count:
        print(f"Basemap PNG: {basemap_path} ({basemap_count} points)")
    else:
        print("Basemap PNG: skipped because no real/projected longitude-latitude coordinates are available")
    if mapped_count:
        print(f"HTML map: {html_path} ({mapped_count} points)")
        print(f"HTML live map: {live_html_path} ({live_mapped_count} points)")
    else:
        print("HTML map: skipped because no real/projected longitude-latitude coordinates are available")
    if gps_db is not None:
        print(f"GPS DB: {gps_db}")
if __name__ == "__main__":
    main()
