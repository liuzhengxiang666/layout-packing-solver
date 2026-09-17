"""Small dependency-free 2-D geometry helpers used by the solver."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, hypot, radians, sin
from typing import Iterable, Sequence

EPS = 1e-7
Point = tuple[float, float]


def add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def mul(a: Point, value: float) -> Point:
    return a[0] * value, a[1] * value


def dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def length(a: Point) -> float:
    return hypot(a[0], a[1])


def unit(a: Point) -> Point:
    size = length(a)
    if size <= EPS:
        raise ValueError("zero-length vector")
    return a[0] / size, a[1] / size


def signed_area(polygon: Sequence[Point]) -> float:
    return sum(cross(polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon))) / 2


def point_on_segment(point: Point, a: Point, b: Point, eps: float = EPS) -> bool:
    ab = sub(b, a)
    ap = sub(point, a)
    scale = max(1.0, length(ab))
    return abs(cross(ab, ap)) <= eps * scale and dot(ap, sub(point, b)) <= eps


def point_in_polygon(point: Point, polygon: Sequence[Point], include_boundary: bool = True) -> bool:
    """Ray casting containment test for a simple, possibly concave polygon."""
    inside = False
    px, py = point
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        if point_on_segment(point, a, b):
            return include_boundary
        if (a[1] > py) != (b[1] > py):
            crossing_x = a[0] + (py - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if crossing_x > px:
                inside = not inside
    return inside


def _orientation(a: Point, b: Point, c: Point) -> float:
    return cross(sub(b, a), sub(c, a))


def proper_segment_intersection(a: Point, b: Point, c: Point, d: Point) -> bool:
    """True only when two segments cross through one another, not when they merely touch."""
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)
    return ((o1 > EPS and o2 < -EPS) or (o1 < -EPS and o2 > EPS)) and (
        (o3 > EPS and o4 < -EPS) or (o3 < -EPS and o4 > EPS)
    )


def rectangle_vertices(center: Point, size: tuple[float, float], angle_degrees: float) -> tuple[Point, ...]:
    """Return rectangle vertices counter-clockwise. Size is (local-x, local-y)."""
    angle = radians(angle_degrees)
    ux = (cos(angle), sin(angle))
    uy = (-sin(angle), cos(angle))
    hx, hy = size[0] / 2, size[1] / 2
    return (
        add(center, add(mul(ux, -hx), mul(uy, -hy))),
        add(center, add(mul(ux, hx), mul(uy, -hy))),
        add(center, add(mul(ux, hx), mul(uy, hy))),
        add(center, add(mul(ux, -hx), mul(uy, hy))),
    )


def convex_polygons_overlap(a: Sequence[Point], b: Sequence[Point], eps: float = 1e-6) -> bool:
    """Strict overlap test. Boundary touching is deliberately allowed."""
    for polygon in (a, b):
        for index, first in enumerate(polygon):
            second = polygon[(index + 1) % len(polygon)]
            edge = sub(second, first)
            axis = (-edge[1], edge[0])
            a_values = [dot(point, axis) for point in a]
            b_values = [dot(point, axis) for point in b]
            if min(max(a_values), max(b_values)) - max(min(a_values), min(b_values)) <= eps:
                return False
    return True


def polygon_inside_room(inner: Sequence[Point], room: Sequence[Point]) -> bool:
    """Check that a convex polygon is wholly contained in a simple room polygon."""
    probes: list[Point] = list(inner)
    probes.append((sum(p[0] for p in inner) / len(inner), sum(p[1] for p in inner) / len(inner)))
    for index, a in enumerate(inner):
        b = inner[(index + 1) % len(inner)]
        probes.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    if not all(point_in_polygon(point, room, include_boundary=True) for point in probes):
        return False
    for index, a in enumerate(inner):
        b = inner[(index + 1) % len(inner)]
        for room_index, c in enumerate(room):
            d = room[(room_index + 1) % len(room)]
            if proper_segment_intersection(a, b, c, d):
                return False
    return True


def distance_point_to_segment(point: Point, a: Point, b: Point) -> float:
    ab = sub(b, a)
    denominator = dot(ab, ab)
    if denominator <= EPS:
        return length(sub(point, a))
    t = max(0.0, min(1.0, dot(sub(point, a), ab) / denominator))
    projection = add(a, mul(ab, t))
    return length(sub(point, projection))


def normalize_angle(angle: float) -> float:
    result = angle % 180.0
    return 0.0 if abs(result - 180.0) < 1e-8 or abs(result) < 1e-8 else result


def bounds(points: Iterable[Point]) -> tuple[float, float, float, float]:
    values = list(points)
    return (
        min(point[0] for point in values),
        min(point[1] for point in values),
        max(point[0] for point in values),
        max(point[1] for point in values),
    )


@dataclass(frozen=True)
class OrientedRect:
    center: Point
    size: tuple[float, float]
    angle: float

    @property
    def vertices(self) -> tuple[Point, ...]:
        return rectangle_vertices(self.center, self.size, self.angle)

