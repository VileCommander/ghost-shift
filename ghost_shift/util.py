"""
ghost_shift/util.py
-------------------
Small helpers shared by the directors and scenes: file logging (stdout is
invisible while `tmux attach` owns the terminal), tmux calls, and polling.
"""

import subprocess
import time
from pathlib import Path

LOG_PATH = Path("~/.local/share/ghost-shift/ghost.log").expanduser()
SHELLS = {"bash", "sh", "zsh", "dash"}

# Last-resort program when there is nothing queued and nothing archived.
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


def log(*parts) -> None:
    """Append a timestamped line to ~/.local/share/ghost-shift/ghost.log."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts) + "\n")


def tmux(*args: str) -> str:
    out = subprocess.run(["tmux", *args], check=True, capture_output=True, text=True)
    return out.stdout.strip()


def send(target: str, *keys: str) -> None:
    """Send named keys (Enter, C-o, Down, ...) to a tmux pane."""
    tmux("send-keys", "-t", target, *keys)


def pane_command(target: str) -> str:
    """Foreground command of a pane, or "" if the pane no longer exists."""
    try:
        return tmux("display-message", "-p", "-t", target, "#{pane_current_command}")
    except subprocess.CalledProcessError:
        return ""


def wait_until(predicate, timeout: float, poll: float = 0.5) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(poll)
    return False
