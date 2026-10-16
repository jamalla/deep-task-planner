# Deep Task Planner

A **LangChain deep agent** that takes a task from a simple chat and breaks it
into smart, scheduled action items. It runs on **AWS Lambda**, and one Function
URL serves both the chat page and the API.

```
Browser chat ──POST /api/chat──▶ Lambda (handler.py) ──▶ deep agent (agent.py) ──▶ OpenAI
   ▲  history kept in localStorage        │ access-code check            │
   └──────────── GET / (chat page) ───────┘                              ├─ write_todos   (plans its own work)
                                                                         ├─ task → plan-reviewer sub-agent
                                                                         └─ get_today, schedule_plan (tools.py)
```

## What the agent does

1. Understands the goal and states its assumptions.
2. Plans its own work with `write_todos`.
3. Drafts 3–6 phases of verb-first action items. Each item has an effort estimate, a priority (Must/Should/Could) and its dependencies.
4. Asks the **plan-reviewer** sub-agent to critique the draft, then applies the fixes.
5. Turns the estimates into real dates with `schedule_plan`, using deterministic Python rather than LLM math.
6. Replies with the Goal, Assumptions, Plan, Schedule, "Do this first (next 15 minutes)" and suggested tweaks.

Follow-ups such as "make it 1 month" or "I only have weekends" revise the existing plan.

## Project layout

| Path | Purpose |
|---|---|
| `app/agent.py` | `create_deep_agent` setup: prompts, the `plan-reviewer` sub-agent and `TodoListMiddleware` |
| `app/tools.py` | `get_today` and `schedule_plan` (dependency-aware, hours/day, skips weekends) |
| `app/handler.py` | Lambda routes (`GET /`, `GET /health`, `POST /api/chat`), access code, validation |
| `app/static/index.html` | Chat UI (no external libraries) |
| `tests/` | 15 pytest tests, including the real deep-agent graph driven by a scripted fake model |
| `scripts/live_demo.sh` | Live demo with your real key in a terminal (for example AWS CloudShell) |
| `deploy.sh` | Builds one zip and deploys Lambda + Function URL (us-east-1) |

## Deploy (AWS CloudShell, us-east-1)

```bash
git clone https://github.com/jamalla/deep-task-planner.git && cd deep-task-planner
bash deploy.sh            # asks for your OpenAI key once; prints chat URL + access code
```

Run it again any time to update the code; it keeps your key and access code. `bash deploy.sh --set-key` replaces the key.

## Run the tests

```bash
pip install -r requirements.txt pytest
python -m pytest -q
```

## Live demo (real model, terminal)

```bash
bash scripts/live_demo.sh "Prepare for the AWS Solutions Architect exam, 1 hour a day"
```

The script asks for your OpenAI key at a hidden prompt and never saves it.

## Configuration (Lambda environment)

| Variable | Purpose |
|---|---|
| `ACCESS_CODE` | Required header `x-access-code` for `/api/chat`. The chat page asks for it once. |
| `OPENAI_API_KEY` | Your OpenAI key. `deploy.sh` asks for it at a hidden prompt (`OPENAI_KEY_PARAM`, an SSM SecureString name, is also supported). |
| `OPENAI_MODEL` | Default `gpt-5-mini` |
| `OPENAI_REASONING_EFFORT` | Default `low` (gpt-5/o models only). Keeps a multi-call deep agent fast. |

## Notes

- Chat memory is stateless on the server. The browser sends the whole history each turn, so it works with any number of Lambda containers.
- deepagents' file tools use the in-memory `StateBackend`. They are virtual files inside the agent's state, and `execute` is disabled, so the agent can't touch the Lambda filesystem or run shell commands.
