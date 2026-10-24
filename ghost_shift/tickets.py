"""
ghost_shift/tickets.py
----------------------
The "manager": a ticket ledger that tracks every program failure.

When generated code crashes, a ticket is opened and assigned to the engineer
(the coder). The ledger records the error, how many fix attempts were made, and
how it ended. The director shows tickets on screen, the tmux status bar shows
the running totals, and programs that could not be fixed are remembered so they
are never replayed.

Statuses
    open       the coder is working on it (background)
    fix_ready  a verified fix is waiting to be shown on screen
    fixed      fixed on screen
    cnr        could not reproduce (it ran fine live)
    unfixed    the coder gave up ("won't fix")
    backlog    crashed live with no prepared fix

    python -m ghost_shift.tickets            # summary
    python -m ghost_shift.tickets --board    # compact board (used by the strip)
"""

import argparse
import contextlib
import fcntl
import json
import os
import random
import textwrap
import time
from pathlib import Path

DATA_DIR = Path("~/.local/share/ghost-shift").expanduser()
LEDGER = DATA_DIR / "tickets.json"
LOCK = DATA_DIR / "tickets.lock"
TICKET_DIR = DATA_DIR / "tickets"

MANAGER_NAME = "Sarah Vance"
MANAGER_ROLE = "IT Ops Lead"
ENGINEER = "Ed"
MAX_TICKETS = 200

ASSIGN_NOTES = [
    "Per my last email, this needs to be fixed before the steering meeting.",
    "No pressure, but leadership is asking about this one.",
    "Could you take a look when you get a moment? (Today.)",
    "I trust this will not happen again.",
    "Please keep me in the loop on progress.",
    "Circling back: this is blocking the Friday demo.",
    "Not sure how this passed review, but let us fix it quickly.",
    "I will need a root cause for the post-mortem.",
    "Marking this P2 so it gets attention. Thanks so much!",
    "Please add notes to the ticket as you go.",
]
ESCALATE_NOTES = [
    "Escalating to the architecture board. Please document what you tried.",
    "This has now exceeded the agreed fix window. Let us discuss.",
    "Parking this for the next sprint. Please write up the findings.",
    "Closing as won't fix. We will revisit after the migration.",
]

CLOSED = ("fixed", "cnr")
OPEN = ("open", "fix_ready", "backlog")

DISPLAY_STATUS = {
    "open": "ASSIGNED", "fix_ready": "ASSIGNED", "backlog": "BACKLOG",
    "fixed": "CLOSED (FIXED)", "cnr": "CLOSED (CANNOT REPRODUCE)",
    "unfixed": "CLOSED (WON'T FIX)",
}


def display_status(t: dict) -> str:
    """Status as people would read it on a ticket (never reveals 'fix_ready')."""
    return DISPLAY_STATUS.get(t["status"], t["status"].upper())


