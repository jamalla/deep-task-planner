"""Terminal chat with the real deep agent (same code Lambda runs)."""

import sys
import time

from app.agent import run_chat

BOLD, DIM, GREEN, CYAN, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[36m", "\033[0m"
ICON = {"completed": "✓", "in_progress": "▶", "pending": "○"}


def turn(history: list[dict]) -> None:
    print(f"{DIM}Agent is planning, reviewing and scheduling...{RESET}", flush=True)
    t0 = time.time()
    out = run_chat(history)
    history.append({"role": "assistant", "content": out["reply"]})
    print(f"\n{BOLD}{CYAN}=== Agent reply ==={RESET}\n{out['reply']}\n")
    print(f"{BOLD}Agent's own plan (write_todos):{RESET}")
    for t in out["todos"] or [{"content": "(none)", "status": ""}]:
        print(f"  {ICON.get(t['status'], '-')} {t['content']}")
    print(f"{GREEN}Tools used:{RESET} {', '.join(out['tools_used']) or '-'}")
    print(f"{DIM}Took {time.time() - t0:.1f}s{RESET}\n")


def main() -> None:
    first = " ".join(sys.argv[1:]).strip() or "Launch a small online bakery in 2 months"
    history = [{"role": "user", "content": first}]
    print(f"{BOLD}You:{RESET} {first}")
    turn(history)
    while True:
        try:
            follow = input(f"{BOLD}Follow-up (Enter to quit):{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not follow:
            break
        history.append({"role": "user", "content": follow})
        turn(history)


if __name__ == "__main__":
    main()
