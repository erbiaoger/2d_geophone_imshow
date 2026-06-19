#!/usr/bin/env python3
"""Interpolate a DAS fiber route into fixed-spacing longitude-latitude samples.

用途:
    读取已有 DAS 测点坐标 CSV/TXT，把这些点按文件中的顺序连接成测线，
    或按 OSM 道路矢量裁剪出测线，沿测线累计长度，并按固定间距插值输出整条光纤的坐标点。

适用场景:
    已有测点基本沿道路/光纤走向排列，需要补出约每 10 m 一个坐标点。
    如果提供 --road-ref，会从 Overpass 查询指定道路并沿道路插值。

常用运行方式:
    uv run --no-sync python scripts/interpolate_fiber_route.py \
      --station-csv "/Volumes/SanDisk2T4/data/dasQt-other/ChangBai/txt_0611_084816.txt" \
      --output-dir outputs/changbai_fiber_10m \
      --spacing-m 10 \
      --road-ref S509

输出:
    fiber_10m_coordinates.csv   每 10 m 插值坐标点，含累计距离和所在原始线段
    fiber_10m_plan.png          原始点、测线和 10 m 点的平面图
    fiber_10m_map.html          可交互 HTML 地图，含卫星/地形底图
    fiber_summary.txt           光纤总长度、点数和间距摘要
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from geophone_map.fiber_interpolation import (  # noqa: E402
    interpolate_fiber_along_route,
    interpolate_fiber_points,
    save_fiber_map_html,
    save_fiber_plan_png,
    save_fiber_samples_csv,
)
from geophone_map.sac_coordinates import load_points_from_csv  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interpolate a DAS fiber route at fixed spacing.")
    parser.add_argument("--station-csv", type=Path, required=True, help="输入坐标 CSV/TXT 路径。")
    parser.add_argument("--output-dir", type=Path, required=True, help="输出目录。")
    parser.add_argument("--spacing-m", type=float, default=10.0, help="插值点间距，单位 m，默认 10。")
    parser.add_argument("--road-ref", help="沿 OSM 道路编号插值，例如 S509。省略时按原始点折线插值。")
    parser.add_argument("--title", default="DAS Fiber 10 m Interpolation", help="输出图标题。")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    points = load_points_from_csv(args.station_csv)
    if args.road_ref:
        route = fetch_osm_road_route(points, args.road_ref)
        samples, total_length_m = interpolate_fiber_along_route(points, route, spacing_m=args.spacing_m)
        route_source = f"osm_ref={args.road_ref}"
    else:
        samples, total_length_m = interpolate_fiber_points(points, spacing_m=args.spacing_m)
        route_source = "input_points"

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "fiber_10m_coordinates.csv"
    png_path = args.output_dir / "fiber_10m_plan.png"
    html_path = args.output_dir / "fiber_10m_map.html"
    summary_path = args.output_dir / "fiber_summary.txt"

    save_fiber_samples_csv(samples, csv_path)
    save_fiber_plan_png(points, samples, png_path, title=args.title)
    save_fiber_map_html(points, samples, html_path, title=args.title)
    summary_path.write_text(
        "\n".join(
            [
                f"source={args.station_csv}",
                f"route_source={route_source}",
                "elevation_source=linear_interpolation_from_measured_points",
                f"spacing_m={args.spacing_m:.3f}",
                f"total_length_m={total_length_m:.3f}",
                f"total_length_km={total_length_m / 1000.0:.6f}",
                f"sample_count={len(samples)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Input points: {len(points)}")
    print(f"Route source: {route_source}")
    print(f"Fiber length: {total_length_m:.3f} m ({total_length_m / 1000.0:.6f} km)")
    print(f"Interpolated points: {len(samples)}")
    print(f"CSV: {csv_path}")
    print(f"PNG: {png_path}")
    print(f"HTML: {html_path}")
    print(f"Summary: {summary_path}")


def fetch_osm_road_route(points, road_ref: str) -> list[tuple[float, float]]:
    lonlat_points = [point for point in points if point.latitude is not None and point.longitude is not None]
    if len(lonlat_points) < 2:
        raise SystemExit("At least two valid points are required to query a road bbox")
    margin = 0.01
    south = min(point.latitude for point in lonlat_points) - margin
    north = max(point.latitude for point in lonlat_points) + margin
    west = min(point.longitude for point in lonlat_points) - margin
    east = max(point.longitude for point in lonlat_points) + margin
    query = f"""
[out:json][timeout:25];
(
  way["highway"]["ref"="{road_ref}"]({south},{west},{north},{east});
);
out body;
>;
out skel qt;
"""
    data = _overpass_query(query)
    nodes = {element["id"]: (element["lat"], element["lon"]) for element in data["elements"] if element["type"] == "node"}
    candidates = []
    for element in data["elements"]:
        if element["type"] != "way":
            continue
        tags = element.get("tags", {})
        if tags.get("ref") != road_ref:
            continue
        route = [nodes[node_id] for node_id in element["nodes"] if node_id in nodes]
        if len(route) >= 2:
            candidates.append(route)
    if not candidates:
        raise SystemExit(f"No OSM highway with ref={road_ref} found in the input coordinate bbox")
    return max(candidates, key=len)


def _overpass_query(query: str) -> dict:
    last_error = None
    for url in ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"):
        session = requests.Session()
        # ponytail: public HTTPS query; avoid broken SOCKS env vars instead of adding PySocks.
        session.trust_env = False
        try:
            response = session.post(url, data={"data": query}, timeout=35, headers={"User-Agent": "2d-geophone-imshow/0.1"})
            response.raise_for_status()
            return json.loads(response.text)
        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_error = exc
    raise SystemExit(f"Overpass query failed: {last_error}")


if __name__ == "__main__":
    main()
