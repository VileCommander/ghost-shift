"""
ghost_shift/generator_worker.py
-------------------------------
Background queue generator that decouple LLM generation times from the live display.
Keeps a pool of validated, ready-to-type Python scripts inside library/ready/.
"""

import time
import os
import uuid
import logging
from pathlib import Path

from ghost_shift.config import load_config
from ghost_shift.codegen import generate_program
from ghost_shift.sandbox import validate_code

logger = logging.getLogger("ghost_shift.generator")

READY_DIR = Path("~/.local/share/ghost-shift/library/ready").expanduser()
ARCHIVE_DIR = Path("~/.local/share/ghost-shift/library/archive").expanduser()

def ensure_directories():
    """Creates persistent library storage directories if they do not exist."""
    READY_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

def fill_ready_queue(config: dict, target_count: int = 3):
    """
    Checks the ready queue and generates new scripts until target_count is met.
    """
    ensure_directories()
    
    existing = list(READY_DIR.glob("*.py"))
    current_count = len(existing)
    
    if current_count >= target_count:
        return

    needed = target_count - current_count
    print(f"[*] Ready queue count: {current_count}/{target_count}. Generating {needed} new script(s)...")

    for i in range(needed):
        try:
            code = generate_program(config)
            if code:
                # Security double-check
                is_safe, _, cleaned = validate_code(code)
                if is_safe and len(cleaned.strip()) >= 20:
                    filename = f"gen_{int(time.time())}_{uuid.uuid4().hex[:6]}.py"
                    file_path = READY_DIR / filename
                    file_path.write_text(cleaned)
                    print(f"[+] Added fresh program to ready queue: {filename}")
                else:
                    print("[-] Generated program failed sandbox verification.")
            else:
                print("[-] Generator returned None.")
        except Exception as e:
            print(f"[-] Generation error: {e}")
            
        time.sleep(2)

def pop_ready_program(config: dict) -> tuple[str, str]:
    """
    Pulls the next ready program from library/ready/, moves a copy to library/archive/,
    and returns (code_string, source_type).
    """
    ensure_directories()
    ready_files = sorted(list(READY_DIR.glob("*.py")))
    
    if ready_files:
        target = ready_files[0]
        code = target.read_text()
        
        # Archive copy
        archive_target = ARCHIVE_DIR / target.name
        archive_target.write_text(code)
        
        # Remove from ready queue
        target.unlink()
        return code, "llm_queued"
        
    # If ready queue is empty, attempt to replay from archive
    archived = list(ARCHIVE_DIR.glob("*.py"))
    if archived:
        import random
        replay = random.choice(archived)
        return replay.read_text(), "archived"
        
    # Standard static fallback if no programs exist anywhere
    fallback = (
        "# [SYSTEM RECOVERY INITIALIZED]\n"
        "import time\nimport random\n\n"
        "for cycle in range(30):\n"
        "    print(f'[ DECK TELEMETRY ] Node {cycle:02d}/30 | Load: {random.randint(15, 95)}% [NOMINAL]')\n"
        "    time.sleep(2)\n"
    )
    return fallback, "static"

def run_worker_loop():
    """Runs continuously as a background service or standalone worker."""
    config = load_config()
    print("[*] Starting Ghost Shift Background Content Generator Worker...")
    while True:
        try:
            fill_ready_queue(config, target_count=3)
        except Exception as e:
            print(f"[-] Worker error: {e}")
        time.sleep(10)

if __name__ == "__main__":
    run_worker_loop()
