from __future__ import annotations

import math
from pathlib import Path

import folium
import matplotlib.pyplot as plt
import pandas as pd
import requests
from PIL import Image
from matplotlib.ticker import ScalarFormatter
from matplotlib.ticker import FuncFormatter

from geophone_map.sac_coordinates import GeophonePoint, valid_lonlat


def points_to_dataframe(points: list[GeophonePoint]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "file_name": point.file_name,
                "path": str(point.path),
                "row": point.row,
                "column": point.column,
                "x": point.x,
                "y": point.y,
                "latitude": point.latitude,
                "longitude": point.longitude,
                "elevation_m": point.elevation_m,
                "coordinate_source": point.coordinate_source,
            }
            for point in points
        ]
    )


def save_points_csv(points: list[GeophonePoint], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    points_to_dataframe(points).to_csv(output_path, index=False)


def save_static_plot(points: list[GeophonePoint], output_path: Path, *, title: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "Times New Roman"
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150, constrained_layout=True)
    df = points_to_dataframe(points)
    if df.empty:
        raise ValueError("No points are available for plotting")

    station_plot = df["column"].isna().all()
    lonlat_plot = df["latitude"].notna().any() and df["longitude"].notna().any()
    if lonlat_plot:
        xlabel = "Longitude"
        ylabel = "Latitude"
    elif station_plot:
        xlabel = "Station index"
        ylabel = "Relative Y"
    else:
        xlabel = "Column index / Longitude"
        ylabel = "Line index / Latitude"
    has_elevation = df["elevation_m"].notna().any()
    colorbar_label = "Elevation (m)" if has_elevation else ("Station ID" if station_plot else "Line index")

    color_values = df["elevation_m"] if has_elevation else df["row"].fillna(0)
    annotate_station_labels = False
    if not has_elevation and station_plot and color_values.max() > 100_000:
        color_values = pd.Series(range(1, len(df) + 1), index=df.index)
        colorbar_label = "Station order"
        annotate_station_labels = True

    scatter = ax.scatter(
        df["x"],
        df["y"],
        c=color_values,
        s=12,
        cmap="terrain" if has_elevation else "viridis",
        alpha=0.85,
        edgecolors="none",
        rasterized=True,
    )
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if lonlat_plot:
        for axis in (ax.xaxis, ax.yaxis):
            formatter = ScalarFormatter(useOffset=False)
            formatter.set_scientific(False)
            axis.set_major_formatter(formatter)
    _expand_degenerate_axis(ax, df["x"].min(), df["x"].max(), axis="x")
    _expand_degenerate_axis(ax, df["y"].min(), df["y"].max(), axis="y")
    if df["x"].nunique() > 1 and df["y"].nunique() > 1 and not lonlat_plot:
        ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.25, linewidth=0.6)
    if annotate_station_labels:
        for _, row in df.iterrows():
            label = str(int(row["row"]))[-4:] if pd.notna(row["row"]) else row["file_name"][:4]
            ax.annotate(
                label,
                (row["x"], row["y"]),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=6,
                alpha=0.75,
            )
    fig.colorbar(scatter, ax=ax, label=colorbar_label)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def save_folium_map(points: list[GeophonePoint], output_path: Path) -> int:
    lonlat_points = [
        point
        for point in points
        if valid_lonlat(point.latitude, point.longitude)
    ]
    if not lonlat_points:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    center_lat = sum(point.latitude for point in lonlat_points if point.latitude is not None) / len(lonlat_points)
    center_lon = sum(point.longitude for point in lonlat_points if point.longitude is not None) / len(lonlat_points)

    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=16, tiles="OpenStreetMap")
    folium.FeatureGroup(name="Geophones", show=True).add_to(fmap)

    for point in lonlat_points:
        popup = (
            f"{point.file_name}<br>"
            f"row={point.row}, column={point.column}<br>"
            f"source={point.coordinate_source}"
        )
        folium.CircleMarker(
            location=[point.latitude, point.longitude],
            radius=2,
            color="#2563eb",
            fill=True,
            fill_color="#ef4444",
            fill_opacity=0.8,
            weight=1,
            popup=popup,
        ).add_to(fmap)

    folium.LayerControl().add_to(fmap)
    fmap.save(output_path)
    return len(lonlat_points)


