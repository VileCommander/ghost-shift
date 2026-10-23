"""
ghost_shift/director_desk.py
----------------------------
Main director: titled desk windows + background queues + mail scenes.

    python -m ghost_shift.director_desk --loop --no-rain
    python -m ghost_shift.director_desk --scene mail          # test one mail scene
    python -m ghost_shift.director_desk --scene code          # test one code scene

Scenes
  code: THINKING window (typed "investigative" commands + htop) ->
        EDITOR window (nano, code typed with human mistakes) ->
        TESTING window (program runs live) -> optional SCREENSAVER.
        Programs come instantly from library/ready/ (see generator_worker.py).
  mail: MAIL window: mutt opens, an unread message is read, the prepared reply
        is typed and sent (see email_scene.py).
In between, the SYSLOG pane fills the screen.
"""

import argparse
import random
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from ghost_shift import email_engine, email_scene
from ghost_shift.config import load_config
from ghost_shift.desk import Desk
from ghost_shift.generator_worker import pop_ready_named
from ghost_shift.queue import ContentQueue
from ghost_shift.stage import init_tmux_session, run_matrix_rain
from ghost_shift.telemetry import run_investigative_typing
from ghost_shift.typist import Typist
from ghost_shift.util import SHELLS, log, pane_command, send, tmux, wait_until

SESSION = "ghost"
STOP_FLAG = Path("/tmp/ghost_llm_ready.flag")
WIDE_ENOUGH = 140  # skip side windows on narrow screens

THINK_TITLES = ["THINKING", "NEURAL SYNTHESIS", "COGNITION", "PLANNING"]
EDIT_TITLES = ["EDITOR", "DEV CONSOLE", "WRITING CODE"]
TEST_TITLES = ["TESTING", "EXECUTING", "QA SANDBOX", "RUNNING TESTS"]


def client_attached() -> bool:
    try:
        return int(tmux("display-message", "-p", "-t", SESSION, "#{session_attached}")) >= 1
    except (subprocess.CalledProcessError, ValueError):
        return False


def monitor_cmd() -> str:
    return "htop" if shutil.which("htop") else "top"


# --------------------------------------------------------------------------
# code scenes
# --------------------------------------------------------------------------
def thinking_scene(desk: Desk, typist: Typist, seconds: float, project_dir: Path) -> None:
    title = random.choice(THINK_TITLES)
    log(f"[*] scene: {title}")
    stage = desk.open(title, where="top", cwd=str(project_dir))
    side = None
    if desk.screen_width() >= WIDE_ENOUGH:
        side = desk.open("NEURAL LOAD", where="right", anchor=stage,
                         size=0.38, command=monitor_cmd())
    pulse = desk.pulse_title(stage, title)

    STOP_FLAG.unlink(missing_ok=True)
    typing = threading.Thread(
        target=run_investigative_typing, args=(stage, typist), daemon=True
    )
    typing.start()
    try:
        time.sleep(seconds)
    finally:
        STOP_FLAG.touch()
        typing.join(timeout=60)
        if typing.is_alive():
            log("[!] wait-state typing still running after 60s")
        else:
            STOP_FLAG.unlink(missing_ok=True)
        pulse.stop()
        desk.title(stage, "[ SYNTHESIS COMPLETE ]")
        time.sleep(1.5)
        desk.close(side)
        desk.close(stage)


def editor_scene(desk: Desk, typist: Typist, file_path: Path, code: str) -> None:
    title = f"{random.choice(EDIT_TITLES)} :: {file_path.name}"
    log(f"[*] scene: {title}")
    pane = desk.open(title, where="top", cwd=str(file_path.parent))
    time.sleep(0.5)

    # -I ignore nanorc (autoindent), -E tabs->spaces, -l line numbers, -w no wrap
    send(pane, f"nano -I -E -l -w {file_path.name}", "Enter")
    wait_until(lambda: pane_command(pane) == "nano", timeout=10)
    time.sleep(0.8)

    typist.type_code_block(pane, code)
    time.sleep(1.0)

    send(pane, "C-o")
    time.sleep(0.8)
    send(pane, "Enter")
    time.sleep(0.8)
    send(pane, "C-x")

    if not wait_until(lambda: pane_command(pane) in SHELLS, timeout=10):
        log("[!] nano did not exit; discarding its buffer")
        send(pane, "C-x")
        time.sleep(0.3)
        send(pane, "n")
        wait_until(lambda: pane_command(pane) in SHELLS, timeout=5)

    # nano is closed: make sure the canonical copy is what is on disk
    on_disk = file_path.read_text() if file_path.exists() else ""
    if on_disk.strip() != code.strip():
        log("[!] nano buffer differed from generated code; rewriting file")
        file_path.write_text(code)

    time.sleep(1.0)
    desk.close(pane)


