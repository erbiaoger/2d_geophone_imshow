from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import folium
from branca.element import Element
from matplotlib import colors as mcolors
from matplotlib.ticker import FuncFormatter
import matplotlib.pyplot as plt

from geophone_map.plotting import (
    _expanded_mercator_extent,
    _fetch_xyz_basemap,
    _lonlat_to_web_mercator,
    _web_mercator_to_lonlat,
)
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


def extend_route_with_connected_routes(
    route_lonlat: list[tuple[float, float]],
    candidate_routes: list[list[tuple[float, float]]],
    *,
    max_links: int = 6,
) -> list[tuple[float, float]]:
    extended = list(route_lonlat)
    used: set[int] = set()
    for _ in range(max_links):
        end = extended[-1]
        match_index = None
        append_points: list[tuple[float, float]] = []
        for index, candidate in enumerate(candidate_routes):
            if index in used or len(candidate) < 2:
                continue
            if _same_lonlat(end, candidate[0]):
                match_index = index
                append_points = candidate[1:]
                break
            if _same_lonlat(end, candidate[-1]):
                match_index = index
                append_points = list(reversed(candidate[:-1]))
                break
        if match_index is None:
            break
        used.add(match_index)
        extended.extend(append_points)
    return extended


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


def interpolate_fiber_along_route(
    points: list[GeophonePoint],
    route_lonlat: list[tuple[float, float]],
    *,
    spacing_m: float = 10.0,
    target_length_m: float | None = None,
) -> tuple[list[FiberSample], float]:
    """Interpolate a DAS fiber line along a road/control route."""
    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    if target_length_m is not None and target_length_m <= 0:
        raise ValueError("target_length_m must be positive")
    lonlat_points = [point for point in points if valid_lonlat(point.latitude, point.longitude)]
    if len(lonlat_points) < 2:
        raise ValueError("At least two valid longitude-latitude points are required")
    if len(route_lonlat) < 2:
        raise ValueError("At least two route points are required")

    all_latitudes = [point.latitude for point in lonlat_points if point.latitude is not None] + [lat for lat, _ in route_lonlat]
    all_longitudes = [point.longitude for point in lonlat_points if point.longitude is not None] + [lon for _, lon in route_lonlat]
    lat0 = math.radians(sum(all_latitudes) / len(all_latitudes))
    lon0 = math.radians(sum(all_longitudes) / len(all_longitudes))
    route_xy = [_lonlat_to_local_xy(lon, lat, lat0=lat0, lon0=lon0) for lat, lon in route_lonlat]

    start_xy = _lonlat_to_local_xy(lonlat_points[0].longitude, lonlat_points[0].latitude, lat0=lat0, lon0=lon0)
    end_xy = _lonlat_to_local_xy(lonlat_points[-1].longitude, lonlat_points[-1].latitude, lat0=lat0, lon0=lon0)
    start_distance, start_projected = _project_xy_to_polyline(start_xy, route_xy)
    end_distance, end_projected = _project_xy_to_polyline(end_xy, route_xy)
    if target_length_m is not None:
        route_length_m = _polyline_cumulative(route_xy)[-1]
        direction = 1.0 if end_distance >= start_distance else -1.0
        target_end_distance = start_distance + direction * target_length_m
        if not 0.0 <= target_end_distance <= route_length_m:
            raise ValueError("target_length_m extends beyond the available route geometry")
        end_distance = target_end_distance
        end_projected = _point_at_polyline_distance(route_xy, end_distance)
    clipped_xy = _clip_route_xy(route_xy, start_distance, start_projected, end_distance, end_projected)
    cumulative = _polyline_cumulative(clipped_xy)
    total_length_m = cumulative[-1]
    if total_length_m == 0:
        raise ValueError("Fiber line length is zero")

    anchors = _route_elevation_anchors(lonlat_points, clipped_xy, lat0=lat0, lon0=lon0)
    target_distances = [i * spacing_m for i in range(int(total_length_m // spacing_m) + 1)]
    if not math.isclose(target_distances[-1], total_length_m):
        target_distances.append(total_length_m)

    samples = [
        _sample_route_at_distance(
            distance_m=distance_m,
            index=index,
            route_xy=clipped_xy,
            cumulative=cumulative,
            anchors=anchors,
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
    label_interval_m: float = 100.0,
    basemap_provider: str = "Esri.WorldTopoMap",
    basemap_zoom: int = 13,
) -> None:
    if label_interval_m <= 0:
        raise ValueError("label_interval_m must be positive")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "Times New Roman"
    fig, ax = plt.subplots(figsize=(9, 8), dpi=180, constrained_layout=True)
    elevation_min, elevation_max = _sample_elevation_range(samples)
    elevations = [_elevation_for_plot(sample.elevation_m, elevation_min) for sample in samples]
    sample_xy = [_lonlat_to_web_mercator(sample.longitude, sample.latitude) for sample in samples]
    xlim, ylim = _expanded_mercator_extent([x for x, _ in sample_xy], [y for _, y in sample_xy], margin_factor=0.08)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    basemap = _fetch_xyz_basemap(
        xlim,
        ylim,
        provider_name=basemap_provider,
        cache_dir=output_path.parent / ".tile_cache",
        zoom_override=basemap_zoom,
    )
    if basemap is not None:
        image, extent, attribution = basemap
        ax.imshow(image, extent=extent, origin="upper", zorder=0)
        ax.text(0.01, 0.01, attribution, transform=ax.transAxes, fontsize=5, color="black", alpha=0.75, zorder=7)
    ax.plot(
        [x for x, _ in sample_xy],
        [y for _, y in sample_xy],
        color="#1f2937",
        linewidth=1.3,
        label="Interpolated fiber",
        zorder=2,
    )
    scatter = ax.scatter(
        [x for x, _ in sample_xy],
        [y for _, y in sample_xy],
        s=7,
        c=elevations,
        cmap="jet" if elevation_min is not None else None,
        alpha=0.65,
        label="10 m samples",
        rasterized=True,
        zorder=3,
    )
    labels = [sample for sample in samples if _is_label_sample(sample, label_interval_m)]
    label_xy = [_lonlat_to_web_mercator(sample.longitude, sample.latitude) for sample in labels]
    ax.scatter(
        [x for x, _ in label_xy],
        [y for _, y in label_xy],
        s=18,
        c=[_elevation_for_plot(sample.elevation_m, elevation_min) for sample in labels],
        cmap="jet" if elevation_min is not None else None,
        edgecolors="#111827",
        linewidths=0.35,
        label=f"{label_interval_m:g} m labels",
        zorder=3,
    )
    originals = [point for point in original_points if valid_lonlat(point.latitude, point.longitude)]
    original_xy = [_lonlat_to_web_mercator(point.longitude, point.latitude) for point in originals]
    ax.scatter(
        [x for x, _ in original_xy],
        [y for _, y in original_xy],
        s=24,
        marker="^",
        c=[_elevation_for_plot(point.elevation_m, elevation_min) for point in originals],
        cmap="jet" if elevation_min is not None else None,
        edgecolors="black",
        linewidths=0.35,
        label="Measured points",
        zorder=4,
    )
    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{_web_mercator_to_lonlat(value, 0.0)[0]:.4f}°"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{_web_mercator_to_lonlat(0.0, value)[1]:.4f}°"))
    ax.grid(True, color="white", alpha=0.45, linewidth=0.5)
    ax.legend(loc="best")
    if elevation_min is not None:
        colorbar = fig.colorbar(scatter, ax=ax, pad=0.02)
        colorbar.set_label("Elevation (m)")
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def save_fiber_map_html(
    original_points: list[GeophonePoint],
    samples: list[FiberSample],
    output_path: Path,
    *,
    title: str,
    label_interval_m: float = 100.0,
) -> None:
    if label_interval_m <= 0:
        raise ValueError("label_interval_m must be positive")
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
    elevation_min, elevation_max = _sample_elevation_range(samples)
    sample_group = folium.FeatureGroup(name="Sample points", show=True)
    sample_marker_refs: list[tuple[str, float]] = []
    for sample in samples:
        elevation_text = _elevation_text(sample.elevation_m)
        color = _elevation_color_hex(sample.elevation_m, elevation_min, elevation_max)
        marker = folium.CircleMarker(
            location=(sample.latitude, sample.longitude),
            radius=3,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            weight=0,
            popup=f"{sample.index}<br>distance={sample.distance_m:.1f} m<br>elevation={elevation_text}",
        )
        marker.add_to(sample_group)
        sample_marker_refs.append((marker.get_name(), sample.distance_m))
    sample_group.add_to(fmap)
    interval_style, interval_script = _sample_interval_control_assets(fmap, sample_group.get_name(), sample_marker_refs)
    fmap.get_root().html.add_child(Element(interval_style))

    kilometer_group = folium.FeatureGroup(name=f"{label_interval_m:g} m labels", show=True)
    for sample in samples:
        if not _is_label_sample(sample, label_interval_m):
            continue
        color = _elevation_color_hex(sample.elevation_m, elevation_min, elevation_max)
        folium.CircleMarker(
            location=(sample.latitude, sample.longitude),
            radius=5,
            color="#111827",
            fill=True,
            fill_color=color,
            fill_opacity=0.95,
            weight=1,
            popup=f"distance={sample.distance_m:.0f} m<br>elevation={_elevation_text(sample.elevation_m)}",
        ).add_to(kilometer_group)
        folium.Marker(
            location=(sample.latitude, sample.longitude),
            icon=folium.DivIcon(
                html=(
                    f"<div style=\"font-family:'Times New Roman'; font-size:11px; "
                    f"font-weight:bold; color:white; text-shadow:0 0 3px black; "
                    f"transform: translate(7px, -7px);\">{sample.distance_m / 1000:.1f} km</div>"
                )
            ),
        ).add_to(kilometer_group)
    kilometer_group.add_to(fmap)

    measured_group = folium.FeatureGroup(name="Measured points", show=True)
    for index, point in enumerate([point for point in original_points if valid_lonlat(point.latitude, point.longitude)], start=1):
        color = _elevation_color_hex(point.elevation_m, elevation_min, elevation_max)
        folium.RegularPolygonMarker(
            location=(point.latitude, point.longitude),
            number_of_sides=3,
            radius=8,
            color="black",
            fill=True,
            fill_color=color,
            fill_opacity=0.95,
            weight=1,
            popup=f"{index}<br>{point.file_name}<br>{point.elevation_m or 'N/A'} m",
        ).add_to(measured_group)
    measured_group.add_to(fmap)
    if elevation_min is not None and elevation_max is not None:
        _add_elevation_colorbar(fmap, elevation_min, elevation_max)
    folium.LayerControl(position="topright", collapsed=False).add_to(fmap)
    fmap.fit_bounds([(sample.latitude, sample.longitude) for sample in samples], padding=(20, 20))
    fmap.save(output_path)
    _append_script_to_saved_html(output_path, interval_script)


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


def _elevation_text(elevation_m: float | None) -> str:
    return "N/A" if elevation_m is None else f"{elevation_m:.1f} m"


def _is_label_sample(sample: FiberSample, label_interval_m: float) -> bool:
    nearest = round(sample.distance_m / label_interval_m) * label_interval_m
    return math.isclose(sample.distance_m, nearest, abs_tol=1e-6)


def _elevation_for_plot(elevation_m: float | None, fallback: float | None) -> float | str:
    if elevation_m is not None:
        return elevation_m
    return fallback if fallback is not None else "#00d4ff"


def _sample_elevation_range(samples: list[FiberSample]) -> tuple[float | None, float | None]:
    elevations = [sample.elevation_m for sample in samples if sample.elevation_m is not None]
    if not elevations:
        return None, None
    return min(elevations), max(elevations)


def _elevation_color_hex(elevation_m: float | None, elevation_min: float | None, elevation_max: float | None) -> str:
    if elevation_m is None or elevation_min is None or elevation_max is None:
        return "#00d4ff"
    if math.isclose(elevation_min, elevation_max):
        value = 0.5
    else:
        value = (elevation_m - elevation_min) / (elevation_max - elevation_min)
    return mcolors.to_hex(plt.get_cmap("jet")(max(0.0, min(1.0, value))))


def _add_elevation_colorbar(fmap: folium.Map, elevation_min: float, elevation_max: float) -> None:
    gradient = ", ".join(_elevation_color_hex(elevation_min + (elevation_max - elevation_min) * i / 10, elevation_min, elevation_max) for i in range(11))
    html = f"""
    <style>
      .fiber-elevation-legend {{
        position: absolute;
        left: 18px;
        bottom: 28px;
        z-index: 1000;
        width: 190px;
        padding: 8px 10px;
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid rgba(0, 0, 0, 0.25);
        border-radius: 4px;
        font-family: "Times New Roman", serif;
        color: #111827;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
      }}
      .fiber-elevation-legend-title {{
        font-size: 13px;
        font-weight: bold;
        margin-bottom: 5px;
      }}
      .fiber-elevation-legend-bar {{
        height: 12px;
        background: linear-gradient(to right, {gradient});
        border: 1px solid rgba(0, 0, 0, 0.35);
      }}
      .fiber-elevation-legend-scale {{
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        margin-top: 3px;
      }}
    </style>
    <div class="fiber-elevation-legend">
      <div class="fiber-elevation-legend-title">Elevation (m)</div>
      <div class="fiber-elevation-legend-bar"></div>
      <div class="fiber-elevation-legend-scale">
        <span>{elevation_min:.1f}</span>
        <span>{elevation_max:.1f}</span>
      </div>
    </div>
    """
    fmap.get_root().html.add_child(Element(html))


def _sample_interval_control_assets(fmap: folium.Map, sample_layer_name: str, sample_marker_refs: list[tuple[str, float]]) -> tuple[str, str]:
    intervals = [10, 20, 50, 100, 200, 500, 1000]
    markers = ",\n".join(
        f"        {{ marker: {marker_name}, distance: {distance_m:.3f} }}"
        for marker_name, distance_m in sample_marker_refs
    )
    script = f"""
    var fiberPointIntervalControl = L.control({{ position: "topright" }});
    fiberPointIntervalControl.onAdd = function () {{
      var div = L.DomUtil.create("div", "fiber-point-interval-control");
      div.innerHTML = '<div class="fiber-point-interval-title">Points</div>'
        + '<select id="fiber-point-interval-select">'
        + {json.dumps("".join(f'<option value="{interval}">{interval} m</option>' for interval in intervals))}
        + '</select>';
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      return div;
    }};
    fiberPointIntervalControl.addTo({fmap.get_name()});

    var fiberPointIntervalMarkers = [
{markers}
    ];
    function applyFiberPointInterval(intervalMeters) {{
      fiberPointIntervalMarkers.forEach(function (entry) {{
        var nearest = Math.round(entry.distance / intervalMeters) * intervalMeters;
        var shouldShow = Math.abs(entry.distance - nearest) < 0.001;
        var isShown = {sample_layer_name}.hasLayer(entry.marker);
        if (shouldShow && !isShown) {{
          entry.marker.addTo({sample_layer_name});
        }} else if (!shouldShow && isShown) {{
          {sample_layer_name}.removeLayer(entry.marker);
        }}
      }});
    }}
    document.getElementById("fiber-point-interval-select").addEventListener("change", function (event) {{
      applyFiberPointInterval(Number(event.target.value));
    }});
    applyFiberPointInterval(10);
    """
    style = """
    <style>
      .fiber-point-interval-control {
        padding: 7px 8px;
        background: rgba(255, 255, 255, 0.94);
        border: 1px solid rgba(0, 0, 0, 0.25);
        border-radius: 4px;
        font-family: "Times New Roman", serif;
        color: #111827;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
      }
      .fiber-point-interval-title {
        font-size: 12px;
        font-weight: bold;
        margin-bottom: 4px;
      }
      .fiber-point-interval-control select {
        width: 82px;
        font-family: "Times New Roman", serif;
        font-size: 12px;
      }
    </style>
    """
    return style, script


def _append_script_to_saved_html(output_path: Path, script: str) -> None:
    html = output_path.read_text(encoding="utf-8")
    closing = "</script>\n</html>"
    if closing not in html:
        raise ValueError("Could not find final script block in saved folium HTML")
    output_path.write_text(html.replace(closing, f"{script}\n{closing}", 1), encoding="utf-8")


def _same_lonlat(first: tuple[float, float], second: tuple[float, float]) -> bool:
    return abs(first[0] - second[0]) < 1e-9 and abs(first[1] - second[1]) < 1e-9


def _segment_index(cumulative: list[float], distance_m: float) -> int:
    for index in range(len(cumulative) - 1):
        if cumulative[index] <= distance_m <= cumulative[index + 1]:
            return index
    return len(cumulative) - 2


def _sample_route_at_distance(
    *,
    distance_m: float,
    index: int,
    route_xy: list[tuple[float, float]],
    cumulative: list[float],
    anchors: list[tuple[float, float]],
    lat0: float,
    lon0: float,
) -> FiberSample:
    segment_start = max(0, min(len(cumulative) - 2, _segment_index(cumulative, distance_m)))
    segment_end = segment_start + 1
    start_distance = cumulative[segment_start]
    end_distance = cumulative[segment_end]
    ratio = 0.0 if end_distance == start_distance else (distance_m - start_distance) / (end_distance - start_distance)
    x0, y0 = route_xy[segment_start]
    x1, y1 = route_xy[segment_end]
    longitude, latitude = _local_xy_to_lonlat(x0 + (x1 - x0) * ratio, y0 + (y1 - y0) * ratio, lat0=lat0, lon0=lon0)
    return FiberSample(
        index=index,
        distance_m=distance_m,
        latitude=latitude,
        longitude=longitude,
        elevation_m=_elevation_at_distance(distance_m, anchors),
        segment_start=segment_start,
        segment_end=segment_end,
    )


def _polyline_cumulative(points: list[tuple[float, float]]) -> list[float]:
    cumulative = [0.0]
    for start, end in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + math.dist(start, end))
    return cumulative


def _project_xy_to_polyline(point: tuple[float, float], polyline: list[tuple[float, float]]) -> tuple[float, tuple[float, float]]:
    cumulative = _polyline_cumulative(polyline)
    best_distance = 0.0
    best_xy = polyline[0]
    best_error = math.inf
    px, py = point
    for index, (start, end) in enumerate(zip(polyline, polyline[1:])):
        x0, y0 = start
        x1, y1 = end
        dx = x1 - x0
        dy = y1 - y0
        length2 = dx * dx + dy * dy
        ratio = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / length2))
        projected = (x0 + dx * ratio, y0 + dy * ratio)
        error = math.dist(point, projected)
        if error < best_error:
            best_error = error
            best_xy = projected
            best_distance = cumulative[index] + math.dist(start, projected)
    return best_distance, best_xy