def save_basemap_plot(
    points: list[GeophonePoint],
    output_path: Path,
    *,
    title: str,
    provider_name: str = "Esri.WorldImagery",
) -> int:
    lonlat_points = [
        point
        for point in points
        if valid_lonlat(point.latitude, point.longitude)
    ]
    if not lonlat_points:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "Times New Roman"
    fig, ax = plt.subplots(figsize=(9, 8), dpi=180, constrained_layout=True)
    rows = []
    for index, point in enumerate(lonlat_points, start=1):
        x, y = _lonlat_to_web_mercator(point.longitude, point.latitude)
        rows.append(
            {
                "x": x,
                "y": y,
                "station_id": point.row,
                "label": str(int(point.row))[-4:] if point.row is not None else str(index),
                "order": index,
                "elevation_m": point.elevation_m,
            }
        )
    df = pd.DataFrame(rows)

    x_margin = max((df["x"].max() - df["x"].min()) * 0.18, 120.0)
    y_margin = max((df["y"].max() - df["y"].min()) * 0.18, 120.0)
    ax.set_xlim(df["x"].min() - x_margin, df["x"].max() + x_margin)
    ax.set_ylim(df["y"].min() - y_margin, df["y"].max() + y_margin)

    basemap = _fetch_xyz_basemap(
        ax.get_xlim(),
        ax.get_ylim(),
        provider_name=provider_name,
        cache_dir=output_path.parent / ".tile_cache",
    )
    if basemap is not None:
        image, extent, attribution = basemap
        ax.imshow(image, extent=extent, origin="upper", zorder=0)
        ax.text(
            0.01,
            0.01,
            attribution,
            transform=ax.transAxes,
            fontsize=5,
            color="black",
            alpha=0.75,
            zorder=7,
        )
    has_elevation = df["elevation_m"].notna().any()
    color_values = df["elevation_m"] if has_elevation else df["order"]
    colorbar_label = "Elevation (m)" if has_elevation else "Station order"
    scatter = ax.scatter(
        df["x"],
        df["y"],
        c=color_values,
        s=34,
        cmap="terrain" if has_elevation else "autumn",
        edgecolors="black",
        linewidths=0.55,
        zorder=5,
    )
    for _, row in df.iterrows():
        ax.annotate(
            row["label"],
            (row["x"], row["y"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=6,
            color="black",
            zorder=6,
        )

    ax.set_title(title)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{_web_mercator_to_lonlat(value, 0.0)[0]:.4f}°"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{_web_mercator_to_lonlat(0.0, value)[1]:.4f}°"))
    ax.grid(True, color="white", alpha=0.5, linewidth=0.5)
    fig.colorbar(scatter, ax=ax, shrink=0.72, label=colorbar_label)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return len(lonlat_points)


def _expand_degenerate_axis(ax, lower: float, upper: float, *, axis: str) -> None:
    if lower != upper:
        return
    margin = 1.0 if lower == 0 else abs(lower) * 0.05
    setter = ax.set_xlim if axis == "x" else ax.set_ylim
    setter(lower - margin, upper + margin)


def _lonlat_to_web_mercator(longitude: float, latitude: float) -> tuple[float, float]:
    radius = 6_378_137.0
    clipped_latitude = max(min(latitude, 85.05112878), -85.05112878)
    x = radius * math.radians(longitude)
    y = radius * math.log(math.tan(math.pi / 4.0 + math.radians(clipped_latitude) / 2.0))
    return x, y


def _web_mercator_to_lonlat(x: float, y: float) -> tuple[float, float]:
    radius = 6_378_137.0
    longitude = math.degrees(x / radius)
    latitude = math.degrees(2.0 * math.atan(math.exp(y / radius)) - math.pi / 2.0)
    return longitude, latitude


