#!/usr/bin/env python3
"""Validate a result JSON independently of the placement search."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from layout_solver.geometry import OrientedRect, add, convex_polygons_overlap, mul, polygon_inside_room
from layout_solver.solver import LayoutSolver


def validate(data: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not result.get("feasible"):
        return ["result says the instance is not feasible"]
    solver = LayoutSolver(
        data,
        fridge_clearance=float(result.get("assumptions", {}).get("fridgeClearanceDepth", 10.0)),
        outward_door_depth=float(result.get("assumptions", {}).get("outwardDoorAccessDepth", 100.0)),
    )
    expected = set(data["algoToPlace"])
    actual = {placement.get("name") for placement in result.get("placements", [])}
    if expected != actual:
        errors.append(f"item names differ: expected {sorted(expected)}, got {sorted(actual)}")

    rectangles: list[tuple[str, OrientedRect]] = []
    protected_zones: list[tuple[str, OrientedRect]] = []
    wall_angles = []
    for index, a in enumerate(solver.room):
        b = solver.room[(index + 1) % len(solver.room)]
        from math import atan2, degrees

        wall_angles.append(degrees(atan2(b[1] - a[1], b[0] - a[0])) % 90)

    for placement in result.get("placements", []):
        name = placement.get("name", "<unknown>")
        if name not in data["algoToPlace"]:
            continue
        expected_size = tuple(map(float, data["algoToPlace"][name]))
        reported_size = tuple(map(float, placement.get("size", expected_size)))
        if reported_size != expected_size:
            errors.append(f"{name}: size changed from {expected_size} to {reported_size}")
        rect = OrientedRect(tuple(map(float, placement["center"])), expected_size, float(placement["angle"]))
        if not polygon_inside_room(rect.vertices, solver.room):
            errors.append(f"{name}: outside boundary")
        if convex_polygons_overlap(rect.vertices, solver.door_zone.vertices):
            errors.append(f"{name}: blocks the door zone")
        if not any(abs(((rect.angle - angle + 45) % 90) - 45) < 1e-3 for angle in wall_angles):
            errors.append(f"{name}: angle is not parallel/perpendicular to a boundary edge")
        rectangles.append((name, rect))
        if placement.get("type") == "fridge" and solver.fridge_clearance > 0:
            raw_direction = placement.get("openingDirection")
            if not isinstance(raw_direction, list) or len(raw_direction) != 2:
                errors.append(f"{name}: missing openingDirection")
            else:
                direction = tuple(map(float, raw_direction))
                protected_center = add(rect.center, mul(direction, (rect.size[1] + solver.fridge_clearance) / 2))
                protected = OrientedRect(protected_center, (rect.size[0], solver.fridge_clearance), rect.angle)
                if not polygon_inside_room(protected.vertices, solver.room):
                    errors.append(f"{name}: opening clearance outside boundary")
                if convex_polygons_overlap(protected.vertices, solver.door_zone.vertices):
                    errors.append(f"{name}: opening clearance blocks the door zone")
                protected_zones.append((name, protected))

    for index, (name_a, rect_a) in enumerate(rectangles):
        for name_b, rect_b in rectangles[index + 1 :]:
            if convex_polygons_overlap(rect_a.vertices, rect_b.vertices):
                errors.append(f"{name_a} overlaps {name_b}")
    for owner, protected in protected_zones:
        for other_name, other in rectangles:
            if owner != other_name and convex_polygons_overlap(protected.vertices, other.vertices):
                errors.append(f"{other_name} blocks {owner}'s opening edge")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a layout result")
    parser.add_argument("input", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    result = json.loads(args.result.read_text(encoding="utf-8"))
    errors = validate(data, result)
    if errors:
        print("INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
