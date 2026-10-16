import pytest

from app.tools import PlanItem, build_schedule, schedule_plan


def items(*spec):
    return [PlanItem(id=i, title=t, hours=h, depends_on=d) for i, t, h, d in spec]


def test_dependencies_come_first():
    rows = build_schedule(items((1, "B", 1, [2]), (2, "A", 1, [])), 2, "2026-10-19")
    assert [r["id"] for r in rows] == [2, 1]


def test_packs_hours_per_day_and_skips_weekend():
    # 2026-10-23 is a Friday: 3h + 3h at 2h/day -> Fri, Mon, Tue
    rows = build_schedule(items((1, "A", 3, []), (2, "B", 3, [1])), 2, "2026-10-23")
    assert rows[0] == {"id": 1, "title": "A", "hours": 3, "start": "2026-10-23", "end": "2026-10-26"}
    assert rows[1]["start"] == "2026-10-26" and rows[1]["end"] == "2026-10-27"


def test_weekends_allowed():
    rows = build_schedule(items((1, "A", 4, [])), 2, "2026-10-24", weekends_off=False)
    assert rows[0]["start"] == "2026-10-24" and rows[0]["end"] == "2026-10-25"


def test_cycle_and_unknown_ids_raise():
    with pytest.raises(ValueError, match="cycle"):
        build_schedule(items((1, "A", 1, [2]), (2, "B", 1, [1])), 2, "2026-10-19")
    with pytest.raises(ValueError, match="unknown"):
        build_schedule(items((1, "A", 1, [9])), 2, "2026-10-19")


def test_tool_returns_markdown_table_and_friendly_errors():
    out = schedule_plan.invoke({
        "items": [{"id": 1, "title": "Write list", "hours": 1}],
        "hours_per_day": 2, "start_date": "2026-10-19",
    })
    assert "| 1 | Write list | 1 | 2026-10-19 | 2026-10-19 |" in out
    bad = schedule_plan.invoke({
        "items": [{"id": 1, "title": "A", "hours": 1, "depends_on": [1]}], "start_date": "2026-10-19",
    })
    assert bad.startswith("Error:")
