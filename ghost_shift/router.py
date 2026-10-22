"""
ghost_shift/router.py
---------------------
LLM Router using direct CLI 'ollama run' subprocess execution.
Prints execution status directly to the active terminal.
"""

import subprocess
import logging
import time

logger = logging.getLogger("ghost_shift.router")

class LLMRouter:
    def __init__(self, config):
        llm_cfg = config.get("llm", {})
        self.model = llm_cfg.get("default_local_model", "qwen3.5:4b")

    def generate(self, prompt_type: str, user_prompt: str) -> str:
        print(f"\n==================================================", flush=True)
        print(f"[*] INITIATING OLLAMA GENERATION: {self.model}", flush=True)
        print(f"==================================================", flush=True)
        start_time = time.time()

        full_prompt = (
            "You are a 1990s hacker terminal script generator. "
            "Output ONLY raw Python code without markdown triple backticks. "
            "Include retro 1990s inline comments on every line. "
            "Use finite loops that run for 60 seconds (for i in range(30) with time.sleep(2)).\n\n"
            f"USER REQUEST: {user_prompt}"
        )

        try:
            print("[*] Calling subprocess: ollama run...", flush=True)
            result = subprocess.run(
                ["ollama", "run", self.model, full_prompt],
                capture_output=True,
                text=True,
                timeout=300
            )

            elapsed = time.time() - start_time
            print(f"[+] Ollama process finished in {elapsed:.2f}s (code {result.returncode})", flush=True)

            if result.returncode == 0 and len(result.stdout.strip()) > 20:
                content = result.stdout.strip()
                print(f"[+] Generated {len(content)} characters of custom Python code!", flush=True)
                return content
            else:
                print(f"[-] Ollama returned empty stdout. Stderr: {result.stderr}", flush=True)

        except Exception as e:
            print(f"[-] Subprocess Exception: {e}", flush=True)

        print("[-] RETURNING FALLBACK CODE BLOCK.", flush=True)
        return (
            "# [SYSTEM RECOVERY INITIALIZED]\n"
            "# [ALLOCATING HEAP SEGMENT 0x88]\n"
            "import time\n"
            "import random\n\n"
            "# [CYBERDECK MONITOR LOOP - 60 SECONDS]\n"
            "for cycle in range(30):\n"
            "    val = random.randint(15, 95)\n"
            "    print(f'[ DECK TELEMETRY ] Node {cycle:02d}/30 | Load: {val}% [NOMINAL]')\n"
            "    time.sleep(2)\n"
        )
