#!/usr/bin/env python3
"""Interpolate a DAS fiber route into fixed-spacing longitude-latitude samples.

用途:
    读取已有 DAS 测点坐标 CSV/TXT，把这些点按文件中的顺序连接成测线，
    沿测线累计长度，并按固定间距插值输出整条光纤的坐标点。

适用场景:
    已有测点基本沿道路/光纤走向排列，需要补出约每 10 m 一个坐标点。
    本脚本不自动识别卫星图中的道路，只沿输入坐标折线插值。

常用运行方式:
    uv run --no-sync python scripts/interpolate_fiber_route.py \
      --station-csv "/Volumes/SanDisk2T4/data/dasQt-other/ChangBai/txt_0611_084816.txt" \
      --output-dir outputs/changbai_fiber_10m \
      --spacing-m 10

输出:
    fiber_10m_coordinates.csv   每 10 m 插值坐标点，含累计距离和所在原始线段
    fiber_10m_plan.png          原始点、测线和 10 m 点的平面图
    fiber_10m_map.html          可交互 HTML 地图，含卫星/地形底图
    fiber_summary.txt           光纤总长度、点数和间距摘要
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from geophone_map.fiber_interpolation import (  # noqa: E402
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
    parser.add_argument("--title", default="DAS Fiber 10 m Interpolation", help="输出图标题。")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    points = load_points_from_csv(args.station_csv)
    samples, total_length_m = interpolate_fiber_points(points, spacing_m=args.spacing_m)

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
    print(f"Fiber length: {total_length_m:.3f} m ({total_length_m / 1000.0:.6f} km)")
    print(f"Interpolated points: {len(samples)}")
    print(f"CSV: {csv_path}")
    print(f"PNG: {png_path}")
    print(f"HTML: {html_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
