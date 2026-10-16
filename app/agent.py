"""The deep agent: a Task Breakdown Coach built with LangChain `deepagents`.

How it works:
  main agent  --write_todos-->  plans its own work (TodoListMiddleware)
              --task()------->  'plan-reviewer' sub-agent critiques the draft
              --schedule_plan-> real dates from effort estimates (tools.py)
"""

from __future__ import annotations

import os

from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_openai import ChatOpenAI

from app.tools import TOOLS

MAIN_PROMPT = """You are "Task Breakdown Coach", an expert project planner.
The user gives you a task or goal in a chat. Your job: turn it into a smart,
realistic breakdown of small action items they can start on immediately.

Method (follow it every time you produce or revise a plan):
1. Understand the goal. If one or two facts are essential and missing
   (e.g. deadline, budget, hours available), make a sensible assumption and
   state it. Only ask questions instead of planning if the request is too vague
   to plan at all (e.g. "help me"). Ask at most 2 short questions.
2. Use write_todos to plan your own work for this request.
3. Draft the breakdown:
   - 3-6 phases, in a logical order.
   - Each action item: starts with a verb, is specific and checkable,
     takes at most ~1 day (split anything bigger), and has: effort in hours,
     priority (Must / Should / Could), and depends_on (ids) where relevant.
   - Number items 1..N across all phases.
4. Delegate a quality check: call the task tool with subagent 'plan-reviewer'
   EXACTLY ONCE per user message, passing the goal, assumptions and the full
   draft. Apply its fixes yourself; do not send the plan back for re-review.
5. Call get_today, then call schedule_plan with all items and the user's
   available hours per day (assume 2 h/day on weekdays if unknown).
6. Reply in Markdown using exactly these sections:
   ## Goal
   ## Assumptions
   ## Plan  (one '### Phase' heading per phase, items as a numbered list:
             **#. Action** — effort h · Priority · depends on #x)
   ## Schedule  (the table from schedule_plan)
   ## Do this first (next 15 minutes)
   ## Want changes?  (one line offering 2-3 concrete tweaks)

For follow-up messages ("make it 1 month", "I only have weekends"),
revise the existing plan instead of starting over, and repeat steps 4-6.
Before your final reply, mark all of your todos as completed with write_todos.
Keep the tone encouraging and concise. Never invent facts about the user.
"""

REVIEWER_PROMPT = """You are a strict senior project manager reviewing a task
breakdown. Check it against this list and return ONLY a short bullet list of
concrete fixes (or 'Looks good' if none):
- Is every item specific, verb-first and checkable (clear definition of done)?
- Is any item bigger than ~1 day? Split it.
- Missing steps (research, approvals, testing, launch, follow-up)?
- Wrong order or missing dependencies?
- Unrealistic effort estimates?
- Are the Must items really the minimum needed to reach the goal?
"""

SUBAGENTS = [
    {
        "name": "plan-reviewer",
        "description": "Reviews a draft task breakdown and returns concrete fixes "
        "(missing steps, items too big, wrong order, bad estimates).",
        "system_prompt": REVIEWER_PROMPT,
    }
]

_agent = None


def build_agent(model=None):
    """Create the deep agent. `model` can be injected for tests."""
    if model is None:
        name = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
        extra = {}
        if name.startswith(("gpt-5", "o")):
            # Reasoning models "think" before every call, and a deep agent makes
            # many calls. Low effort cut our live demo from minutes to seconds.
            extra["reasoning_effort"] = os.environ.get("OPENAI_REASONING_EFFORT", "low")
        model = ChatOpenAI(model=name, timeout=120, max_retries=2, **extra)
    return create_deep_agent(
        model=model,
        tools=TOOLS,
        system_prompt=MAIN_PROMPT,
        subagents=SUBAGENTS,
        # deepagents >= 0.7 no longer adds the planner by default: this middleware
        # gives the agent the write_todos tool and keeps `todos` in its state.
        middleware=[TodoListMiddleware()],
        name="task-breakdown-coach",
    )


def get_agent():
    """Build once per Lambda container and reuse across requests (warm starts)."""
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def run_chat(messages: list[dict], agent=None) -> dict:
    """Run one chat turn. `messages` is the full history [{role, content}, ...]."""
    agent = agent or get_agent()
    state = agent.invoke({"messages": messages}, config={"recursion_limit": 80})
    last = state["messages"][-1]
    reply = str(last.text)  # .text joins text blocks (works for str or list content)
    todos = [
        {"content": t.get("content", ""), "status": t.get("status", "")}
        for t in state.get("todos", []) or []
    ]
    used = [
        call["name"]
        for msg in state["messages"]
        for call in (getattr(msg, "tool_calls", None) or [])
    ]
    return {"reply": reply, "todos": todos, "tools_used": used}
