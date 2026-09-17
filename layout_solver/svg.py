"""Generate a simple SVG preview without plotting dependencies."""

from __future__ import annotations

from html import escape
from typing import Any

from .geometry import OrientedRect, bounds, rectangle_vertices


COLORS = {
    "fridge": "#ef8354",
    "shelf": "#2d9cdb",
    "overShelf": "#6fcf97",
    "iceMaker": "#bb6bd9",
}


def render_svg(data: dict[str, Any], result: dict[str, Any], width: int = 900, height: int = 700) -> str:
    boundary = [tuple(map(float, point)) for point in data["boundary"]]
    if boundary[0] == boundary[-1]:
        boundary.pop()
    min_x, min_y, max_x, max_y = bounds(boundary)
    pad = max(max_x - min_x, max_y - min_y) * 0.05 or 1
    view_x, view_y = min_x - pad, min_y - pad
    view_w, view_h = max_x - min_x + 2 * pad, max_y - min_y + 2 * pad

    def points(values: list[tuple[float, float]] | tuple[tuple[float, float], ...]) -> str:
        return " ".join(f"{x:.3f},{y:.3f}" for x, y in values)

    elements = [
        f'<polygon points="{points(boundary)}" fill="#f8fafc" stroke="#172033" stroke-width="12"/>',
    ]
    door = [tuple(map(float, point)) for point in data["door"]]
    elements.append(f'<line x1="{door[0][0]}" y1="{door[0][1]}" x2="{door[1][0]}" y2="{door[1][1]}" stroke="#e11d48" stroke-width="24"/>')
    for placement in result.get("placements", []):
        rect = OrientedRect(tuple(placement["center"]), tuple(placement["size"]), placement["angle"])
        fill = COLORS.get(placement["type"], "#f2c94c")
        elements.append(
            f'<polygon points="{points(rect.vertices)}" fill="{fill}" fill-opacity="0.72" '
            f'stroke="#172033" stroke-width="8"><title>{escape(placement["name"])}</title></polygon>'
        )
        x, y = placement["center"]
        font_size = max(view_w, view_h) / 55
        elements.append(
            f'<text x="{x}" y="{y}" font-size="{font_size:.2f}" text-anchor="middle" '
            f'dominant-baseline="middle" fill="#111827" transform="translate(0 {2 * y}) scale(1 -1)">'
            f'{escape(placement["name"])}</text>'
        )
    status = "FEASIBLE" if result.get("feasible") else "INFEASIBLE / NOT FOUND"
    elements.append(
        f'<text x="{view_x + pad * .25}" y="{view_y + pad * .8}" font-size="{max(view_w, view_h) / 40:.2f}" '
        f'fill="#111827">{status}</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="{view_x} {view_y} {view_w} {view_h}">'
        f'<g transform="translate(0 {2 * view_y + view_h}) scale(1 -1)">{"".join(elements[:-1])}</g>{elements[-1]}</svg>'
    )
