"""
ghost_shift/director_phase2_test.py  (revised)
----------------------------------------------
Run from the project root as a module so the package imports resolve:

    python -m ghost_shift.director_phase2_test            # one cycle
    python -m ghost_shift.director_phase2_test --loop     # forever

Cycle: wait-state typing while the local model generates -> validate ->
type into nano -> save/exit nano -> run the program live.

Fixes vs the original:
  * Waits for the wait-state typing thread to really finish (it could
    previously keep typing into nano after a 3 s join timeout).
  * Clears any half-typed command before `clear` / opening nano.
  * Waits for the tmux client to attach so the pane has its real size.
  * Saves nano with pauses and CONFIRMS nano exited before touching the file
    (the old Ctrl+O, Enter, Ctrl+X burst could race, and killing nano with
    unsaved changes is what leaves *.save files behind).
  * Launches nano with -I so a user nanorc (autoindent) can't mangle code.
  * Uses the streaming HTTP client: bounded runtime, no infinite join.
  * Shorter prompt (fewer tokens = minutes saved), one shorter retry.
  * Only genuine LLM output is pushed to the content queue; on failure it
    replays an archived program before using the static fallback.
  * Program run is wrapped in `timeout` so it always ends.
"""

import argparse
import random
import subprocess
import threading
import time
import uuid
from pathlib import Path

from ghost_shift.config import load_config
from ghost_shift.local_llm import generate_local, strip_noise
from ghost_shift.queue import ContentQueue
from ghost_shift.sandbox import validate_code
from ghost_shift.stage import init_tmux_session, run_matrix_rain
from ghost_shift.telemetry import run_investigative_typing
from ghost_shift.typist import Typist

SESSION = "ghost"
STOP_FLAG = Path("/tmp/ghost_llm_ready.flag")
SHELLS = {"bash", "sh", "zsh", "dash"}
RUN_SECONDS = 150  # hard cap on a live program run
LOG_PATH = Path("~/.local/share/ghost-shift/ghost.log").expanduser()


