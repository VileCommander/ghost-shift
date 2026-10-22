"""
ghost_shift/typist.py
---------------------
Simulates a human typing into tmux panes: fast burst typing, keyboard-neighbour
typos, and (in code blocks) believable SYNTAX MISTAKES that the "programmer"
notices and fixes on screen. Every mistake is fully repaired before the next
line starts, so the saved file is always exactly the code that was passed in.

The first argument of every method is any tmux target: a session name or a
pane id such as "%7".

Mistakes (code blocks only, one per affected line):
  misspell  a keyword/identifier is typed wrong (retrun, pritn, true, ...);
            after the line is finished the cursor walks back, fixes it, and
            returns to the end of the line.
  eq        `if x == 3:` typed as `if x = 3:`, fixed the same way.
  missing   the colon / closing bracket / closing quote is forgotten, Enter is
            pressed, then the programmer notices, goes Up, End, adds it, Down.
  closer    the wrong closing bracket is typed (`]` for `)`), noticed after a
            beat, backspaced and corrected.

Optional config.yaml section (every key optional):

    typist:
      base_wpm: 90               # shell-command typing speed
      variance: 30
      typo_chance: 0.03          # per letter, shell commands
      code_typo_chance: 0.015    # per letter, code
      code_speed: 3.0            # speed multiplier while typing code
      burst: true                # send 1-5 characters per tmux call
      mistake_chance: 0.15       # per code line; set 0 to disable mistakes
      max_mistakes_per_block: 5
      notice_min: 0.35           # seconds before a mistake is noticed
      notice_max: 1.0
      pause_punctuation: 0.12
      pause_newline: 0.4
      correction_delay_min: 0.08
      correction_delay_max: 0.22
"""

import logging
import random
import re
import subprocess
import time

logger = logging.getLogger("ghost_shift.typist")

# QWERTY neighbours, so typos land on a nearby key like a human's would.
NEIGHBORS = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh",
    "u": "yij", "i": "uok", "o": "ipl", "p": "ol", "a": "qsz", "s": "awdx",
    "d": "sefc", "f": "drgv", "g": "fthb", "h": "gyjn", "j": "hukm", "k": "jil",
    "l": "kop", "z": "asx", "x": "zsc", "c": "xdv", "v": "cfb", "b": "vgn",
    "n": "bhm", "m": "nj",
}
SPECIAL = ".,;:!?\n"          # a chunk always ends after one of these
CLOSERS = ")]}"
WORD_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]{3,}")


def _code_mask(body: str) -> list:
    """True for characters that are real code (not inside a string/comment)."""
    mask, quote, esc = [], None, False
    for ch in body:
        if quote:
            mask.append(False)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
        elif ch == "#":
            mask.extend([False] * (len(body) - len(mask)))
            break
        elif ch in "'\"":
            quote = ch
            mask.append(False)
        else:
            mask.append(True)
    return mask


def _misspell(word: str):
    """Return a plausible wrong version of `word`, or None."""
    if word in ("True", "False", "None"):
        return word[0].lower() + word[1:]
    ops = []
    swaps = [k for k in range(1, len(word) - 1) if word[k] != word[k + 1]]
    if swaps:
        ops.append("swap")
    if len(word) >= 5:
        ops.append("drop")
    ops.append("double")
    op = random.choice(ops)
    if op == "swap":
        k = random.choice(swaps)
        return word[:k] + word[k + 1] + word[k] + word[k + 2:]
    if op == "drop":
        k = random.randrange(1, len(word) - 1)
        return word[:k] + word[k + 1:]
    k = random.randrange(1, len(word))
    return word[:k] + word[k] + word[k:]


