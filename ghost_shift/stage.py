import subprocess
import time
import os

def run_matrix_rain(duration_sec=10):
    """Runs cmatrix full screen if available, or a fallback python matrix rain script."""
    try:
        subprocess.run(["which", "cmatrix"], check=True, stdout=subprocess.DEVNULL)
        proc = subprocess.Popen(["cmatrix", "-s", "-b"])
        time.sleep(duration_sec)
        proc.terminate()
        proc.wait()
    except subprocess.CalledProcessError:
        end_time = time.time() + duration_sec
        cols = os.get_terminal_size().columns
        while time.time() < end_time:
            line = "".join([chr(ord('a') + os.urandom(1)[0] % 26) if (os.urandom(1)[0] % 3 == 0) else " " for _ in range(cols)])
            print(f"\033[32m{line}\033[0m")
            time.sleep(0.05)

def init_tmux_session(session_name="ghost"):
    """Creates a clean full-screen session (no split panes, 100% canvas)."""
    subprocess.run(["tmux", "kill-session", "-t", session_name], stderr=subprocess.DEVNULL)
    # Create a single window session taking up the full screen
    subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "bash"], check=True)
    # Clean 90s retro status bar at the bottom
    subprocess.run(["tmux", "set-option", "-t", session_name, "status-style", "bg=black,fg=green"], check=True)
    subprocess.run(["tmux", "set-option", "-t", session_name, "status-left", "[GHOST-SHIFT v0.1] "], check=True)
