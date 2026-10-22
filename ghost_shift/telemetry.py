"""
ghost_shift/telemetry.py
------------------------
Simulates human investigative typing in the terminal while waiting for the LLM.
Polls the ready flag continuously to transition instantly when the LLM finishes.
"""

import time
import random
import os
import json
from pathlib import Path

POOL_PATH = Path("~/.local/share/ghost-shift/commands_pool.json").expanduser()

DEFAULT_COMMANDS = [
    "df -h", "free -m", "uptime", "ls -la ghost_shift/", "ls -la workspace/",
    "cat /proc/loadavg", "ps aux --sort=-%cpu | head -n 5", "uname -a",
    "netstat -tuln", "whoami", "date", "vmstat 1 3", "sensors"
]

def load_command_pool() -> list:
    if POOL_PATH.exists():
        try:
            with open(POOL_PATH, "r") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            pass
    return DEFAULT_COMMANDS.copy()

def run_investigative_typing(session_name: str, typist):
    """
    Pulls unique commands from the pool and types them out while waiting for Ollama.
    """
    flag_path = Path("/tmp/ghost_llm_ready.flag")
    Path("workspace").mkdir(parents=True, exist_ok=True)
    
    pool = load_command_pool()
    used_commands = set()
    
    typist.type_text(session_name, "echo '[-] SESSION ACTIVE: AWAITING NEURAL SYNTHESIS...'\n")
    time.sleep(2.0)
    
    while not flag_path.exists():
        if flag_path.exists():
            break
            
        available = [c for c in pool if c not in used_commands]
        if not available:
            used_commands.clear()
            available = pool
            
        cmd = random.choice(available)
        used_commands.add(cmd)
        
        typist.type_text(session_name, f"{cmd}\n")
        
        # Check flag frequently during the pause so it transitions instantly
        for _ in range(20):
            if flag_path.exists():
                break
            time.sleep(0.5)