def _point_at_polyline_distance(polyline: list[tuple[float, float]], distance_m: float) -> tuple[float, float]:
    cumulative = _polyline_cumulative(polyline)
    segment_start = max(0, min(len(cumulative) - 2, _segment_index(cumulative, distance_m)))
    start_distance = cumulative[segment_start]
    end_distance = cumulative[segment_start + 1]
    ratio = 0.0 if end_distance == start_distance else (distance_m - start_distance) / (end_distance - start_distance)
    x0, y0 = polyline[segment_start]
    x1, y1 = polyline[segment_start + 1]
    return (x0 + (x1 - x0) * ratio, y0 + (y1 - y0) * ratio)


def _clip_route_xy(
    route_xy: list[tuple[float, float]],
    start_distance: float,
    start_xy: tuple[float, float],
    end_distance: float,
    end_xy: tuple[float, float],
) -> list[tuple[float, float]]:
    if start_distance > end_distance:
        clipped = _clip_route_xy(route_xy, end_distance, end_xy, start_distance, start_xy)
        return list(reversed(clipped))

    cumulative = _polyline_cumulative(route_xy)
    clipped = [start_xy]
    for distance, point in zip(cumulative[1:-1], route_xy[1:-1]):
        if start_distance < distance < end_distance:
            clipped.append(point)
    clipped.append(end_xy)
    return _dedupe_adjacent_xy(clipped)


