# Deep Task Planner

A **LangChain deep agent** that takes a task from a simple chat and breaks it
into smart, scheduled action items. It runs on **AWS Lambda**, and one Function
URL serves both the chat page and the API.

```
Browser chat ──POST /api/chat──▶ Lambda (handler.py) ──▶ deep agent (agent.py) ──▶ OpenAI
   ▲  history kept in localStorage        │ access-code check            │
   └──────────── GET / (chat page) ───────┘                              ├─ write_todos   (plans its own work)
                                                                         ├─ task → plan-reviewer sub-agent
                                                                         └─ schedule_plan (tools.py)
```

## What the agent does

1. Understands the goal and states its assumptions.
2. Plans its own work with `write_todos` (once; the app marks the todos completed).
3. Drafts 3–6 phases of verb-first action items. Each item has an effort estimate, a priority (Must/Should/Could) and its dependencies.
4. Asks the **plan-reviewer** sub-agent to critique the draft, then applies the fixes.
5. Turns the estimates into real dates with `schedule_plan`, using deterministic Python rather than LLM math. The app pastes the table into the reply.
6. Replies with the Goal, Assumptions, Plan, Schedule, "Do this first (next 15 minutes)" and suggested tweaks.

Follow-ups such as "make it 1 month" or "I only have weekends" revise the existing plan.

## Project layout

| Path | Purpose |
|---|---|
| `app/agent.py` | `create_deep_agent` setup: prompts, the `plan-reviewer` sub-agent, `TodoListMiddleware`, `{{SCHEDULE}}` fill-in and `TimingCallback` |
| `app/tools.py` | `schedule_plan` (dependency-aware, hours/day, `work_days` such as Mon-Fri or Sat,Sun); `get_today` is kept but no longer a tool |
| `app/handler.py` | Lambda routes (`GET /`, `GET /health`, `POST /api/chat`), access code, validation |
| `app/static/index.html` | Chat UI (no external libraries) |
| `tests/` | 19 pytest tests, including the real deep-agent graph driven by a scripted fake model |
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
| `OPENAI_REASONING_EFFORT` | Default `low` (gpt-5/o models only). `minimal` is faster. Keeps a multi-call deep agent fast. |
| `OPENAI_REVIEWER_MODEL` | Model for the plan-reviewer sub-agent. Default `gpt-4.1-mini` (fast, no reasoning). `same` reuses `OPENAI_MODEL`. |
| `PLANNER_TIMEZONE` | Timezone for "today" in the prompt. Default `UTC`. |

## Speed (Final Lab)

A deep agent's LLM calls run one after another, and most of the time goes into the tokens each call *writes*. Three changes cut it down:

1. **`{{SCHEDULE}}` placeholder.** The model writes `{{SCHEDULE}}` and `run_chat` pastes the exact `schedule_plan` table in, so the longest reply no longer re-types the table (and the dates can't drift).
2. **Two fewer round trips.** Today's date goes into the prompt instead of a `get_today` call, and todos are marked completed in code instead of a final `write_todos` call.
3. **Fast reviewer.** The plan-reviewer sub-agent runs on `gpt-4.1-mini`, receives a compact one-line-per-item draft, and answers with at most 5 bullets.

Every response includes `timings` (total seconds, LLM calls, output tokens, per-step durations), and the same summary is logged to CloudWatch as a `chat_timing` JSON line.

## Notes

- Chat memory is stateless on the server. The browser sends the whole history each turn, so it works with any number of Lambda containers.
- deepagents' file tools use the in-memory `StateBackend`. They are virtual files inside the agent's state, and `execute` is disabled, so the agent can't touch the Lambda filesystem or run shell commands.
