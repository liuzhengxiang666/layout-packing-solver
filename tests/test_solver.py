from __future__ import annotations

import json
import unittest
from pathlib import Path

from layout_solver.geometry import OrientedRect, convex_polygons_overlap, polygon_inside_room
from layout_solver.solver import LayoutSolver
from validate import validate


ROOT = Path(__file__).resolve().parents[1]


class GeometryTests(unittest.TestCase):
    def test_touching_rectangles_do_not_overlap(self) -> None:
        left = OrientedRect((0, 0), (2, 2), 0)
        right = OrientedRect((2, 0), (2, 2), 0)
        self.assertFalse(convex_polygons_overlap(left.vertices, right.vertices))

    def test_concave_room_rejects_rectangle_across_notch(self) -> None:
        room = ((0, 0), (5, 0), (5, 5), (3, 5), (3, 2), (2, 2), (2, 5), (0, 5))
        across_notch = OrientedRect((2.5, 3.0), (2, 1), 0)
        self.assertFalse(polygon_inside_room(across_notch.vertices, room))


class ExampleTests(unittest.TestCase):
    def test_all_supplied_examples_are_feasible_and_valid(self) -> None:
        for number in range(1, 5):
            with self.subTest(example=number):
                path = ROOT / "examples" / f"example{number}.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                result = LayoutSolver(data).solve()
                self.assertTrue(result["feasible"])
                self.assertEqual(len(result["placements"]), len(data["algoToPlace"]))
                self.assertTrue(all(p["againstWall"] for p in result["placements"]))
                self.assertEqual(validate(data, result), [])


if __name__ == "__main__":
    unittest.main()