def _dedupe_adjacent_xy(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    deduped = [points[0]]
    for point in points[1:]:
        if math.dist(deduped[-1], point) > 1e-6:
            deduped.append(point)
    return deduped


def _route_elevation_anchors(
    points: list[GeophonePoint],
    route_xy: list[tuple[float, float]],
    *,
    lat0: float,
    lon0: float,
) -> list[tuple[float, float]]:
    anchors = []
    for point in points:
        if point.elevation_m is None:
            continue
        xy = _lonlat_to_local_xy(point.longitude, point.latitude, lat0=lat0, lon0=lon0)
        distance, _ = _project_xy_to_polyline(xy, route_xy)
        anchors.append((distance, point.elevation_m))
    return sorted(anchors)


def _elevation_at_distance(distance_m: float, anchors: list[tuple[float, float]]) -> float | None:
    if not anchors:
        return None
    if distance_m <= anchors[0][0]:
        return anchors[0][1]
    if distance_m >= anchors[-1][0]:
        return anchors[-1][1]
    for (d0, z0), (d1, z1) in zip(anchors, anchors[1:]):
        if d0 <= distance_m <= d1:
            ratio = 0.0 if d1 == d0 else (distance_m - d0) / (d1 - d0)
            return z0 + (z1 - z0) * ratio
    return anchors[-1][1]


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
