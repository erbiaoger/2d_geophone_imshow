from __future__ import annotations

import struct
import sys
import sqlite3
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from geophone_map.sac_coordinates import (
    SAC_NULL,
    collect_sac_points,
    collect_filename_station_points,
    collect_station_points,
    load_points_from_csv,
    load_igu_gps_coordinates,
    parse_array_position,
    read_sac_coordinates,
    valid_lonlat,
)
from geophone_map.georeference import project_array_points
from geophone_map.plotting import _lonlat_to_web_mercator, _web_mercator_to_lonlat


def write_sac(path: Path, *, stla: float = SAC_NULL, stlo: float = SAC_NULL) -> None:
    floats = [SAC_NULL] * 70
    floats[0] = 0.002
    floats[5] = 0.0
    floats[31] = stla
    floats[32] = stlo
    ints = [-12345] * 40
    strings = [b"-12345  "] * 24
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        struct.pack("<70f", *floats)
        + struct.pack("<40i", *ints)
        + b"".join(strings)
        + struct.pack("<10f", *([0.0] * 10))
    )


def test_read_sac_coordinates_reads_little_endian_stla_stlo(tmp_path: Path) -> None:
    sac_path = tmp_path / "1" / "S1_Z_1.sac"
    write_sac(sac_path, stla=40.123, stlo=116.456)

    coords = read_sac_coordinates(sac_path)

    assert round(coords.latitude, 3) == 40.123
    assert round(coords.longitude, 3) == 116.456


def test_valid_lonlat_rejects_sac_null_and_zero_zero() -> None:
    assert not valid_lonlat(SAC_NULL, SAC_NULL)
    assert not valid_lonlat(0.0, 0.0)
    assert valid_lonlat(40.0, 116.0)


def test_parse_array_position_uses_parent_and_filename_indices(tmp_path: Path) -> None:
    sac_path = tmp_path / "12" / "S12_Z_34.sac"
    sac_path.parent.mkdir()
    sac_path.touch()

    position = parse_array_position(sac_path)

    assert position is not None
    assert position.row == 12
    assert position.column == 34
    assert position.x == 34
    assert position.y == 12


def test_collect_sac_points_falls_back_to_array_coordinates(tmp_path: Path) -> None:
    write_sac(tmp_path / "1" / "S1_Z_1.sac")
    write_sac(tmp_path / "1" / "S1_Z_2.sac")
    write_sac(tmp_path / "2" / "S2_Z_1.sac", stla=40.1, stlo=116.2)

    points = collect_sac_points(tmp_path)

    assert len(points) == 3
    by_name = {point.file_name: point for point in points}
    assert by_name["S1_Z_1.sac"].coordinate_source == "array"
    assert by_name["S1_Z_1.sac"].x == 1
    assert by_name["S1_Z_2.sac"].x == 2
    assert by_name["S2_Z_1.sac"].coordinate_source == "sac_lonlat"
    assert by_name["S2_Z_1.sac"].longitude == pytest.approx(116.2)


def test_collect_sac_points_array_mode_skips_sac_lonlat(tmp_path: Path) -> None:
    write_sac(tmp_path / "2" / "S2_Z_1.sac", stla=40.1, stlo=116.2)

    points = collect_sac_points(tmp_path, coordinate_mode="array")

    assert len(points) == 1
    assert points[0].coordinate_source == "array"
    assert points[0].latitude is None
    assert points[0].x == 1


def test_collect_station_points_keeps_one_representative_per_folder(tmp_path: Path) -> None:
    write_sac(tmp_path / "1" / "S1_Z_1.sac")
    write_sac(tmp_path / "1" / "S1_Z_2.sac")
    write_sac(tmp_path / "2" / "S2_Z_1.sac")
    write_sac(tmp_path / "2" / "S2_Z_2.sac")

    points = collect_station_points(tmp_path, coordinate_mode="array")

    assert len(points) == 2
    assert [point.row for point in points] == [1, 2]
    assert [point.file_name for point in points] == ["S1_Z_1.sac", "S2_Z_1.sac"]
    assert [point.x for point in points] == [1.0, 2.0]
    assert all(point.y == 0.0 for point in points)
    assert all(point.coordinate_source == "station_index" for point in points)


