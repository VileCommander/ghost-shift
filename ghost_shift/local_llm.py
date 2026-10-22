"""
ghost_shift/local_llm.py
------------------------
Streaming client for a local Ollama server, built for a slow Raspberry Pi.

Why this replaces `subprocess.Popen(["ollama", "run", ...])`:
  * Failure means "no tokens for idle_timeout seconds" or "total_deadline
    exceeded", NOT "a healthy generation was merely slow".
  * Output is capped with num_predict so runtime is bounded.
  * The model stays loaded (keep_alive=-1), avoiding multi-minute reloads.
  * Thinking mode is disabled so hybrid-reasoning models don't burn
    thousands of tokens before writing any code.
  * Real tokens/sec is logged so you can tune with numbers.
"""

import json
import re
import time

import requests

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"


class GenerationTimeout(Exception):
    """Raised when a generation exceeds its hard wall-clock deadline."""


def _post(payload: dict, idle_timeout: int) -> requests.Response:
    # (connect timeout, read timeout). The read timeout fires only if the
    # server sends NO bytes for that long, i.e. it behaves as an idle timeout.
    return requests.post(
        OLLAMA_CHAT_URL, json=payload, stream=True, timeout=(10, idle_timeout)
    )


def generate_local(
    prompt: str,
    model: str,
    system: str | None = None,
    max_tokens: int = 700,
    total_deadline: int = 2400,
    idle_timeout: int = 300,
    num_thread: int = 3,
    num_ctx: int = 2048,
    temperature: float = 0.8,
    on_token=None,
    log=print,
) -> str:
    """Stream a completion from Ollama and return the full text."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "think": False,  # removed automatically if the server rejects it
        "keep_alive": -1,
        "options": {
            "num_predict": max_tokens,
            "num_ctx": num_ctx,
            "num_thread": num_thread,
            "temperature": temperature,
        },
    }

    start = time.time()
    parts: list[str] = []
    final: dict = {}

    resp = _post(payload, idle_timeout)
    if resp.status_code == 400 and "think" in payload:
        # Older Ollama or a model without thinking support: retry without it.
        resp.close()
        payload.pop("think")
        resp = _post(payload, idle_timeout)

    with resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            token = chunk.get("message", {}).get("content", "")
            if token:
                parts.append(token)
                if on_token:
                    on_token(token)
            if chunk.get("done"):
                final = chunk
                break
            if time.time() - start > total_deadline:
                raise GenerationTimeout(
                    f"hard deadline of {total_deadline}s exceeded"
                )

    count = final.get("eval_count")
    dur = final.get("eval_duration")
    if count and dur:
        log(
            f"[llm] {model}: {count} tokens at {count / (dur / 1e9):.2f} tok/s "
            f"in {time.time() - start:.0f}s (stopped: {final.get('done_reason')})"
        )
    return "".join(parts)


_CODE_START = (
    "import ", "from ", "#", "def ", "class ", "for ", "while ", "if ", "print",
)


def strip_noise(text: str) -> str:
    """Remove <think> blocks, markdown fences, and chatty preambles."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*\Z", "", text, flags=re.DOTALL)  # unterminated

    fenced = re.search(r"```(?:python|py)?\s*\n(.*?)(?:```|\Z)", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)

    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith(_CODE_START):
            lines = lines[i:]
            break
    return "\n".join(lines).strip() + "\n"
