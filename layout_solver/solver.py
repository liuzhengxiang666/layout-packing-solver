"""Wall-first placement search for rectangles inside a polygon."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, cos, degrees, radians, sin
from typing import Any, Iterable

from .geometry import (
    EPS,
    OrientedRect,
    Point,
    add,
    bounds,
    convex_polygons_overlap,
    length,
    mul,
    normalize_angle,
    point_in_polygon,
    polygon_inside_room,
    signed_area,
    sub,
    unit,
)


@dataclass(frozen=True)
class Item:
    name: str
    size: tuple[float, float]
    kind: str


@dataclass(frozen=True)
class Candidate:
    rect: OrientedRect
    protected: OrientedRect | None
    wall: bool
    wall_index: int
    wall_position: float
    rank: int = 0


@dataclass
class SearchStats:
    nodes: int = 0
    backtracks: int = 0
    candidates: int = 0


def item_kind(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith("fridge"):
        return "fridge"
    if lowered.startswith("overshelf"):
        return "overShelf"
    if lowered.startswith("shelf"):
        return "shelf"
    if lowered.startswith("icemaker"):
        return "iceMaker"
    return name.split("-", 1)[0]


class LayoutSolver:
    """Solve one layout instance.

    ``fridge_clearance`` reserves a rectangular no-placement strip in front of
    the fridge's opening edge. The statement does not supply a number, so the
    small default is a documented, configurable modelling assumption.
    """

    def __init__(
        self,
        data: dict[str, Any],
        *,
        grid_step: float = 100.0,
        wall_step: float = 100.0,
        fridge_clearance: float = 10.0,
        outward_door_depth: float = 100.0,
        node_limit: int = 500_000,
    ) -> None:
        raw_boundary = [tuple(map(float, point)) for point in data["boundary"]]
        if len(raw_boundary) >= 2 and raw_boundary[0] == raw_boundary[-1]:
            raw_boundary.pop()
        if len(raw_boundary) < 3 or abs(signed_area(raw_boundary)) <= EPS:
            raise ValueError("boundary must be a non-degenerate polygon")
        self.room: tuple[Point, ...] = tuple(raw_boundary)
        self.ccw = signed_area(self.room) > 0
        self.door: tuple[Point, Point] = tuple(tuple(map(float, p)) for p in data["door"])  # type: ignore[assignment]
        self.is_open_inward = bool(data.get("isOpenInward", False))
        self.items = [
            Item(name, tuple(map(float, size)), item_kind(name))
            for name, size in data["algoToPlace"].items()
        ]
        if any(item.size[0] <= 0 or item.size[1] <= 0 for item in self.items):
            raise ValueError("all item dimensions must be positive")
        self.grid_step = max(20.0, grid_step)
        self.wall_step = max(20.0, wall_step)
        self.fridge_clearance = max(0.0, fridge_clearance)
        self.outward_door_depth = max(1.0, outward_door_depth)
        self.node_limit = node_limit
        self.stats = SearchStats()
        door_width = length(sub(self.door[1], self.door[0]))
        door_depth = door_width if self.is_open_inward else self.outward_door_depth
        self.door_zone = self._inward_zone(self.door[0], self.door[1], door_depth)
        self._candidate_cache: dict[tuple[float, float, str], list[Candidate]] = {}

    def _wall_inward_normal(self, a: Point, b: Point) -> Point:
        direction = unit(sub(b, a))
        return (-direction[1], direction[0]) if self.ccw else (direction[1], -direction[0])

    def _inward_zone(self, a: Point, b: Point, depth: float) -> OrientedRect:
        direction = unit(sub(b, a))
        normals = [(-direction[1], direction[0]), (direction[1], -direction[0])]
        middle = mul(add(a, b), 0.5)
        chosen = max(normals, key=lambda normal: int(point_in_polygon(add(middle, mul(normal, depth * 0.5)), self.room)))
        angle = degrees(atan2(direction[1], direction[0]))
        return OrientedRect(add(middle, mul(chosen, depth / 2)), (length(sub(b, a)), depth), angle)

    def _fridge_protected(self, rect: OrientedRect, front_sign: int = 1) -> OrientedRect | None:
        if self.fridge_clearance <= EPS:
            return None
        angle = radians(rect.angle)
        local_y = (-sin(angle), cos(angle))
        center = add(rect.center, mul(local_y, front_sign * (rect.size[1] + self.fridge_clearance) / 2))
        return OrientedRect(center, (rect.size[0], self.fridge_clearance), rect.angle)

    def _valid_geometry(self, rect: OrientedRect, protected: OrientedRect | None) -> bool:
        if not polygon_inside_room(rect.vertices, self.room):
            return False
        if convex_polygons_overlap(rect.vertices, self.door_zone.vertices):
            return False
        if protected is not None:
            if not polygon_inside_room(protected.vertices, self.room):
                return False
            if convex_polygons_overlap(protected.vertices, self.door_zone.vertices):
                return False
        return True

    @staticmethod
    def _positions(span: float, wall_length: float, step: float) -> Iterable[float]:
        low, high = span / 2, wall_length - span / 2
        if high < low - EPS:
            return []
        count = max(1, int(ceil((high - low) / step)))
        values = {low, high}
        values.update(low + (high - low) * index / count for index in range(count + 1))
        return sorted(values)

    def _wall_candidates(self, item: Item) -> list[Candidate]:
        result: list[Candidate] = []
        for wall_index, a in enumerate(self.room):
            b = self.room[(wall_index + 1) % len(self.room)]
            vector = sub(b, a)
            wall_length = length(vector)
            if wall_length <= EPS:
                continue
            along = unit(vector)
            inward = self._wall_inward_normal(a, b)
            edge_angle = degrees(atan2(along[1], along[0]))
            modes = [(item.size[0], item.size[1], edge_angle)]
            if item.kind != "fridge":
                modes.append((item.size[1], item.size[0], edge_angle - 90.0))
            for span, depth, angle in modes:
                for position in self._positions(span, wall_length, self.wall_step):
                    # A sub-millimetre inset makes serialized coordinates
                    # robust to decimal rounding while still representing a
                    # wall placement for practical purposes.
                    center = add(add(a, mul(along, position)), mul(inward, depth / 2 + 0.1))
                    rect = OrientedRect(center, item.size, normalize_angle(angle))
                    protected = None
                    if item.kind == "fridge":
                        # The fridge opening face points into the room.  The
                        # local-y direction may have been flipped when a wall
                        # angle was normalized to [0, 180), so derive its sign
                        # from the actual inward normal instead of assuming +y.
                        normalized = radians(rect.angle)
                        local_y = (-sin(normalized), cos(normalized))
                        front_sign = 1 if local_y[0] * inward[0] + local_y[1] * inward[1] >= 0 else -1
                        protected = self._fridge_protected(rect, front_sign)
                    candidate = Candidate(rect, protected, True, wall_index, position)
                    if self._valid_geometry(rect, protected):
                        result.append(candidate)
        return result

    def _room_orientations(self) -> list[float]:
        angles: set[float] = set()
        for index, a in enumerate(self.room):
            b = self.room[(index + 1) % len(self.room)]
            if length(sub(b, a)) <= EPS:
                continue
            base = degrees(atan2(b[1] - a[1], b[0] - a[0]))
            angles.add(round(normalize_angle(base), 7))
            angles.add(round(normalize_angle(base + 90), 7))
        return sorted(angles)

    def _grid_candidates(self, item: Item) -> list[Candidate]:
        min_x, min_y, max_x, max_y = bounds(self.room)
        result: list[Candidate] = []
        for angle in self._room_orientations():
            x = min_x
            while x <= max_x + EPS:
                y = min_y
                while y <= max_y + EPS:
                    rect = OrientedRect((x, y), item.size, angle)
                    signs = (1, -1) if item.kind == "fridge" else (1,)
                    for sign in signs:
                        protected = self._fridge_protected(rect, sign) if item.kind == "fridge" else None
                        if self._valid_geometry(rect, protected):
                            result.append(Candidate(rect, protected, False, -1, x + y))
                    y += self.grid_step
                x += self.grid_step
        return result

    def candidates_for(self, item: Item) -> list[Candidate]:
        key = (item.size[0], item.size[1], item.kind)
        if key not in self._candidate_cache:
            candidates = self._wall_candidates(item) + self._grid_candidates(item)
            seen: set[tuple[float, float, float, int]] = set()
            unique: list[Candidate] = []
            for candidate in candidates:
                signature = (
                    round(candidate.rect.center[0], 4),
                    round(candidate.rect.center[1], 4),
                    round(candidate.rect.angle, 4),
                    1 if candidate.wall else 0,
                )
                if signature not in seen:
                    seen.add(signature)
                    unique.append(candidate)
            unique.sort(key=lambda c: (not c.wall, c.wall_index, c.wall_position, c.rect.angle))
            self._candidate_cache[key] = [
                Candidate(c.rect, c.protected, c.wall, c.wall_index, c.wall_position, rank)
                for rank, c in enumerate(unique)
            ]
        return self._candidate_cache[key]

    @staticmethod
    def _fits(candidate: Candidate, placed: list[Candidate]) -> bool:
        for other in placed:
            if convex_polygons_overlap(candidate.rect.vertices, other.rect.vertices):
                return False
            if other.protected and convex_polygons_overlap(candidate.rect.vertices, other.protected.vertices):
                return False
            if candidate.protected and convex_polygons_overlap(candidate.protected.vertices, other.rect.vertices):
                return False
        return True

    def solve(self) -> dict[str, Any]:
        # Large and constrained equipment first; stable name ordering keeps output deterministic.
        ordered = sorted(
            self.items,
            key=lambda item: (item.kind != "fridge", -(item.size[0] * item.size[1]), item.name),
        )
        candidate_lists = {item.name: self.candidates_for(item) for item in ordered}
        self.stats.candidates = sum(len(values) for values in candidate_lists.values())
        if any(not candidate_lists[item.name] for item in ordered):
            return self._output(None)

        placed: list[Candidate] = []
        chosen: dict[str, Candidate] = {}
        previous_rank: dict[tuple[str, tuple[float, float]], int] = {}

        def visit(index: int) -> bool:
            self.stats.nodes += 1
            if self.stats.nodes > self.node_limit:
                return False
            if index == len(ordered):
                return True
            item = ordered[index]
            symmetry_key = (item.kind, item.size)
            minimum_rank = previous_rank.get(symmetry_key, -1) + 1
            for candidate in candidate_lists[item.name]:
                if candidate.rank < minimum_rank or not self._fits(candidate, placed):
                    continue
                old_rank = previous_rank.get(symmetry_key)
                previous_rank[symmetry_key] = candidate.rank
                placed.append(candidate)
                chosen[item.name] = candidate
                if visit(index + 1):
                    return True
                placed.pop()
                chosen.pop(item.name, None)
                if old_rank is None:
                    previous_rank.pop(symmetry_key, None)
                else:
                    previous_rank[symmetry_key] = old_rank
                self.stats.backtracks += 1
            return False

        return self._output(chosen if visit(0) else None)

    def _output(self, chosen: dict[str, Candidate] | None) -> dict[str, Any]:
        if chosen is None:
            return {
                "feasible": False,
                "placements": [],
                "message": "No layout was found within the configured search limit.",
                "search": vars(self.stats),
            }
        placements = []
        for item in self.items:
            candidate = chosen[item.name]
            placement = {
                "name": item.name,
                "type": item.kind,
                # Keep enough precision for rectangles placed exactly on a
                # slanted wall; coarse rounding can move a corner a tiny
                # distance outside the polygon.
                "center": [round(candidate.rect.center[0], 8), round(candidate.rect.center[1], 8)],
                "angle": round(normalize_angle(candidate.rect.angle), 8),
                "size": [item.size[0], item.size[1]],
                "againstWall": candidate.wall,
            }
            if item.kind == "fridge" and candidate.protected is not None:
                direction = unit(sub(candidate.protected.center, candidate.rect.center))
                placement["openingDirection"] = [round(direction[0], 8), round(direction[1], 8)]
            placements.append(placement)
        return {
            "feasible": True,
            "placements": placements,
            "assumptions": {
                "fridgeClearanceDepth": self.fridge_clearance,
                "outwardDoorAccessDepth": self.outward_door_depth,
                "touchingEdgesAllowed": True,
            },
            "search": vars(self.stats),
        }


def solve_layout(data: dict[str, Any], **options: Any) -> dict[str, Any]:
    return LayoutSolver(data, **options).solve()
