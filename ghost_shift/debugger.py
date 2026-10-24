"""
ghost_shift/debugger.py
-----------------------
The "coder": finds crashing programs and tries to fix them, in the background.

  smoke_test()    runs a program headlessly in a child process: time.sleep is a
                  no-op (a 90 second animation finishes in seconds), stdout is
                  discarded, and CPU, memory and file-size limits apply. A crash
                  anywhere in the run is caught and summarised.
  debug_program() asks the model for a fix, re-tests it, and retries.
  make_patch()    turns old/new source into line edits that the director can
                  type into nano on screen, like a person fixing the bug.

The smoke test executes AI-written code, just as the live TESTING window does;
the resource limits make that safer but it is not a full sandbox.
"""

import difflib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ghost_shift import tickets
from ghost_shift.codegen import DEFAULT_MODULES, SYSTEM_PROMPT
from ghost_shift.local_llm import generate_local, strip_noise
from ghost_shift.sandbox import validate_code
from ghost_shift.util import log

HARNESS_PATH = Path("~/.local/share/ghost-shift/harness.py").expanduser()

HARNESS = '''\
import os, resource, runpy, sys, time

path = sys.argv[1]
cpu = int(sys.argv[2]) if len(sys.argv) > 2 else 25
resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 5))
resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, 1 << 20))
resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
time.sleep = lambda seconds: None          # run the whole animation instantly
sys.stdout = open(os.devnull, "w")
sys.stdin = open(os.devnull, "r")
runpy.run_path(path, run_name="__main__")
'''

FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>.+))?$')


def ensure_harness() -> None:
    HARNESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not HARNESS_PATH.exists() or HARNESS_PATH.read_text() != HARNESS:
        HARNESS_PATH.write_text(HARNESS)


def parse_failure(stderr: str, prog_path: str, display_name: str) -> dict:
    """Boil a raw traceback down to the program's own frames."""
    lines = stderr.splitlines()
    frames = []
    for i, ln in enumerate(lines):
        m = FRAME.match(ln)
        if not m or m["file"] != prog_path:
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        src = nxt.strip() if nxt.startswith("    ") and not FRAME.match(nxt) else ""
        frames.append((int(m["line"]), m["func"] or "<module>", src))
    error = next((ln.strip() for ln in reversed(lines)
                  if ln.strip() and not ln.startswith((" ", "\t"))
                  and not ln.startswith("Traceback")), "")
    out = ["Traceback (most recent call last):"]
    for lineno, func, src in frames:
        out.append(f'  File "{display_name}", line {lineno}, in {func}')
        if src:
            out.append(f"    {src}")
    out.append(error)
    line, source = (frames[-1][0], frames[-1][2]) if frames else (None, "")
    return {"error": error + (f" (line {line})" if line else ""),
            "line": line, "source": source, "traceback": "\n".join(out)}


def smoke_test(code: str, name: str = "program.py", cpu_seconds: int = 25,
               wall_timeout: int = 40) -> dict:
    """Run a program headlessly. Returns {"ok": bool, "kind": ..., ...}."""
    if re.search(r"^\s*(import curses|from curses)", code, re.M):
        return {"ok": True, "kind": "skipped"}       # needs a real terminal
    ensure_harness()
    with tempfile.TemporaryDirectory(prefix="ghost-smoke-") as tmp:
        prog = Path(tmp) / name
        prog.write_text(code)
        env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp,
               "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            r = subprocess.run(
                [sys.executable, str(HARNESS_PATH), str(prog), str(cpu_seconds)],
                capture_output=True, text=True, timeout=wall_timeout,
                cwd=tmp, stdin=subprocess.DEVNULL, env=env)
        except subprocess.TimeoutExpired:
            return {"ok": True, "kind": "slow"}
        if r.returncode == 0:
            return {"ok": True, "kind": "ok"}
        if r.returncode < 0:                         # killed by a limit (CPU etc.)
            return {"ok": True, "kind": "slow"}
        info = parse_failure(r.stderr, str(prog), name)
        if not info["error"]:
            return {"ok": True, "kind": "unknown"}
        return {"ok": False, "kind": "crash", **info}


def request_fix(config: dict, code: str, failure: dict):
    """Ask the model to repair the program. Returns new source or None."""
    model = config.get("llm", {}).get("local_model", "qwen2.5-coder:3b")
    deadline = config.get("llm", {}).get("deadline_s", 2400)
    modules = config.get("codegen", {}).get("allowed_modules", DEFAULT_MODULES)
    lines = ["This Python 3 program crashes. Fix the bug.", "", "Program:",
             code.rstrip(), "", "Error:", failure["traceback"]]
    if failure.get("line") and failure.get("source"):
        lines.append(f"The failing line is line {failure['line']}: {failure['source']}")
    lines += ["", "Rules:",
              "- Output the complete corrected program, raw code only: no markdown, no explanations.",
              "- Change as little as possible.",
              f"- Allowed imports: {', '.join(modules)}. No input(), no files, no network, no os, no sys."]
    raw = generate_local("\n".join(lines), model=model, system=SYSTEM_PROMPT,
                         max_tokens=1200, total_deadline=deadline, log=log)
    _, _, cleaned = validate_code(strip_noise(raw))
    if cleaned and cleaned.strip() and cleaned.strip() != code.strip():
        return cleaned
    return None


def debug_program(config: dict, code: str, name: str, slug: str,
                  failure: dict, ticket: dict) -> dict:
    """Try to fix a crashing program. Returns the 'story' for the director."""
    max_attempts = config.get("debug", {}).get("max_attempts", 2)
    timeout = config.get("debug", {}).get("smoke_timeout", 40)
    current, fail, fixed, attempts = code, failure, None, 0
    for n in range(1, max_attempts + 1):
        attempts = n
        tickets.update_ticket(ticket["id"], attempts=n)
        try:
            candidate = request_fix(config, current, fail)
        except Exception as exc:
            log(f"[!] fix attempt {n} failed: {exc}")
            candidate = None
        if not candidate:
            continue
        result = smoke_test(candidate, name=name, wall_timeout=timeout)
        if result["ok"]:
            fixed = candidate
            break
        current, fail = candidate, result    # feed the new error into the next try
    return {"program": name, "slug": slug, "ticket": ticket["id"],
            "status": "fixed" if fixed else "unfixed", "attempts": attempts,
            "error": failure["error"], "line": failure.get("line"),
            "traceback": failure["traceback"], "fixed_code": fixed}


def make_patch(old: str, new: str) -> list:
    """Line edits turning old into new: [{"start": 1-based line, "remove": n, "insert": [...]}]."""
    a, b = old.splitlines(), new.splitlines()
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    return [{"start": i1 + 1, "remove": i2 - i1, "insert": b[j1:j2]}
            for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]


def should_patch(hunks: list) -> bool:
    """Small edits are patched in place; big ones are rewritten from scratch."""
    changed = sum(h["remove"] + len(h["insert"]) for h in hunks)
    return 0 < len(hunks) <= 4 and changed <= 14
