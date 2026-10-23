"""
ghost_shift/generator_worker.py
-------------------------------
Background generator that decouples LLM generation time from the live display.

Keeps two queues topped up:
  * library/ready/   validated, ready-to-type Python programs
  * the Maildir      unread work emails, each with a prepared reply
Programs are saved as <slug>_<time>_<id>.py so file names stay meaningful.
"""

import random
import time
import uuid
from pathlib import Path

from ghost_shift import email_engine
from ghost_shift.codegen import generate_program, slug
from ghost_shift.config import load_config
from ghost_shift.sandbox import validate_code
from ghost_shift.util import log

READY_DIR = Path("~/.local/share/ghost-shift/library/ready").expanduser()
ARCHIVE_DIR = Path("~/.local/share/ghost-shift/library/archive").expanduser()


def say(msg: str) -> None:
    print(msg, flush=True)
    log(msg)


def ensure_directories():
    """Creates persistent library storage directories if they do not exist."""
    READY_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


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
            if code:
                # Security double-check
                is_safe, _, cleaned = validate_code(code)
                if is_safe and len(cleaned.strip()) >= 20:
                    filename = f"{slug()}_{int(time.time())}_{uuid.uuid4().hex[:6]}.py"
                    (READY_DIR / filename).write_text(cleaned)
                    say(f"[+] Added fresh program to ready queue: {filename}")
                else:
                    say("[-] Generated program failed sandbox verification.")
            else:
                say("[-] Generator returned None.")
        except Exception as e:
            say(f"[-] Generation error: {e}")
        time.sleep(2)


def pop_ready_program(config: dict) -> tuple[str, str]:
    """
    Pull the next ready program from library/ready/, keep a copy in
    library/archive/, and return (code_string, source_type).
    """
    ensure_directories()
    ready_files = sorted(READY_DIR.glob("*.py"))

    if ready_files:
        target = ready_files[0]
        code = target.read_text()
        (ARCHIVE_DIR / target.name).write_text(code)
        target.unlink()
        return code, "llm_queued"

    # Queue empty: replay from the archive
    archived = list(ARCHIVE_DIR.glob("*.py"))
    if archived:
        return random.choice(archived).read_text(), "archived"

    # Nothing anywhere: static fallback
    fallback = (
        "# [SYSTEM RECOVERY INITIALIZED]\n"
        "import time\nimport random\n\n"
        "for cycle in range(30):\n"
        "    print(f'[ DECK TELEMETRY ] Node {cycle:02d}/30 | Load: {random.randint(15, 95)}% [NOMINAL]')\n"
        "    time.sleep(2)\n"
    )
    return fallback, "static"


def pop_ready_named(config: dict) -> tuple[str, str, str]:
    """Like pop_ready_program, but also returns a file-name stem such as 'mazesolver'."""
    ensure_directories()
    ready = sorted(READY_DIR.glob("*.py"))
    stem = "sysmon"
    if ready and ready[0].stem.count("_") >= 2:
        stem = ready[0].stem.rsplit("_", 2)[0]
        if stem == "gen":          # old-style names from before slugs existed
            stem = "sysmon"
    if not ready:
        archived = list(ARCHIVE_DIR.glob("*.py"))
        if archived:
            pick = random.choice(archived)
            stem = "sysmon"
            if pick.stem.count("_") >= 2:
                stem = pick.stem.rsplit("_", 2)[0]
                if stem == "gen":
                    stem = "sysmon"
            return pick.read_text(), "archived", stem
    code, source = pop_ready_program(config)
    return code, source, stem


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