def _web_mercator_to_tile(x: float, y: float, zoom: int) -> tuple[int, int]:
    longitude, latitude = _web_mercator_to_lonlat(x, y)
    latitude_rad = math.radians(max(min(latitude, 85.05112878), -85.05112878))
    scale = 2**zoom
    tile_x = int((longitude + 180.0) / 360.0 * scale)
    tile_y = int((1.0 - math.asinh(math.tan(latitude_rad)) / math.pi) / 2.0 * scale)
    tile_x = max(0, min(scale - 1, tile_x))
    tile_y = max(0, min(scale - 1, tile_y))
    return tile_x, tile_y


def _tile_bounds_web_mercator(tile_x: int, tile_y: int, zoom: int) -> tuple[float, float, float, float]:
    scale = 2**zoom
    west = tile_x / scale * 360.0 - 180.0
    east = (tile_x + 1) / scale * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * tile_y / scale))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (tile_y + 1) / scale))))
    west_x, south_y = _lonlat_to_web_mercator(west, south)
    east_x, north_y = _lonlat_to_web_mercator(east, north)
    return west_x, east_x, south_y, north_y


def _fetch_xyz_basemap(
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    *,
    provider_name: str,
    cache_dir: Path,
):
    provider = _xyz_provider(provider_name)
    zoom = provider["zoom"]
    min_x, max_x = xlim
    min_y, max_y = ylim
    west_tile, south_tile = _web_mercator_to_tile(min_x, min_y, zoom)
    east_tile, north_tile = _web_mercator_to_tile(max_x, max_y, zoom)
    min_tile_x, max_tile_x = sorted((west_tile, east_tile))
    min_tile_y, max_tile_y = sorted((north_tile, south_tile))

    tile_size = 256
    canvas = Image.new(
        "RGB",
        ((max_tile_x - min_tile_x + 1) * tile_size, (max_tile_y - min_tile_y + 1) * tile_size),
        "white",
    )
    loaded_any = False
    for tile_x in range(min_tile_x, max_tile_x + 1):
        for tile_y in range(min_tile_y, max_tile_y + 1):
            tile = _load_tile(provider, tile_x, tile_y, zoom, cache_dir)
            if tile is None:
                continue
            loaded_any = True
            canvas.paste(tile, ((tile_x - min_tile_x) * tile_size, (tile_y - min_tile_y) * tile_size))

    if not loaded_any:
        return None

    west, _, _, north = _tile_bounds_web_mercator(min_tile_x, min_tile_y, zoom)
    _, east, south, _ = _tile_bounds_web_mercator(max_tile_x, max_tile_y, zoom)
    return canvas, (west, east, south, north), provider["attribution"]


def _load_tile(provider: dict[str, str | int], tile_x: int, tile_y: int, zoom: int, cache_dir: Path) -> Image.Image | None:
    provider_key = str(provider["key"])
    cache_path = cache_dir / provider_key / str(zoom) / str(tile_x) / f"{tile_y}.png"
    if cache_path.exists():
        return Image.open(cache_path).convert("RGB")

    url = str(provider["url"]).format(z=zoom, x=tile_x, y=tile_y)
    try:
        response = requests.get(url, timeout=12, headers={"User-Agent": "2d-geophone-imshow/0.1"})
        response.raise_for_status()
    except requests.RequestException:
        return None

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(response.content)
    return Image.open(cache_path).convert("RGB")


def _xyz_provider(provider_name: str) -> dict[str, str | int]:
    providers: dict[str, dict[str, str | int]] = {
        "Esri.WorldTopoMap": {
            "key": "esri_world_topo",
            "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
            "zoom": 17,
            "attribution": "Tiles (C) Esri",
        },
        "Esri.WorldImagery": {
            "key": "esri_world_imagery",
            "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            "zoom": 17,
            "attribution": "Tiles (C) Esri",
        },
        "Esri.WorldPhysical": {
            "key": "esri_world_physical",
            "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Physical_Map/MapServer/tile/{z}/{y}/{x}",
            "zoom": 8,
            "attribution": "Tiles (C) Esri",
        },
        "OpenTopoMap": {
            "key": "opentopomap",
            "url": "https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
            "zoom": 15,
            "attribution": "Map data (C) OpenStreetMap contributors, SRTM | OpenTopoMap",
        },
    }
    return providers.get(provider_name, providers["Esri.WorldTopoMap"])
