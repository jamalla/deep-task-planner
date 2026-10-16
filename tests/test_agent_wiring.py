"""Runs the real deep agent graph with a scripted fake model (no OpenAI calls).

The fake model: 1) writes todos, 2) delegates to plan-reviewer,
3) (as the reviewer) answers, 4) calls schedule_plan, 5) final reply.
"""

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.agent import build_agent, run_chat


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def call(name, args, i):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}])


def test_deep_agent_plans_delegates_and_schedules():
    script = iter([
        call("write_todos", {"todos": [{"content": "Draft plan", "status": "in_progress"},
                                       {"content": "Review + schedule", "status": "pending"}]}, 1),
        call("task", {"subagent_type": "plan-reviewer", "description": "Review: 1. Buy flour (1h)"}, 2),
        AIMessage(content="Looks good"),  # the reviewer sub-agent's answer
        call("schedule_plan", {"items": [{"id": 1, "title": "Buy flour", "hours": 1}],
                               "start_date": "2026-10-19"}, 3),
        AIMessage(content="## Goal\nBake bread\n## Schedule\n| 1 | Buy flour |"),
    ])
    agent = build_agent(model=ScriptedModel(messages=script))
    out = run_chat([{"role": "user", "content": "Bake bread this week"}], agent=agent)

    assert out["reply"].startswith("## Goal")
    assert {"write_todos", "task", "schedule_plan"} <= set(out["tools_used"])
    assert [t["content"] for t in out["todos"]] == ["Draft plan", "Review + schedule"]
