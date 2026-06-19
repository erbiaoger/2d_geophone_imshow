from __future__ import annotations

from pathlib import Path

import pytest

from geophone_map.fiber_interpolation import interpolate_fiber_along_route, interpolate_fiber_points
from geophone_map.sac_coordinates import GeophonePoint


def point(latitude: float, longitude: float, elevation_m: float | None = None) -> GeophonePoint:
    return GeophonePoint(
        path=Path("test.txt"),
        file_name="test",
        row=None,
        column=None,
        x=longitude,
        y=latitude,
        latitude=latitude,
        longitude=longitude,
        elevation_m=elevation_m,
        coordinate_source="test",
    )


def test_interpolate_fiber_points_samples_every_spacing_and_keeps_endpoint() -> None:
    points = [
        point(42.0, 128.0, 1000.0),
        point(42.0, 128.0001, 1010.0),
        point(42.0, 128.0002, 1020.0),
    ]

    interpolated, total_length_m = interpolate_fiber_points(points, spacing_m=10.0)

    assert total_length_m == pytest.approx(16.546, abs=0.02)
    assert [item.distance_m for item in interpolated] == pytest.approx([0.0, 10.0, total_length_m])
    assert interpolated[0].longitude == pytest.approx(128.0)
    assert interpolated[-1].longitude == pytest.approx(128.0002)
    assert interpolated[-1].elevation_m == pytest.approx(1020.0)


def test_interpolate_fiber_along_route_follows_route_bend() -> None:
    points = [
        point(42.0, 128.0, 1000.0),
        point(42.001, 128.001, 1020.0),
    ]
    route = [
        (42.0, 128.0),
        (42.001, 128.0),
        (42.001, 128.001),
    ]

    interpolated, total_length_m = interpolate_fiber_along_route(points, route, spacing_m=100.0)

    assert total_length_m > 190.0
    assert any(sample.latitude > 42.0008 and sample.longitude < 128.0002 for sample in interpolated)
    assert interpolated[-1].latitude == pytest.approx(42.001)
    assert interpolated[-1].longitude == pytest.approx(128.001)