def test_collect_filename_station_points_keeps_one_representative_per_station(tmp_path: Path) -> None:
    write_sac(tmp_path / "453010490.00000001.2024.08.14.06.55.20.000.z.sac")
    write_sac(tmp_path / "453010490.00000001.2024.08.22.06.55.20.000.z.sac")
    write_sac(tmp_path / "453011985.00000001.2024.08.14.03.45.16.000.z.sac")

    points = collect_filename_station_points(tmp_path, coordinate_mode="array")

    assert len(points) == 2
    assert [point.row for point in points] == [453010490, 453011985]
    assert [point.x for point in points] == [1.0, 2.0]
    assert all(point.coordinate_source == "station_index" for point in points)


def test_collect_filename_station_points_uses_gps_coordinates(tmp_path: Path) -> None:
    write_sac(tmp_path / "453010490.00000001.2024.08.14.06.55.20.000.z.sac")
    db_path = tmp_path / "dccigugps.db"
    create_gps_db(db_path)
    gps = load_igu_gps_coordinates(db_path)

    points = collect_filename_station_points(tmp_path, coordinate_mode="auto", gps_coordinates=gps)

    assert len(points) == 1
    assert points[0].coordinate_source == "gps_db"
    assert points[0].latitude == pytest.approx(42.1)
    assert points[0].longitude == pytest.approx(128.2)
    assert points[0].elevation_m == pytest.approx(1100.0)


def test_load_points_from_csv_prefers_lonlat_and_elevation(tmp_path: Path) -> None:
    csv_path = tmp_path / "stations.csv"
    csv_path.write_text(
        "station,lat,lon,elevation,path\n"
        "101,42.1,128.2,1100,/tmp/A.sac\n",
        encoding="utf-8",
    )

    points = load_points_from_csv(csv_path)

    assert len(points) == 1
    assert points[0].row == 101
    assert points[0].longitude == pytest.approx(128.2)
    assert points[0].latitude == pytest.approx(42.1)
    assert points[0].elevation_m == pytest.approx(1100.0)
    assert points[0].coordinate_source == "csv_lonlat"
    assert points[0].file_name == "A.sac"


def test_load_points_from_csv_accepts_xy_aliases(tmp_path: Path) -> None:
    csv_path = tmp_path / "stations_xy.csv"
    csv_path.write_text(
        "station_id,X,Y,file_name\n"
        "202,12.5,9.5,station202\n",
        encoding="utf-8",
    )

    points = load_points_from_csv(csv_path)

    assert len(points) == 1
    assert points[0].row == 202
    assert points[0].x == pytest.approx(12.5)
    assert points[0].y == pytest.approx(9.5)
    assert points[0].coordinate_source == "csv_xy"
    assert points[0].file_name == "station202"


def test_project_array_points_uses_origin_spacing_and_bearings(tmp_path: Path) -> None:
    write_sac(tmp_path / "1" / "S1_Z_1.sac")
    write_sac(tmp_path / "1" / "S1_Z_2.sac")
    points = collect_sac_points(tmp_path)

    projected = project_array_points(
        points,
        origin_latitude=40.0,
        origin_longitude=116.0,
        x_spacing_m=10.0,
        y_spacing_m=20.0,
        x_bearing_deg=90.0,
        y_bearing_deg=0.0,
    )

    assert projected[0].latitude == 40.0
    assert projected[0].longitude == 116.0
    assert projected[1].longitude > projected[0].longitude
    assert round(projected[1].latitude, 6) == 40.0


def test_lonlat_to_web_mercator_projects_origin_and_positive_longitude() -> None:
    x0, y0 = _lonlat_to_web_mercator(0.0, 0.0)
    x1, y1 = _lonlat_to_web_mercator(128.0, 42.0)
    lon1, lat1 = _web_mercator_to_lonlat(x1, y1)

    assert x0 == pytest.approx(0.0)
    assert y0 == pytest.approx(0.0, abs=1e-8)
    assert x1 > x0
    assert y1 > y0
    assert lon1 == pytest.approx(128.0)
    assert lat1 == pytest.approx(42.0)


def create_gps_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IGUGPSDATA (
                IGU_ID INT,
                GPS_LAT FLOAT,
                GPS_LONG FLOAT,
                GPS_ELV FLOAT,
                GPS_REC_VALID_COUNT INT
            )
            """
        )
        connection.executemany(
            "INSERT INTO IGUGPSDATA VALUES (?, ?, ?, ?, ?)",
            [
                (453010490, 42.0, 128.0, 1000.0, 1),
                (453010490, 42.2, 128.4, 1200.0, 1),
                (453010490, 0.0, 0.0, 0.0, 100),
            ],
        )