@contextlib.contextmanager
def _locked():
    """The worker and the director are separate processes; serialise access."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _load() -> dict:
    try:
        data = json.loads(LEDGER.read_text())
        data.setdefault("next", 4001)
        data.setdefault("tickets", [])
        data.setdefault("bad", [])
        return data
    except Exception:
        return {"next": 4001, "tickets": [], "bad": []}


def _save(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, LEDGER)


def open_ticket(program: str, slug: str, error: str, traceback: str = "",
                source: str = "worker") -> dict:
    """Open a ticket for a crashing program and assign it to the engineer."""
    with _locked():
        data = _load()
        ticket = {
            "id": data["next"], "program": program, "slug": slug, "error": error,
            "traceback": traceback, "status": "open", "attempts": 0, "source": source,
            "priority": random.choice(["P2", "P2", "P3"]),
            "note": random.choice(ASSIGN_NOTES),
            "opened": time.time(), "closed": None,
        }
        data["next"] += 1
        data["tickets"] = (data["tickets"] + [ticket])[-MAX_TICKETS:]
        _save(data)
    return ticket


def get_ticket(ticket_id: int):
    with _locked():
        for t in _load()["tickets"]:
            if t["id"] == ticket_id:
                return t
    return None


def update_ticket(ticket_id: int, **fields) -> None:
    with _locked():
        data = _load()
        for t in data["tickets"]:
            if t["id"] == ticket_id:
                t.update(fields)
        _save(data)


def close_ticket(ticket_id: int, status: str, attempts: int = None) -> None:
    fields = {"status": status}
    if status in CLOSED + ("unfixed", "backlog"):
        fields["closed"] = time.time()
    if attempts is not None:
        fields["attempts"] = attempts
    if status in ("unfixed", "backlog"):
        fields["note"] = random.choice(ESCALATE_NOTES)
    update_ticket(ticket_id, **fields)


def mark_bad(program: str) -> None:
    """Remember a program that must not be replayed."""
    with _locked():
        data = _load()
        if program not in data["bad"]:
            data["bad"] = (data["bad"] + [program])[-MAX_TICKETS:]
        _save(data)


def bad_programs() -> set:
    with _locked():
        return set(_load()["bad"])


def stats() -> dict:
    with _locked():
        tickets = _load()["tickets"]
    count = lambda group: sum(1 for t in tickets if t["status"] in group)
    fixed, wontfix = count(CLOSED), count(("unfixed",))
    return {"total": len(tickets), "open": count(OPEN), "fixed": fixed,
            "wontfix": wontfix,
            "fix_rate": round(100 * fixed / (fixed + wontfix)) if fixed + wontfix else None}


def status_line() -> str:
    s = stats()
    return f"TICKETS open:{s['open']} fixed:{s['fixed']} wontfix:{s['wontfix']}"


def render_ticket(t: dict, width: int = 64) -> str:
    """ASCII ticket, as the manager would file it."""
    inner = width - 4
    opened = time.strftime("%H:%M", time.localtime(t["opened"]))
    rule = "+" + "-" * (width - 2) + "+"

    def row(text="") -> str:
        return "| " + text.ljust(inner) + " |"

    def wrapped(label: str, text: str):
        lines = textwrap.wrap(text, inner - len(label)) or [""]
        out = [row(label + lines[0])]
        out += [row(" " * len(label) + ln) for ln in lines[1:]]
        return out

    left = f"TICKET #{t['id']}"
    right = f"PRIORITY: {t['priority']}"
    rows = [rule, row(left + right.rjust(inner - len(left))), rule]
    rows += wrapped("Reported by : ", f"{MANAGER_NAME} ({MANAGER_ROLE})")
    rows += wrapped("Assigned to : ", ENGINEER)
    rows += wrapped("Program     : ", t["program"])
    rows += wrapped("Opened      : ", opened)
    rows += wrapped("Status      : ", display_status(t))
    rows.append(row())
    rows += wrapped("", t["error"] or "Unknown error")
    rows.append(row())
    rows += wrapped("Note: ", t["note"])
    rows.append(rule)
    return "\n".join(rows) + "\n"


def write_ticket_file(t: dict) -> Path:
    TICKET_DIR.mkdir(parents=True, exist_ok=True)
    path = TICKET_DIR / f"{t['id']}.txt"
    path.write_text(render_ticket(t))
    return path


def board(limit: int = 8, width: int = 100) -> str:
    """Compact board for the bottom strip / `watch`."""
    s = stats()
    with _locked():
        recent = _load()["tickets"][-limit:][::-1]
    rate = f"{s['fix_rate']}%" if s["fix_rate"] is not None else "n/a"
    lines = [f" TICKET BOARD   open: {s['open']}   fixed: {s['fixed']}   "
             f"won't fix: {s['wontfix']}   fix rate: {rate}", ""]
    for t in recent:
        line = f" #{t['id']}  {display_status(t).split()[0]:<9} {t['slug'][:14]:<14} {t['error']}"
        lines.append(line[:width])
    if not recent:
        lines.append(" no tickets yet - everything is working (for now)")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", action="store_true", help="print the compact board")
    args = parser.parse_args()
    if args.board:
        print(board())
        return
    print(status_line())
    s = stats()
    print(f"total tickets: {s['total']}   fix rate: "
          f"{s['fix_rate'] if s['fix_rate'] is not None else 'n/a'}%")
    print(board(limit=12))


if __name__ == "__main__":
    main()
