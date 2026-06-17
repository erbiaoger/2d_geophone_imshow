from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, replace
from pathlib import Path

SAC_NULL = -12345.0
SAC_HEADER_BYTES = 632
_SAC_FLOAT_COUNT = 70
_ARRAY_NAME_RE = re.compile(r"^S(?P<row>\d+)_Z_(?P<column>\d+)\.sac$", re.IGNORECASE)


@dataclass(frozen=True)
class SACCoordinates:
    latitude: float
    longitude: float
    elevation_m: float
    byte_order: str


@dataclass(frozen=True)
class ArrayPosition:
    row: int
    column: int
    x: float
    y: float


@dataclass(frozen=True)
class GeophonePoint:
    path: Path
    file_name: str
    row: int | None
    column: int | None
    x: float
    y: float
    latitude: float | None
    longitude: float | None
    coordinate_source: str

    def with_lonlat(self, latitude: float, longitude: float, source: str) -> "GeophonePoint":
        return replace(
            self,
            latitude=latitude,
            longitude=longitude,
            coordinate_source=source,
        )


def read_sac_coordinates(path: Path) -> SACCoordinates:
    """Read station coordinates from the binary SAC header."""
    with Path(path).open("rb") as handle:
        header = handle.read(SAC_HEADER_BYTES)
    if len(header) < 280:
        raise ValueError(f"{path} is too small to contain a SAC float header")

    candidates = []
    for byte_order in ("<", ">"):
        floats = struct.unpack(f"{byte_order}{_SAC_FLOAT_COUNT}f", header[:280])
        delta = floats[0]
        score = 0
        if 0 < abs(delta) < 10_000:
            score += 1
        if -90 <= floats[31] <= 90 or floats[31] == SAC_NULL:
            score += 1
        if -180 <= floats[32] <= 180 or floats[32] == SAC_NULL:
            score += 1
        candidates.append((score, byte_order, floats))

    _, byte_order, floats = max(candidates, key=lambda item: item[0])
    return SACCoordinates(
        latitude=float(floats[31]),
        longitude=float(floats[32]),
        elevation_m=float(floats[33]),
        byte_order=byte_order,
    )


def valid_lonlat(latitude: float | None, longitude: float | None) -> bool:
    if latitude is None or longitude is None:
        return False
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return False
    if abs(latitude - SAC_NULL) < 1e-3 or abs(longitude - SAC_NULL) < 1e-3:
        return False
    if abs(latitude) < 1e-12 and abs(longitude) < 1e-12:
        return False
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


def parse_array_position(path: Path) -> ArrayPosition | None:
    match = _ARRAY_NAME_RE.match(Path(path).name)
    if not match:
        return None

    row = int(match.group("row"))
    column = int(match.group("column"))
    return ArrayPosition(row=row, column=column, x=float(column), y=float(row))


def collect_sac_points(root: Path, *, coordinate_mode: str = "auto") -> list[GeophonePoint]:
    """Collect usable geophone coordinates from SAC files under a data root."""
    if coordinate_mode not in {"auto", "array", "sac"}:
        raise ValueError("coordinate_mode must be one of: auto, array, sac")

    root = Path(root)
    paths = sorted(root.rglob("*.sac"), key=_sac_sort_key)
    points: list[GeophonePoint] = []

    for path in paths:
        position = parse_array_position(path)
        coords = SACCoordinates(SAC_NULL, SAC_NULL, SAC_NULL, "<")
        if coordinate_mode in {"auto", "sac"}:
            try:
                coords = read_sac_coordinates(path)
            except ValueError:
                coords = SACCoordinates(SAC_NULL, SAC_NULL, SAC_NULL, "<")

        if coordinate_mode in {"auto", "sac"} and valid_lonlat(coords.latitude, coords.longitude):
            x = coords.longitude
            y = coords.latitude
            source = "sac_lonlat"
            latitude = coords.latitude
            longitude = coords.longitude
        elif coordinate_mode in {"auto", "array"} and position is not None:
            x = position.x
            y = position.y
            source = "array"
            latitude = None
            longitude = None
        else:
            continue

        points.append(
            GeophonePoint(
                path=path,
                file_name=path.name,
                row=position.row if position else None,
                column=position.column if position else None,
                x=x,
                y=y,
                latitude=latitude,
                longitude=longitude,
                coordinate_source=source,
            )
        )

    return points


def collect_station_points(root: Path, *, coordinate_mode: str = "auto") -> list[GeophonePoint]:
    """Collect one representative point per station folder."""
    if coordinate_mode not in {"auto", "array", "sac"}:
        raise ValueError("coordinate_mode must be one of: auto, array, sac")

    root = Path(root)
    station_dirs = sorted(
        [path for path in root.iterdir() if path.is_dir() and path.name.isdigit()],
        key=lambda path: int(path.name),
    )
    points: list[GeophonePoint] = []

    for station_dir in station_dirs:
        station_index = int(station_dir.name)
        path = _representative_sac_for_station(station_dir, station_index)
        if path is None:
            continue

        coords = SACCoordinates(SAC_NULL, SAC_NULL, SAC_NULL, "<")
        if coordinate_mode in {"auto", "sac"}:
            try:
                coords = read_sac_coordinates(path)
            except ValueError:
                coords = SACCoordinates(SAC_NULL, SAC_NULL, SAC_NULL, "<")

        if coordinate_mode in {"auto", "sac"} and valid_lonlat(coords.latitude, coords.longitude):
            x = coords.longitude
            y = coords.latitude
            source = "sac_lonlat"
            latitude = coords.latitude
            longitude = coords.longitude
        elif coordinate_mode in {"auto", "array"}:
            x = float(station_index)
            y = 0.0
            source = "station_index"
            latitude = None
            longitude = None
        else:
            continue

        points.append(
            GeophonePoint(
                path=path,
                file_name=path.name,
                row=station_index,
                column=None,
                x=x,
                y=y,
                latitude=latitude,
                longitude=longitude,
                coordinate_source=source,
            )
        )

    return points


def _sac_sort_key(path: Path) -> tuple[int, int, str]:
    position = parse_array_position(path)
    if position:
        return (position.row, position.column, path.name)
    parent = path.parent.name
    parent_index = int(parent) if parent.isdigit() else 10**9
    return (parent_index, 10**9, path.name)


def _representative_sac_for_station(station_dir: Path, station_index: int) -> Path | None:
    preferred = station_dir / f"S{station_index}_Z_1.sac"
    if preferred.exists():
        return preferred
    paths = sorted(station_dir.glob("*.sac"), key=_sac_sort_key)
    return paths[0] if paths else None