def test_scene(desk: Desk, typist: Typist, file_path: Path, run_seconds: int) -> None:
    title = random.choice(TEST_TITLES)
    log(f"[*] scene: {title}")
    stage = desk.open(title, where="top", cwd=str(file_path.parent))
    side = None
    if desk.screen_width() >= WIDE_ENOUGH:
        side = desk.open("SYSTEM LOAD", where="right", anchor=stage,
                         size=0.35, command=monitor_cmd())
    time.sleep(0.8)

    typist.type_text(stage, f"timeout {run_seconds} python3 {file_path.name}\n")
    time.sleep(3)
    wait_until(lambda: pane_command(stage) in SHELLS, timeout=run_seconds + 15, poll=1)

    desk.title(stage, "[ TEST COMPLETE ]")
    time.sleep(random.uniform(3, 6))
    desk.close(side)
    desk.close(stage)


def interlude_scene(desk: Desk) -> None:
    if not shutil.which("cmatrix"):
        return
    log("[*] scene: SCREENSAVER")
    pane = desk.open("SCREENSAVER", where="top", command="cmatrix -ab -C green")
    time.sleep(random.uniform(6, 12))
    desk.close(pane)


def code_cycle(config: dict, queue: ContentQueue, typist: Typist,
               desk: Desk, project_dir: Path) -> None:
    workspace = Path(
        config.get("system", {}).get("workspace_dir", "~/workspace")
    ).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)
    dcfg = config.get("director", {})

    thinking_scene(desk, typist, dcfg.get("think_seconds", 15), project_dir)

    code, source, stem = pop_ready_named(config)
    log(f"[*] popped program: source={source} name={stem}")

    file_path = workspace / f"{stem}_{int(time.time())}_{uuid.uuid4().hex[:4]}.py"
    if "llm" in source:
        queue.push("code", code, file_path.name)

    editor_scene(desk, typist, file_path, code)
    test_scene(desk, typist, file_path, dcfg.get("run_seconds", 120))


# --------------------------------------------------------------------------
# scheduling
# --------------------------------------------------------------------------
class Schedule:
    """Decides between code and mail scenes."""

    def __init__(self, config: dict):
        mcfg = config.get("mail", {})
        self.enabled = mcfg.get("enabled", True)
        self.every_min = max(1, mcfg.get("every_min", 2))
        self.every_max = max(self.every_min, mcfg.get("every_max", 4))
        self.code_since_mail = 0
        self.next_mail = random.randint(self.every_min, self.every_max)

    def pick(self, forced: str = "auto") -> str:
        if forced in ("code", "mail"):
            return forced
        if (self.enabled and self.code_since_mail >= self.next_mail
                and email_engine.unread_messages()):
            return "mail"
        return "code"

    def done(self, kind: str, ok: bool = True) -> None:
        if kind == "mail" and ok:
            self.code_since_mail = 0
            self.next_mail = random.randint(self.every_min, self.every_max)
        elif kind == "code":
            self.code_since_mail += 1


def run_cycle(config: dict, queue: ContentQueue, typist: Typist, desk: Desk,
              project_dir: Path, schedule: Schedule, forced: str) -> None:
    desk.cleanup()
    kind = schedule.pick(forced)
    if kind == "mail":
        if forced == "mail":
            email_engine.ensure_unread(config)
        ok = email_scene.run_scene(desk, typist, config)
        schedule.done("mail", ok)
        if not ok:
            schedule.code_since_mail = 0   # don't retry the same failure instantly
    else:
        code_cycle(config, queue, typist, desk, project_dir)
        schedule.done("code")
    interlude_scene(desk)
    time.sleep(random.uniform(3, 8))       # SYSLOG fills the screen for a moment


def worker(config: dict, loop: bool, desk: Desk, project_dir: Path, forced: str) -> None:
    if not wait_until(client_attached, timeout=30):
        log("[!] tmux client never attached; continuing anyway")
    time.sleep(1.0)

    queue = ContentQueue()
    typist = Typist(config)
    schedule = Schedule(config)
    while True:
        try:
            run_cycle(config, queue, typist, desk, project_dir, schedule, forced)
        except Exception as exc:
            log(f"[!] cycle failed: {exc}")
            desk.cleanup()
            time.sleep(10)
        if not loop:
            break


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="run cycles forever")
    parser.add_argument("--no-rain", action="store_true", help="skip startup rain")
    parser.add_argument("--no-anim", action="store_true", help="no grow/shrink animation")
    parser.add_argument("--scene", choices=["auto", "code", "mail"], default="auto",
                        help="force one kind of scene (for testing)")
    args = parser.parse_args()

    config = load_config()
    desk_cfg = config.get("desk", {})
    log("[*] Launching Ghost Shift (desk mode)...")

    if not args.no_rain:
        run_matrix_rain(2)
    init_tmux_session(SESSION)

    desk = Desk(
        SESSION,
        syslog_cmd=desk_cfg.get("syslog_cmd"),
        animate=not args.no_anim and desk_cfg.get("animate", True),
    )
    desk.setup()

    project_dir = Path.cwd()
    threading.Thread(
        target=worker, args=(config, args.loop, desk, project_dir, args.scene),
        daemon=True,
    ).start()
    subprocess.run(["tmux", "attach", "-t", SESSION])


if __name__ == "__main__":
    main()
