from __future__ import annotations

import math

from geophone_map.sac_coordinates import GeophonePoint

EARTH_RADIUS_M = 6_371_008.8


def project_array_points(
    points: list[GeophonePoint],
    *,
    origin_latitude: float,
    origin_longitude: float,
    x_spacing_m: float,
    y_spacing_m: float,
    x_bearing_deg: float = 90.0,
    y_bearing_deg: float = 0.0,
    origin_x: float | None = None,
    origin_y: float | None = None,
) -> list[GeophonePoint]:
    """Project array index coordinates into approximate WGS84 lon/lat coordinates."""
    if not points:
        return []

    origin_x = min(point.x for point in points) if origin_x is None else origin_x
    origin_y = min(point.y for point in points) if origin_y is None else origin_y
    x_bearing = math.radians(x_bearing_deg)
    y_bearing = math.radians(y_bearing_deg)
    lat0 = math.radians(origin_latitude)

    projected: list[GeophonePoint] = []
    for point in points:
        x_distance = (point.x - origin_x) * x_spacing_m
        y_distance = (point.y - origin_y) * y_spacing_m

        east_m = x_distance * math.sin(x_bearing) + y_distance * math.sin(y_bearing)
        north_m = x_distance * math.cos(x_bearing) + y_distance * math.cos(y_bearing)

        latitude = origin_latitude + math.degrees(north_m / EARTH_RADIUS_M)
        longitude = origin_longitude + math.degrees(east_m / (EARTH_RADIUS_M * math.cos(lat0)))
        projected.append(point.with_lonlat(latitude, longitude, "projected_array"))

    return projected

