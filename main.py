#!/usr/bin/env python3
"""Command-line entry point for the layout solver."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from layout_solver import LayoutSolver
from layout_solver.svg import render_svg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Place rectangular equipment inside a polygonal room.")
    parser.add_argument("input", type=Path, help="input JSON path")
    parser.add_argument("-o", "--output", type=Path, help="write result JSON to this path")
    parser.add_argument("--svg", type=Path, help="write an SVG preview to this path")
    parser.add_argument("--grid-step", type=float, default=100.0, help="interior search grid in mm")
    parser.add_argument("--wall-step", type=float, default=100.0, help="wall sliding search step in mm")
    parser.add_argument("--fridge-clearance", type=float, default=10.0, help="fridge door no-placement strip in mm")
    parser.add_argument("--outward-door-depth", type=float, default=100.0, help="access strip for outward doors in mm")
    parser.add_argument("--node-limit", type=int, default=500_000, help="maximum backtracking nodes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = None
    try:
        with args.input.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        solver = LayoutSolver(
            data,
            grid_step=args.grid_step,
            wall_step=args.wall_step,
            fridge_clearance=args.fridge_clearance,
            outward_door_depth=args.outward_door_depth,
            node_limit=args.node_limit,
        )
        result = solver.solve()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        result = {"feasible": False, "placements": [], "error": str(error)}

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    if args.svg and data is not None:
        args.svg.parent.mkdir(parents=True, exist_ok=True)
        args.svg.write_text(render_svg(data, result), encoding="utf-8")
    return 0 if result.get("feasible") else 2


if __name__ == "__main__":
    raise SystemExit(main())
