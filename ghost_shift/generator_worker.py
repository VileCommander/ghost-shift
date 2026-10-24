"""
ghost_shift/generator_worker.py
-------------------------------
Background generator that decouples LLM generation time from the live display.

Keeps two queues topped up:
  * library/ready/   validated, ready-to-type Python programs
  * the Maildir      unread work emails, each with a prepared reply

Every program is smoke-tested headlessly. A crashing program gets a ticket from
the manager (tickets.py) and the coder (debugger.py) tries to fix it. If a fix
is found, the buggy original is queued together with a <name>.story.json
sidecar, so the director can show the crash and the on-screen fix. Programs
that cannot be fixed are dropped. Programs are named <slug>_<time>_<id>.py.
"""

import json
import random
import time
import uuid
from pathlib import Path

from ghost_shift import debugger, email_engine, tickets
from ghost_shift.codegen import generate_program, slug
from ghost_shift.config import load_config
from ghost_shift.sandbox import validate_code
from ghost_shift.util import log

READY_DIR = Path("~/.local/share/ghost-shift/library/ready").expanduser()
ARCHIVE_DIR = Path("~/.local/share/ghost-shift/library/archive").expanduser()

STATIC_FALLBACK = (
    "# [SYSTEM RECOVERY INITIALIZED]\n"
    "import time\nimport random\n\n"
    "for cycle in range(30):\n"
    "    print(f'[ DECK TELEMETRY ] Node {cycle:02d}/30 | Load: {random.randint(15, 95)}% [NOMINAL]')\n"
    "    time.sleep(2)\n"
)


def say(msg: str) -> None:
    print(msg, flush=True)
    log(msg)


def ensure_directories():
    """Creates persistent library storage directories if they do not exist."""
    READY_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def _stem(name: str) -> str:
    """Task name from '<slug>_<time>_<id>.py' ('sysmon' for old-style names)."""
    stem = Path(name).stem
    if stem.count("_") >= 2:
        stem = stem.rsplit("_", 2)[0]
        if stem != "gen":
            return stem
    return "sysmon"


def _queue_one(config: dict, cleaned: str, task: str) -> None:
    """Smoke-test one validated program, debug it if needed, and queue it."""
    name = f"{task}_{int(time.time())}_{uuid.uuid4().hex[:6]}.py"
    dbg = config.get("debug", {})

    if dbg.get("enabled", True):
        result = debugger.smoke_test(cleaned, name=name,
                                     wall_timeout=dbg.get("smoke_timeout", 40))
        if not result["ok"]:
            say(f"[!] {name} crashes: {result['error']}")
            ticket = tickets.open_ticket(name, task, result["error"],
                                         result["traceback"], source="worker")
            say(f"[*] ticket #{ticket['id']} opened; the coder is on it")
            story = debugger.debug_program(config, cleaned, name, task, result, ticket)
            if story["status"] == "fixed":
                (READY_DIR / name).write_text(cleaned)
                (READY_DIR / name.replace(".py", ".story.json")).write_text(json.dumps(story))
                tickets.update_ticket(ticket["id"], status="fix_ready",
                                      attempts=story["attempts"])
                say(f"[+] ticket #{ticket['id']}: fix ready after {story['attempts']} attempt(s); queued {name}")
            else:
                tickets.close_ticket(ticket["id"], "unfixed", attempts=story["attempts"])
                tickets.mark_bad(name)
                say(f"[-] ticket #{ticket['id']}: could not fix after {story['attempts']} attempt(s); dropped")
            return

    (READY_DIR / name).write_text(cleaned)
    say(f"[+] Added fresh program to ready queue: {name}")


def fill_ready_queue(config: dict, target_count: int = 3, max_new: int = None):
    """Generate new scripts until the ready queue holds target_count."""
    ensure_directories()
    current_count = len(list(READY_DIR.glob("*.py")))
    if current_count >= target_count:
        return

    needed = target_count - current_count
    if max_new is not None:
        needed = min(needed, max_new)
    say(f"[*] Ready queue count: {current_count}/{target_count}. Generating {needed} new script(s)...")

    for _ in range(needed):
        try:
            code = generate_program(config)
            task = slug()
            if code:
                # Security double-check
                is_safe, _, cleaned = validate_code(code)
                if is_safe and len(cleaned.strip()) >= 20:
                    _queue_one(config, cleaned, task)
                else:
                    say("[-] Generated program failed sandbox verification.")
            else:
                say("[-] Generator returned None.")
        except Exception as e:
            say(f"[-] Generation error: {e}")
        time.sleep(2)


def pop_ready_item(config: dict) -> dict:
    """
    Take the next program: {"code", "source", "stem", "story", "name"}. A queued program
    is archived (the FIXED version if it came with a story). With an empty queue
    an archived program is replayed, skipping any the manager marked as bad.
    """
    ensure_directories()
    ready = sorted(READY_DIR.glob("*.py"))

    if ready:
        target = ready[0]
        code = target.read_text()
        story = None
        sidecar = target.with_suffix(".story.json")
        if sidecar.exists():
            try:
                story = json.loads(sidecar.read_text())
            except Exception:
                story = None
            sidecar.unlink(missing_ok=True)
        archive_code = (story or {}).get("fixed_code") or code
        (ARCHIVE_DIR / target.name).write_text(archive_code)
        target.unlink()
        return {"code": code, "source": "llm_queued", "stem": _stem(target.name),
                "story": story, "name": target.name}

    bad = tickets.bad_programs()
    archived = [p for p in ARCHIVE_DIR.glob("*.py") if p.name not in bad]
    if archived:
        pick = random.choice(archived)
        return {"code": pick.read_text(), "source": "archived",
                "stem": _stem(pick.name), "story": None, "name": pick.name}

    return {"code": STATIC_FALLBACK, "source": "static", "stem": "sysmon", "story": None,
            "name": ""}


def pop_ready_named(config: dict) -> tuple[str, str, str]:
    """Compatibility wrapper: (code, source, stem)."""
    item = pop_ready_item(config)
    return item["code"], item["source"], item["stem"]


def pop_ready_program(config: dict) -> tuple[str, str]:
    """Compatibility wrapper: (code, source)."""
    item = pop_ready_item(config)
    return item["code"], item["source"]


def run_worker_loop():
    """Run continuously as a background service or standalone worker."""
    config = load_config()
    mail_cfg = config.get("mail", {})
    mail_on = mail_cfg.get("enabled", True)
    say("[*] Starting Ghost Shift background generator worker...")

    if mail_on:
        try:
            email_engine.seed_inbox_if_empty()
        except Exception as e:
            say(f"[-] Could not prepare the mailbox: {e}")

    while True:
        try:
            fill_ready_queue(config, target_count=3, max_new=1)
        except Exception as e:
            say(f"[-] Worker error: {e}")

        if mail_on:
            try:
                email_engine.fill_mail_queue(
                    config, target_unread=mail_cfg.get("target_unread", 3), max_new=1)
                email_engine.prune(max_read=mail_cfg.get("max_read", 30))
            except Exception as e:
                say(f"[-] Mail worker error: {e}")

        time.sleep(10)


if __name__ == "__main__":
    run_worker_loop()
