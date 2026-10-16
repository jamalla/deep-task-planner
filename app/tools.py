"""Deterministic tools the deep agent can call.

LLMs are bad at calendar arithmetic, so dates and scheduling are done in
plain Python. The agent decides *what* to do, and these tools work out *when*.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from langchain.tools import tool
from pydantic import BaseModel, Field


@tool
def get_today(timezone_name: str = "UTC") -> str:
    """Return today's date and weekday in an IANA timezone (e.g. 'Asia/Singapore')."""
    try:
        now = datetime.now(ZoneInfo(timezone_name))
    except Exception:  # noqa: BLE001 - unknown timezone falls back to UTC
        now = datetime.now(ZoneInfo("UTC"))
        timezone_name = "UTC"
    return f"{now:%Y-%m-%d} ({now:%A}), timezone {timezone_name}"


class PlanItem(BaseModel):
    id: int = Field(description="Unique number of the action item, e.g. 1, 2, 3")
    title: str = Field(description="Short verb-first action, e.g. 'Draft menu of 10 items'")
    hours: float = Field(gt=0, le=40, description="Estimated effort in hours")
    depends_on: list[int] = Field(default_factory=list, description="ids that must finish first")


def _order(items: list[PlanItem]) -> list[PlanItem]:
    """Topological sort (dependencies first, then by id). Raises on cycles."""
    by_id = {i.id: i for i in items}
    unknown = {d for i in items for d in i.depends_on if d not in by_id}
    if unknown:
        raise ValueError(f"depends_on refers to unknown ids: {sorted(unknown)}")
    done: set[int] = set()
    ordered: list[PlanItem] = []
    remaining = sorted(items, key=lambda i: i.id)
    while remaining:
        ready = [i for i in remaining if set(i.depends_on) <= done]
        if not ready:
            raise ValueError("dependency cycle between ids " + str([i.id for i in remaining]))
        nxt = ready[0]
        ordered.append(nxt)
        done.add(nxt.id)
        remaining.remove(nxt)
    return ordered


def build_schedule(
    items: list[PlanItem],
    hours_per_day: float = 2.0,
    start_date: str | None = None,
    weekends_off: bool = True,
) -> list[dict]:
    """Pack items, in dependency order, into working days of `hours_per_day`."""
    if hours_per_day <= 0:
        raise ValueError("hours_per_day must be > 0")
    day = date.fromisoformat(start_date) if start_date else date.today()

    def skip_weekend(d: date) -> date:
        while weekends_off and d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    day = skip_weekend(day)
    used = 0.0
    out = []
    for item in _order(items):
        left = item.hours
        start = None
        while left > 1e-9:
            if used >= hours_per_day - 1e-9:
                day = skip_weekend(day + timedelta(days=1))
                used = 0.0
            chunk = min(left, hours_per_day - used)
            start = start or day
            used += chunk
            left -= chunk
        out.append(
            {"id": item.id, "title": item.title, "hours": item.hours,
             "start": start.isoformat(), "end": day.isoformat()}
        )
    return out


@tool
def schedule_plan(
    items: list[PlanItem],
    hours_per_day: float = 2.0,
    start_date: str | None = None,
    weekends_off: bool = True,
) -> str:
    """Turn action items with effort estimates into a dated schedule.

    Respects depends_on order, fits `hours_per_day` of work per day, and skips
    weekends unless weekends_off is False. start_date is YYYY-MM-DD (default today).
    Returns a Markdown table plus the finish date.
    """
    try:
        rows = build_schedule(items, hours_per_day, start_date, weekends_off)
    except ValueError as exc:
        return f"Error: {exc}. Fix the items and call schedule_plan again."
    total = sum(r["hours"] for r in rows)
    lines = ["| # | Action | Hours | Start | End |", "|---|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['title']} | {r['hours']:g} | {r['start']} | {r['end']} |" for r in rows]
    finish = max(r["end"] for r in rows) if rows else "-"
    lines.append(f"\nTotal effort: {total:g} h at {hours_per_day:g} h/day -> finishes {finish}")
    return "\n".join(lines)


TOOLS = [get_today, schedule_plan]