class Typist:
    def __init__(self, config):
        cfg = config.get("typist", {})
        self.base_wpm = cfg.get("base_wpm", 90)
        self.variance = cfg.get("variance", 30)
        self.typo_chance = cfg.get("typo_chance", 0.03)
        self.code_typo_chance = cfg.get("code_typo_chance", 0.015)
        self.code_speed = max(0.1, cfg.get("code_speed", 3.0))
        self.burst = cfg.get("burst", True)
        self.mistake_chance = cfg.get("mistake_chance", 0.15)
        self.max_mistakes = cfg.get("max_mistakes_per_block", 5)
        self.notice_min = cfg.get("notice_min", 0.35)
        self.notice_max = cfg.get("notice_max", 1.0)
        self.corr_min = cfg.get("correction_delay_min", 0.08)
        self.corr_max = cfg.get("correction_delay_max", 0.22)
        self.pause_punct = cfg.get("pause_punctuation", 0.12)
        self.pause_newline = cfg.get("pause_newline", 0.4)

    # ------------------------------------------------------------- timing
    def _get_delay(self) -> float:
        wpm = max(10, random.gauss(self.base_wpm, self.variance))
        chars_per_sec = (wpm * 5) / 60.0
        delay = 1.0 / chars_per_sec
        return max(0.02, random.uniform(0.02, delay * 1.5))

    @staticmethod
    def _pause(seconds: float, speed: float = 1.0) -> None:
        time.sleep(seconds / speed)

    def _notice(self) -> None:
        """Human reaction time before spotting a mistake."""
        time.sleep(random.uniform(self.notice_min, self.notice_max))

    # ------------------------------------------------------------ tmux I/O
    @staticmethod
    def _tmux_send(target: str, *args: str) -> None:
        subprocess.run(["tmux", "send-keys", "-t", target, *args], check=True)

    def _send_key(self, target: str, key: str) -> None:
        """Send a named key such as Enter, BSpace, Left, Up, End."""
        self._tmux_send(target, key)

    def _send_literal(self, target: str, text: str) -> None:
        """Send text exactly as given (no key-name interpretation)."""
        if not text:
            return
        # A bare "-x..." argument would be parsed as a tmux option.
        if text.startswith("-") and len(text) > 1:
            self._send_literal(target, "-")
            self._send_literal(target, text[1:])
            return
        # tmux treats an argument ending in ";" as a command separator.
        if text.endswith(";"):
            text = text[:-1] + "\\;"
        self._tmux_send(target, "-l", text)

    def _send_chunk(self, target: str, chunk: str) -> None:
        # Newline must be the Enter key (CR). A literal LF is Ctrl-J, which
        # bash accepts but nano treats as "Justify".
        parts = chunk.split("\n")
        for i, part in enumerate(parts):
            if part:
                self._send_literal(target, part)
            if i < len(parts) - 1:
                self._send_key(target, "Enter")

    def _repeat_key(self, target: str, key: str, n: int, gap: float = 0.03) -> None:
        """Press a key n times in small groups, like holding it down."""
        while n > 0:
            k = min(n, 4)
            self._tmux_send(target, *([key] * k))
            n -= k
            time.sleep(gap)

    # -------------------------------------------------------------- chunks
    def _chunks(self, text: str):
        i = 0
        while i < len(text):
            n = random.choice([1, 2, 2, 3, 3, 4, 5]) if self.burst else 1
            chunk = text[i:i + n]
            if chunk[0] == "-":
                chunk = "-"
            for j, ch in enumerate(chunk):
                if ch in SPECIAL:
                    chunk = chunk[:j + 1]
                    break
            yield chunk
            i += len(chunk)

    # -------------------------------------------------------------- public
    def type_text(self, session_name: str, text: str, target_window: str = None,
                  speed: float = 1.0, typo_chance: float = None) -> None:
        """Type text like a person: bursts, pauses, neighbour-key typos."""
        if target_window:
            subprocess.run(
                ["tmux", "select-window", "-t", f"{session_name}:{target_window}"],
                check=True,
            )
        typo = self.typo_chance if typo_chance is None else typo_chance

        for chunk in self._chunks(text):
            first = chunk[0]
            if random.random() < typo * len(chunk) and first.lower() in NEIGHBORS:
                wrong = random.choice(NEIGHBORS[first.lower()])
                if first.isupper():
                    wrong = wrong.upper()
                self._send_literal(session_name, wrong)
                self._pause(random.uniform(self.corr_min, self.corr_max), speed)
                self._send_key(session_name, "BSpace")
                self._pause(random.uniform(self.corr_min, self.corr_max), speed)

            self._send_chunk(session_name, chunk)

            last = chunk[-1]
            regular = len(chunk) - (1 if last in SPECIAL else 0)
            wait = sum(self._get_delay() for _ in range(regular))
            if last == "\n":
                wait += random.uniform(self.pause_newline * 0.5, self.pause_newline * 1.5)
            elif last in SPECIAL:
                wait += random.uniform(self.pause_punct * 0.5, self.pause_punct * 1.5)
            self._pause(wait, speed)

    def type_code_block(self, session_name: str, code_str: str) -> None:
        """Type multi-line code into an editor with occasional syntax mistakes.

        Indentation is sent instantly (a real editor would auto-indent).
        Assumes the editor has NO auto-indent and starts on an empty line.
        """
        # Only un-escape when the whole program arrived as ONE line containing
        # literal backslash-n sequences. Never touch "\\n" inside real code.
        if "\n" not in code_str.strip() and "\\n" in code_str:
            code_str = code_str.replace("\\n", "\n")

        mistakes_left = self.max_mistakes
        for line in code_str.splitlines():
            body = line.lstrip(" ")
            indent = line[: len(line) - len(body)]
            if indent:
                self._send_literal(session_name, indent)

            plan = None
            if body and mistakes_left > 0 and random.random() < self.mistake_chance:
                plan = self._plan_mistake(body)
                if plan:
                    mistakes_left -= 1

            typed = plan["typed"] if plan else body
            if typed:
                self.type_text(session_name, typed, speed=self.code_speed,
                               typo_chance=self.code_typo_chance)

            kind = plan["kind"] if plan else None
            if kind == "closer":
                self._notice()
                self._send_key(session_name, "BSpace")
                time.sleep(0.1)
                self.type_text(session_name, plan["right"], speed=self.code_speed,
                               typo_chance=0)
            elif kind in ("misspell", "eq"):
                self._notice()
                self._fix_in_line(session_name, plan)

            self._send_key(session_name, "Enter")

            if kind == "missing":
                self._notice()
                self._send_key(session_name, "Up")
                self._send_key(session_name, "End")
                time.sleep(0.2)
                self.type_text(session_name, plan["right"], speed=self.code_speed,
                               typo_chance=0)
                time.sleep(0.15)
                self._send_key(session_name, "Down")
            time.sleep(random.uniform(0.1, 0.2) / self.code_speed)

    # ------------------------------------------------------------ mistakes
    def _plan_mistake(self, body: str):
        """Pick one applicable mistake for this line, or None."""
        text = body.rstrip()
        if len(text) < 6 or text.startswith("#"):
            return None
        mask = _code_mask(body)
        options = []  # (weight, kind)

        words = [m for m in WORD_RE.finditer(body) if all(mask[m.start():m.end()])]
        if words:
            options.append((4, "misspell"))
        if re.match(r"(if|elif|while)\b", body):
            if any(body.startswith("==", i) and mask[i] and mask[i + 1]
                   for i in range(len(body) - 1)):
                options.append((2, "eq"))
        if body == text and text[-1] in ":)]}\"'":
            options.append((3, "missing"))
        if body == text and text[-1] in CLOSERS:
            options.append((2, "closer"))
        if not options:
            return None

        kinds, weights = [k for _, k in options], [w for w, _ in options]
        kind = random.choices(kinds, weights)[0]

        if kind == "misspell":
            m = random.choice(words)
            wrong = _misspell(m.group())
            if not wrong or wrong == m.group():
                return None
            typed = body[:m.start()] + wrong + body[m.end():]
            return {"kind": kind, "typed": typed,
                    "start": m.start(), "wrong": wrong, "right": m.group()}
        if kind == "eq":
            idxs = [i for i in range(len(body) - 1)
                    if body.startswith("==", i) and mask[i] and mask[i + 1]]
            i = random.choice(idxs)
            typed = body[:i] + "=" + body[i + 2:]
            return {"kind": kind, "typed": typed,
                    "start": i, "wrong": "=", "right": "=="}
        if kind == "missing":
            return {"kind": kind, "typed": body[:-1], "right": body[-1]}
        wrong = random.choice([c for c in CLOSERS if c != text[-1]])
        return {"kind": "closer", "typed": body[:-1] + wrong, "right": text[-1]}

    def _fix_in_line(self, target: str, plan: dict) -> None:
        """Walk the cursor back to the mistake, repair it, return to line end."""
        start, wrong, right = plan["start"], plan["wrong"], plan["right"]
        left = len(plan["typed"]) - (start + len(wrong))
        self._repeat_key(target, "Left", left)
        time.sleep(0.15)
        self._repeat_key(target, "BSpace", len(wrong), gap=0.05)
        time.sleep(0.1)
        self.type_text(target, right, speed=self.code_speed, typo_chance=0)
        time.sleep(0.1)
        self._send_key(target, "End")
