from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import folium
import matplotlib.pyplot as plt

from geophone_map.sac_coordinates import GeophonePoint, valid_lonlat

EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True)
class FiberSample:
    index: int
    distance_m: float
    latitude: float
    longitude: float
    elevation_m: float | None
    segment_start: int
    segment_end: int


def interpolate_fiber_points(points: list[GeophonePoint], *, spacing_m: float = 10.0) -> tuple[list[FiberSample], float]:
    """Interpolate a DAS fiber line at fixed distance spacing along the input point order."""
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")

    lonlat_points = [point for point in points if valid_lonlat(point.latitude, point.longitude)]
    if len(lonlat_points) < 2:
        raise ValueError("At least two valid longitude-latitude points are required")

    lat0 = math.radians(sum(point.latitude for point in lonlat_points if point.latitude is not None) / len(lonlat_points))
    lon0 = math.radians(sum(point.longitude for point in lonlat_points if point.longitude is not None) / len(lonlat_points))
    local_xy = [
        _lonlat_to_local_xy(point.longitude, point.latitude, lat0=lat0, lon0=lon0)
        for point in lonlat_points
    ]

    cumulative = [0.0]
    for start, end in zip(local_xy, local_xy[1:]):
        cumulative.append(cumulative[-1] + math.dist(start, end))
    total_length_m = cumulative[-1]
    if total_length_m == 0:
        raise ValueError("Fiber line length is zero")

    target_distances = [i * spacing_m for i in range(int(total_length_m // spacing_m) + 1)]
    if not math.isclose(target_distances[-1], total_length_m):
        target_distances.append(total_length_m)

    samples = [
        _sample_at_distance(
            distance_m=distance_m,
            index=index,
            points=lonlat_points,
            local_xy=local_xy,
            cumulative=cumulative,
            lat0=lat0,
            lon0=lon0,
        )
        for index, distance_m in enumerate(target_distances)
    ]
    return samples, total_length_m


def save_fiber_samples_csv(samples: list[FiberSample], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "distance_m", "latitude", "longitude", "elevation_m", "segment_start", "segment_end"])
        for sample in samples:
            writer.writerow(
                [
                    sample.index,
                    f"{sample.distance_m:.3f}",
                    f"{sample.latitude:.9f}",
                    f"{sample.longitude:.9f}",
                    "" if sample.elevation_m is None else f"{sample.elevation_m:.3f}",
                    sample.segment_start,
                    sample.segment_end,
                ]
            )


def save_fiber_plan_png(
    original_points: list[GeophonePoint],
    samples: list[FiberSample],
    output_path: Path,
    *,
    title: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "Times New Roman"
    fig, ax = plt.subplots(figsize=(9, 8), dpi=180, constrained_layout=True)
    ax.plot(
        [sample.longitude for sample in samples],
        [sample.latitude for sample in samples],
        color="#1f2937",
        linewidth=1.3,
        label="Interpolated fiber",
    )
    ax.scatter(
        [sample.longitude for sample in samples],
        [sample.latitude for sample in samples],
        s=4,
        color="#38bdf8",
        alpha=0.65,
        label="10 m samples",
        rasterized=True,
    )
    originals = [point for point in original_points if valid_lonlat(point.latitude, point.longitude)]
    ax.scatter(
        [point.longitude for point in originals],
        [point.latitude for point in originals],
        s=24,
        marker="^",
        color="#ef4444",
        edgecolors="black",
        linewidths=0.35,
        label="Measured points",
        zorder=4,
    )
    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, alpha=0.25, linewidth=0.6)
    ax.legend(loc="best")
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def save_fiber_map_html(
    original_points: list[GeophonePoint],
    samples: list[FiberSample],
    output_path: Path,
    *,
    title: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    center_lat = sum(sample.latitude for sample in samples) / len(samples)
    center_lon = sum(sample.longitude for sample in samples) / len(samples)
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles (C) Esri",
        name="卫星",
        control=True,
    ).add_to(fmap)
    folium.TileLayer(
        tiles="https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
        attr="Map data (C) OpenStreetMap contributors, SRTM | OpenTopoMap",
        name="地形",
        control=True,
    ).add_to(fmap)
    folium.PolyLine(
        locations=[(sample.latitude, sample.longitude) for sample in samples],
        color="#00d4ff",
        weight=4,
        opacity=0.9,
        tooltip=title,
    ).add_to(fmap)
    sample_group = folium.FeatureGroup(name="10 m points", show=False)
    for sample in samples:
        folium.CircleMarker(
            location=(sample.latitude, sample.longitude),
            radius=2,
            color="#00d4ff",
            fill=True,
            fill_opacity=0.75,
            weight=0,
            popup=f"{sample.index}<br>{sample.distance_m:.1f} m",
        ).add_to(sample_group)
    sample_group.add_to(fmap)

    measured_group = folium.FeatureGroup(name="Measured points", show=True)
    for index, point in enumerate([point for point in original_points if valid_lonlat(point.latitude, point.longitude)], start=1):
        folium.RegularPolygonMarker(
            location=(point.latitude, point.longitude),
            number_of_sides=3,
            radius=8,
            color="black",
            fill=True,
            fill_color="#ef4444",
            fill_opacity=0.95,
            weight=1,
            popup=f"{index}<br>{point.file_name}<br>{point.elevation_m or 'N/A'} m",
        ).add_to(measured_group)
    measured_group.add_to(fmap)
    folium.LayerControl(position="topright", collapsed=False).add_to(fmap)
    fmap.fit_bounds([(sample.latitude, sample.longitude) for sample in samples], padding=(20, 20))
    fmap.save(output_path)


def _sample_at_distance(
    *,
    distance_m: float,
    index: int,
    points: list[GeophonePoint],
    local_xy: list[tuple[float, float]],
    cumulative: list[float],
    lat0: float,
    lon0: float,
) -> FiberSample:
    segment_start = max(0, min(len(cumulative) - 2, _segment_index(cumulative, distance_m)))
    segment_end = segment_start + 1
    start_distance = cumulative[segment_start]
    end_distance = cumulative[segment_end]
    ratio = 0.0 if end_distance == start_distance else (distance_m - start_distance) / (end_distance - start_distance)
    x0, y0 = local_xy[segment_start]
    x1, y1 = local_xy[segment_end]
    longitude, latitude = _local_xy_to_lonlat(x0 + (x1 - x0) * ratio, y0 + (y1 - y0) * ratio, lat0=lat0, lon0=lon0)
    elevation = _interpolate_elevation(points[segment_start].elevation_m, points[segment_end].elevation_m, ratio)
    return FiberSample(
        index=index,
        distance_m=distance_m,
        latitude=latitude,
        longitude=longitude,
        elevation_m=elevation,
        segment_start=segment_start,
        segment_end=segment_end,
    )


def _segment_index(cumulative: list[float], distance_m: float) -> int:
    for index in range(len(cumulative) - 1):
        if cumulative[index] <= distance_m <= cumulative[index + 1]:
            return index
    return len(cumulative) - 2


def _interpolate_elevation(start: float | None, end: float | None, ratio: float) -> float | None:
    if start is None or end is None:
        return None
    return start + (end - start) * ratio


def _lonlat_to_local_xy(longitude: float, latitude: float, *, lat0: float, lon0: float) -> tuple[float, float]:
    return (
        EARTH_RADIUS_M * (math.radians(longitude) - lon0) * math.cos(lat0),
        EARTH_RADIUS_M * (math.radians(latitude) - lat0),
    )


def _local_xy_to_lonlat(x: float, y: float, *, lat0: float, lon0: float) -> tuple[float, float]:
    return (
        math.degrees(lon0 + x / (EARTH_RADIUS_M * math.cos(lat0))),
        math.degrees(lat0 + y / EARTH_RADIUS_M),
    )
