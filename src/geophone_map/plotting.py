from __future__ import annotations

from pathlib import Path

import folium
import matplotlib.pyplot as plt
import pandas as pd

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

    station_index_plot = df["column"].isna().all() and df["coordinate_source"].eq("station_index").any()
    xlabel = "Station index / Longitude" if station_index_plot else "Column index / Longitude"
    ylabel = "Relative Y / Latitude" if station_index_plot else "Line index / Latitude"
    colorbar_label = "Station index" if station_index_plot else "Line index"

    scatter = ax.scatter(
        df["x"],
        df["y"],
        c=df["row"].fillna(0),
        s=12,
        cmap="viridis",
        alpha=0.85,
        edgecolors="none",
        rasterized=True,
    )
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    _expand_degenerate_axis(ax, df["x"].min(), df["x"].max(), axis="x")
    _expand_degenerate_axis(ax, df["y"].min(), df["y"].max(), axis="y")
    if df["x"].nunique() > 1 and df["y"].nunique() > 1:
        ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.25, linewidth=0.6)
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


def _expand_degenerate_axis(ax, lower: float, upper: float, *, axis: str) -> None:
    if lower != upper:
        return
    margin = 1.0 if lower == 0 else abs(lower) * 0.05
    setter = ax.set_xlim if axis == "x" else ax.set_ylim
    setter(lower - margin, upper + margin)
