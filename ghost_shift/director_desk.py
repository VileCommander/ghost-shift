"""
ghost_shift/director_desk.py
----------------------------
Main Director with decoupled background queue integration.
Pulls ready AI-generated programs instantly from library/ready/.
"""

import argparse
import random
import subprocess
import threading
import time
import uuid
from pathlib import Path

from ghost_shift.config import load_config
from ghost_shift.generator_worker import pop_ready_program
from ghost_shift.queue import ContentQueue
from ghost_shift.stage import init_tmux_session, run_matrix_rain
from ghost_shift.telemetry import run_investigative_typing
from ghost_shift.typist import Typist

SESSION = "ghost"
STOP_FLAG = Path("/tmp/ghost_llm_ready.flag")
SHELLS = {"bash", "sh", "zsh", "dash"}
RUN_SECONDS = 120
LOG_PATH = Path("~/.local/share/ghost-shift/ghost.log").expanduser()

def log(*parts) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts) + "\n")

def _tmux(*args: str) -> str:
    out = subprocess.run(["tmux", *args], check=True, capture_output=True, text=True)
    return out.stdout.strip()

def send(*keys: str) -> None:
    _tmux("send-keys", "-t", SESSION, *keys)

def pane_command() -> str:
    return _tmux("display-message", "-p", "-t", SESSION, "#{pane_current_command}")

def client_attached() -> bool:
    try:
        return int(_tmux("display-message", "-p", "-t", SESSION, "#{session_attached}")) >= 1
    except Exception:
        return False

def wait_until(predicate, timeout: float, poll: float = 0.5) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(poll)
    return False

def reset_prompt() -> None:
    send("C-c")
    time.sleep(0.3)
    send("C-u")
    time.sleep(0.1)
    send("clear", "Enter")
    time.sleep(0.8)

def start_wait_state(typist: Typist) -> threading.Thread:
    STOP_FLAG.unlink(missing_ok=True)
    t = threading.Thread(target=run_investigative_typing, args=(SESSION, typist), daemon=True)
    t.start()
    return t

def stop_wait_state(t: threading.Thread) -> None:
    STOP_FLAG.touch()
    t.join(timeout=10)
    STOP_FLAG.unlink(missing_ok=True)

def type_into_nano(typist: Typist, file_path: Path, code: str) -> None:
    send(f"nano -I -E -l -w {file_path}", "Enter")
    wait_until(lambda: pane_command() == "nano", timeout=10)
    time.sleep(0.8)

    typist.type_code_block(SESSION, code)
    time.sleep(1.0)

    send("C-o")
    time.sleep(0.8)
    send("Enter")
    time.sleep(0.8)
    send("C-x")

    if not wait_until(lambda: pane_command() in SHELLS, timeout=10):
        log("[!] nano exit timeout; sending extra exit sequence")
        send("C-x")
        time.sleep(0.3)
        send("n")
        wait_until(lambda: pane_command() in SHELLS, timeout=5)

    on_disk = file_path.read_text() if file_path.exists() else ""
    if on_disk.strip() != code.strip():
        log("[!] nano buffer difference detected; rewriting canonical copy")
        file_path.write_text(code)

def run_program(typist: Typist, file_path: Path) -> None:
    typist.type_text(SESSION, f"clear && timeout {RUN_SECONDS} python3 {file_path}\n")
    time.sleep(3)
    wait_until(lambda: pane_command() in SHELLS, timeout=RUN_SECONDS + 15, poll=1)

def run_cycle(config: dict, queue: ContentQueue, typist: Typist) -> None:
    workspace = Path(config.get("system", {}).get("workspace_dir", "~/workspace")).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)

    reset_prompt()
    
    # 1. Brief telemetry wait state (12 seconds of active typing)
    waiter = start_wait_state(typist)
    time.sleep(12)
    stop_wait_state(waiter)

    # 2. Pop pre-generated program instantly from background queue
    code, source = pop_ready_program(config)
    log(f"[*] Popped program source: {source}")

    reset_prompt()

    file_path = workspace / f"sys_monitor_{int(time.time())}_{uuid.uuid4().hex[:6]}.py"
    if "llm" in source:
        queue.push("code", code, file_path.name)

    # 3. Type into nano and execute live
    type_into_nano(typist, file_path, code)
    run_program(typist, file_path)
    time.sleep(random.uniform(4, 8))

def worker(config: dict, loop: bool) -> None:
    if not wait_until(client_attached, timeout=30):
        log("[!] tmux client never attached; continuing anyway")
    time.sleep(1.0)

    queue = ContentQueue()
    typist = Typist(config)
    while True:
        try:
            run_cycle(config, queue, typist)
        except Exception as exc:
            log(f"[!] Cycle error: {exc}")
            time.sleep(5)
        if not loop:
            break

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="run cycles continuously")
    parser.add_argument("--no-rain", action="store_true", help="skip matrix rain")
    args = parser.parse_args()

    config = load_config()
    log("[*] Starting Ghost Shift Director Desk...")

    if not args.no_rain:
        run_matrix_rain(2)
    init_tmux_session(SESSION)

    threading.Thread(target=worker, args=(config, args.loop), daemon=True).start()
    subprocess.run(["tmux", "attach", "-t", SESSION])

if __name__ == "__main__":
    main()
