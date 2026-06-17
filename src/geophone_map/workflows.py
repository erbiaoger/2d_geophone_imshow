from __future__ import annotations

from pathlib import Path

from geophone_map.georeference import project_array_points
from geophone_map.plotting import save_basemap_plot, save_folium_map, save_points_csv, save_static_plot
from geophone_map.sac_coordinates import (
    GeophonePoint,
    collect_filename_station_points,
    collect_sac_points,
    collect_station_points,
    find_default_gps_db,
    load_igu_gps_coordinates,
)


def collect_points_from_sac_source(
    data_root: Path,
    *,
    coordinate_mode: str = "auto",
    group_by: str = "auto",
    gps_db: str = "auto",
    origin_lat: float | None = None,
    origin_lon: float | None = None,
    x_spacing_m: float = 1.0,
    y_spacing_m: float = 1.0,
    x_bearing_deg: float = 90.0,
    y_bearing_deg: float = 0.0,
) -> tuple[list[GeophonePoint], Path | None, str]:
    data_root = Path(data_root)
    resolved_group_by = resolve_group_by(data_root, group_by)
    resolved_gps_db = resolve_gps_db(data_root, gps_db)
    gps_coordinates = load_igu_gps_coordinates(resolved_gps_db) if resolved_gps_db is not None else {}

    if resolved_group_by == "station-folder":
        points = collect_station_points(data_root, coordinate_mode=coordinate_mode)
    elif resolved_group_by == "filename-prefix":
        points = collect_filename_station_points(
            data_root,
            coordinate_mode=coordinate_mode,
            gps_coordinates=gps_coordinates,
        )
    else:
        points = collect_sac_points(data_root, coordinate_mode=coordinate_mode)

    if origin_lat is not None or origin_lon is not None:
        if origin_lat is None or origin_lon is None:
            raise ValueError("--origin-lat and --origin-lon must be provided together")
        points = project_array_points(
            points,
            origin_latitude=origin_lat,
            origin_longitude=origin_lon,
            x_spacing_m=x_spacing_m,
            y_spacing_m=y_spacing_m,
            x_bearing_deg=x_bearing_deg,
            y_bearing_deg=y_bearing_deg,
        )

    return points, resolved_gps_db, resolved_group_by


def render_point_outputs(
    points: list[GeophonePoint],
    output_dir: Path,
    *,
    title: str = "Geophone Station Coordinates",
    basemap_provider: str = "Esri.WorldImagery",
    basemap_margin_factor: float = 0.18,
    html_map_margin_factor: float = 1.2,
    html_basemap_zoom: int = 14,
) -> dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "geophone_array_coordinates.csv"
    png_path = output_dir / "geophone_array.png"
    basemap_path = output_dir / "geophone_basemap.png"
    html_path = output_dir / "geophone_map.html"
    live_html_path = output_dir / "geophone_map_live.html"

    save_points_csv(points, csv_path)
    save_static_plot(points, png_path, title=title)
    basemap_count = save_basemap_plot(
        points,
        basemap_path,
        title=title,
        provider_name=basemap_provider,
        margin_factor=basemap_margin_factor,
    )
    mapped_count = save_folium_map(
        points,
        html_path,
        provider_name=basemap_provider,
        margin_factor=html_map_margin_factor,
        basemap_zoom=html_basemap_zoom,
        map_mode="embedded",
    )
    live_mapped_count = save_folium_map(
        points,
        live_html_path,
        provider_name=basemap_provider,
        margin_factor=html_map_margin_factor,
        basemap_zoom=html_basemap_zoom,
        map_mode="live",
    )

    return {
        "csv_path": csv_path,
        "png_path": png_path,
        "basemap_path": basemap_path,
        "html_path": html_path,
        "live_html_path": live_html_path,
        "basemap_count": basemap_count,
        "mapped_count": mapped_count,
        "live_mapped_count": live_mapped_count,
    }


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
