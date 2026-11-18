"""Company logo as an inline data URI, with a monogram fallback."""

from __future__ import annotations

import base64
import html
import io

from aladeen.dataflows.http import Http


def logo_data_uri(http: Http, url: str | None, size: int = 160) -> str | None:
    if not url:
        return None
    try:
        raw = http.get(url, binary=True)
        from PIL import Image

        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        img.thumbnail((size, size))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def monogram_svg(name: str, color: str = "#1f4e9c") -> str:
    words = [w for w in name.replace("Ltd", "").replace("Limited", "").split() if w[:1].isalnum()]
    letters = "".join(w[0] for w in words[:2]).upper() or "?"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
        f'<rect width="96" height="96" rx="18" fill="{color}"/>'
        f'<text x="48" y="60" font-family="Arial,sans-serif" font-size="38" font-weight="700" '
        f'fill="#fff" text-anchor="middle">{html.escape(letters)}</text></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