def log(*parts) -> None:
    """Append to a log file. stdout is invisible while `tmux attach` owns the
    terminal, so watch this with:  tail -f ~/.local/share/ghost-shift/ghost.log
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts) + "\n")


SYSTEM_PROMPT = (
    "You write tiny Python 3 terminal programs. "
    "Output raw code only: no markdown fences, no explanations."
)

THEMES = [
    "a retro 1990s cyber-deck hardware diagnostic with CPU/RAM progress bars",
    "a glowing digital matrix clock with simulated system uptime telemetry",
    "a network traffic analyzer showing packet routes, ports, and latency",
    "a fake mainframe boot checker that probes imaginary disk arrays",
    "a modem-era BBS node monitor listing connected callers and baud rates",
    "a firewall log watcher flagging suspicious packets in colored text",
    "an ASCII oscilloscope drawing a scrolling sine wave",
]
CODENAMES = ["NIGHTJAR", "BLACKICE", "CRTWOLF", "VOIDLINE", "TAPEWORM", "HALCYON"]

FALLBACK_CODE = (
    "# ==================================================\n"
    "# [GHOST SHIFT SYSTEM MONITOR v1.0] - FALLBACK ACTIVE\n"
    "# ==================================================\n"
    "import time\n"
    "import random\n\n"
    "# [MAIN TELEMETRY LOOP - RUNS FOR 60 SECONDS]\n"
    "for cycle in range(30):\n"
    "    cpu_load = random.randint(18, 92)\n"
    "    mem_load = random.randint(45, 88)\n"
    "    print(f'[ CYBERDECK ] Node {cycle:02d}/30 | CPU: {cpu_load}% | "
    "RAM: {mem_load}% [SYS NOMINAL]')\n"
    "    time.sleep(2)\n"
    "# [END OF TELEMETRY SEQUENCE]\n"
)


# --------------------------------------------------------------------------
# tmux helpers
# --------------------------------------------------------------------------
def _tmux(*args: str) -> str:
    out = subprocess.run(
        ["tmux", *args], check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def send(*keys: str) -> None:
    _tmux("send-keys", "-t", SESSION, *keys)


def pane_command() -> str:
    return _tmux("display-message", "-p", "-t", SESSION, "#{pane_current_command}")


def client_attached() -> bool:
    try:
        return int(_tmux("display-message", "-p", "-t", SESSION, "#{session_attached}")) >= 1
    except (subprocess.CalledProcessError, ValueError):
        return False


def wait_until(predicate, timeout: float, poll: float = 0.5) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(poll)
    return False


def reset_prompt() -> None:
    """Abort any running command, discard a half-typed line, clear screen."""
    send("C-c")
    time.sleep(0.3)
    send("C-u")
    time.sleep(0.1)
    send("clear", "Enter")
    time.sleep(0.8)


# --------------------------------------------------------------------------
# Wait-state typing (runs while the model generates)
# --------------------------------------------------------------------------
def start_wait_state(typist: Typist) -> threading.Thread:
    STOP_FLAG.unlink(missing_ok=True)
    t = threading.Thread(
        target=run_investigative_typing, args=(SESSION, typist), daemon=True
    )
    t.start()
    return t


def stop_wait_state(t: threading.Thread) -> None:
    """Signal stop and wait for the thread to finish its current command."""
    STOP_FLAG.touch()
    t.join(timeout=90)
    if t.is_alive():
        log("[!] wait-state typing still running after 90s; "
              "telemetry.py should poll the flag between every command")
    else:
        STOP_FLAG.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Code generation
# --------------------------------------------------------------------------
def build_prompt(theme: str, max_lines: int) -> str:
    return (
        f"Write a Python 3 terminal program: {theme}. Codename: {random.choice(CODENAMES)}.\n"
        f"Rules:\n"
        f"- Under {max_lines} lines. Standard library only (time, random, math, datetime).\n"
        f"- Short retro 1990s hacker comments, e.g. # [ALLOCATING HEAP BUFFER].\n"
        f"- Use a finite loop: for cycle in range(30) with time.sleep(2).\n"
        f"- Print bracketed status like [OK] or [WARN] and ASCII bars.\n"
        f"- Raw code only."
    )


def generate_program(config: dict) -> str | None:
    llm = config.get("llm", {})
    model = llm.get("local_model", "qwen2.5-coder:3b")
    deadline = llm.get("deadline_s", 2400)
    theme = random.choice(THEMES)
    log(f"[*] generating with model={model!r} theme={theme[:40]!r}")

    # First attempt normal size; retry once with a smaller ask.
    for max_lines, max_tokens in ((45, 700), (25, 450)):
        try:
            raw = generate_local(
                build_prompt(theme, max_lines),
                model=model,
                system=SYSTEM_PROMPT,
                max_tokens=max_tokens,
                total_deadline=deadline,
                log=log,
            )
            _, _, cleaned = validate_code(strip_noise(raw))
            if cleaned and len(cleaned.strip()) >= 20:
                return cleaned
            log("[!] generation produced too little code; retrying smaller")
        except Exception as exc:  # validation failure, timeout, HTTP error
            log(f"[!] generation attempt failed: {exc}")
    return None


def fallback_program(workspace: Path) -> tuple[str, str]:
    """Replay a previously saved program if any exist, else the static one."""
    archived = [p for p in workspace.glob("sys_monitor_*.py") if p.stat().st_size > 200]
    if archived:
        return random.choice(archived).read_text(), "archived"
    return FALLBACK_CODE, "static"


# --------------------------------------------------------------------------
# nano + execution
# --------------------------------------------------------------------------
def type_into_nano(typist: Typist, file_path: Path, code: str) -> None:
    # -I ignore nanorc (autoindent would compound indentation), -E tabs to
    # spaces, -l line numbers for the look, -w never hard-wrap lines.
    send(f"nano -I -E -l -w {file_path}", "Enter")
    wait_until(lambda: pane_command() == "nano", timeout=10)
    time.sleep(0.8)

    typist.type_code_block(SESSION, code)
    time.sleep(1.0)

    # Save, then exit, with pauses; never fire these as one burst.
    send("C-o")
    time.sleep(0.8)
    send("Enter")
    time.sleep(0.8)
    send("C-x")

    if not wait_until(lambda: pane_command() in SHELLS, timeout=10):
        log("[!] nano did not exit; discarding its buffer")
        send("C-x")
        time.sleep(0.3)
        send("n")
        wait_until(lambda: pane_command() in SHELLS, timeout=5)

    # Nano is closed now, so it is safe to touch the file. Make sure the
    # canonical copy is what ends up on disk.
    on_disk = file_path.read_text() if file_path.exists() else ""
    if on_disk.strip() != code.strip():
        log("[!] nano buffer differed from generated code; rewriting file")
        file_path.write_text(code)


def run_program(typist: Typist, file_path: Path) -> None:
    typist.type_text(
        SESSION, f"clear && timeout {RUN_SECONDS} python3 {file_path}\n"
    )
    time.sleep(3)  # let the process start before polling for the shell
    wait_until(lambda: pane_command() in SHELLS, timeout=RUN_SECONDS + 15, poll=1)


# --------------------------------------------------------------------------
# One full scene
# --------------------------------------------------------------------------
def run_cycle(config: dict, queue: ContentQueue, typist: Typist) -> None:
    workspace = Path(
        config.get("system", {}).get("workspace_dir", "~/workspace")
    ).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)

    reset_prompt()
    waiter = start_wait_state(typist)
    try:
        code = generate_program(config)
    finally:
        stop_wait_state(waiter)

    source = "llm"
    if code is None:
        code, source = fallback_program(workspace)
        log(f"[*] using {source} program")

    reset_prompt()  # discard any half-typed wait-state command

    log(f"[*] program source: {source}")
    file_path = workspace / f"sys_monitor_{int(time.time())}_{uuid.uuid4().hex[:6]}.py"
    if source == "llm":
        queue.push("code", code, file_path.name)

    type_into_nano(typist, file_path, code)
    run_program(typist, file_path)
    time.sleep(random.uniform(4, 10))  # linger on the final output


def worker(config: dict, loop: bool) -> None:
    if not wait_until(client_attached, timeout=30):
        log("[!] tmux client never attached; continuing anyway")
    time.sleep(1.0)  # let tmux finish resizing the pane

    queue = ContentQueue()
    typist = Typist(config)
    while True:
        try:
            run_cycle(config, queue, typist)
        except Exception as exc:
            log(f"[!] cycle failed: {exc}")
            time.sleep(10)
        if not loop:
            break


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="run cycles forever")
    parser.add_argument("--no-rain", action="store_true", help="skip matrix rain")
    args = parser.parse_args()

    config = load_config()
    log("[*] Launching Ghost Shift art installation...")

    if not args.no_rain:
        run_matrix_rain(2)
    init_tmux_session(SESSION)

    # daemon=True so detaching from tmux (which returns from attach below)
    # ends the process instead of leaving the worker running headless.
    threading.Thread(target=worker, args=(config, args.loop), daemon=True).start()
    subprocess.run(["tmux", "attach", "-t", SESSION])


if __name__ == "__main__":
    main()
