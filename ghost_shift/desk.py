
"""
ghost_shift/desk.py
-------------------
A tiny tiling "window manager" built on tmux panes.

Every pane gets a retro title bar (tmux pane-border-status). Windows open by
growing out of the screen edge and close by shrinking away, so the installation
looks like windows are being summoned and dismissed instead of one static
terminal.

Layout model
  * A permanent BASE pane lives at the bottom. Between scenes it fills the
    screen showing the "idle" content; while a scene is open it shrinks to a
    strip showing the "strip" content.
  * Stage windows open ABOVE it.
  * Side windows (htop etc.) open to the RIGHT of a stage window.

Strip / idle content: "off" (a blank 1-row sliver), "syslog" (the log),
"tickets" (the manager's board), "clock", or "matrix" (needs cmatrix).

Panes are addressed by tmux pane id (like "%7"). Pass that id anywhere the old
code passed the session name, e.g. typist.type_text(pane_id, "ls\\n").
"""

import shlex
import shutil
import subprocess
import sys
import threading
import time


def _tmux(*args: str, check: bool = True) -> str:
    r = subprocess.run(["tmux", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"tmux {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


class Pulse:
    """Animates a pane title: 'THINKING...  02:41'. Call stop() when done."""

    def __init__(self, desk: "Desk", pane: str, text: str):
        self._desk, self._pane, self._text = desk, pane, text
        self._stop = threading.Event()
        self._t0 = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        i = 0
        while not self._stop.wait(0.6):
            el = int(time.time() - self._t0)
            dots = ("." * (i % 4)).ljust(3)
            self._desk.title(
                self._pane, f"[ {self._text}{dots} ]  {el // 60:02d}:{el % 60:02d}"
            )
            i += 1

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)


BASE_TITLES = {"syslog": "[ SYSLOG ]", "tickets": "[ TICKET BOARD ]",
               "clock": "[ CLOCK ]", "matrix": "[ SCREENSAVER ]"}


class Desk:
    def __init__(
        self,
        session: str = "ghost",
        syslog_cmd: str | None = None,
        animate: bool = True,
        step_delay: float = 0.03,
        strip: str = "off",
        strip_lines: int = 9,
        idle: str = "syslog",
        project_dir=None,
    ):
        self.session = session
        self.animate = animate
        self.step_delay = step_delay
        self.syslog_cmd = syslog_cmd or (
            "tail -n 40 -F ~/.local/share/ghost-shift/ghost.log"
        )
        self.strip = strip
        self.idle = idle
        # "off" leaves a 1-row sliver (tmux cannot give a pane zero rows)
        self.strip_lines = 2 if strip == "off" else max(3, int(strip_lines))
        self.project_dir = project_dir
        self.base: str = ""
        self._horizontal: dict[str, bool] = {}
        self._stages: set[str] = set()
        self._status_extra = ""

    # ------------------------------------------------------------------ setup
    def setup(self) -> None:
        """Style the session and turn the first pane into the base pane."""
        s = self.session
        window_opts = [
            ("pane-border-status", "top"),
            ("pane-border-format", " #{pane_title} "),
            ("pane-border-lines", "double"),          # tmux >= 3.2
            ("pane-border-style", "fg=colour22"),
            ("pane-active-border-style", "fg=colour46,bold"),
            ("allow-set-title", "off"),               # shells can't rename panes
            ("window-status-format", ""),
            ("window-status-current-format", ""),
        ]
        for key, val in window_opts:  # best effort: older tmux may lack some
            _tmux("set-option", "-w", "-t", s, key, val, check=False)

        session_opts = [
            ("status", "on"),
            ("status-interval", "1"),
            ("status-style", "bg=black,fg=colour46"),
            ("status-left-length", "40"),
            ("status-left", "[ GHOST-SHIFT ] "),
            ("status-right-length", "90"),
            ("status-right", "%H:%M:%S  %a %d-%b-%Y "),
        ]
        for key, val in session_opts:
            _tmux("set-option", "-t", s, key, val, check=False)

        self.base = _tmux("list-panes", "-t", s, "-F", "#{pane_id}").splitlines()[0]
        self._set_base(self.idle)

    def set_status_extra(self, text: str) -> None:
        """Show extra text (e.g. the ticket totals) in the status bar."""
        self._status_extra = text
        safe = text.replace("#", "##")
        right = f"{safe}   " if safe else ""
        _tmux("set-option", "-t", self.session, "status-right",
              f"{right}%H:%M:%S  %a %d-%b-%Y ", check=False)

    # ------------------------------------------------------------ base pane
    def _command_for(self, mode: str) -> str:
        if mode == "syslog":
            return self.syslog_cmd
        if mode == "tickets":
            return (f"watch -t -n 5 {shlex.quote(sys.executable)} "
                    "-m ghost_shift.tickets --board")
        if mode == "clock":
            return "watch -t -n 1 date '+%H:%M:%S   %a %d %b %Y'"
        if mode == "matrix" and shutil.which("cmatrix"):
            return "cmatrix -ab -C green"
        if mode == "matrix":
            return self._command_for("clock")
        return "tail -f /dev/null"                    # "off": blank

    def _set_base(self, mode: str) -> None:
        args = ["respawn-pane", "-k", "-t", self.base]
        if self.project_dir:
            args += ["-c", str(self.project_dir)]
        _tmux(*args, self._command_for(mode), check=False)
        self.title(self.base, BASE_TITLES.get(mode, " "))

    # ---------------------------------------------------------------- queries
    def dims(self, pane: str) -> tuple[int, int]:
        w, h = _tmux(
            "display-message", "-p", "-t", pane, "#{pane_width} #{pane_height}"
        ).split()
        return int(w), int(h)

    def screen_width(self) -> int:
        return int(_tmux("display-message", "-p", "-t", self.session, "#{window_width}"))

    def title(self, pane: str, text: str) -> None:
        _tmux("select-pane", "-t", pane, "-T", text, check=False)

    # ----------------------------------------------------------- open / close
    def open(
        self,
        title: str,
        where: str = "top",
        anchor: str | None = None,
        size: float = 0.4,
        command: str | None = None,
        cwd: str | None = None,
    ) -> str:
        """Open a titled window and return its pane id.

        where: 'top' | 'bottom' | 'left' | 'right' (relative to anchor).
        size:  fraction of the anchor's width/height. When opening 'top' above
               the base pane, the window fills everything except the strip.
        command: program to run in the window (window closes when it exits);
                 omit for an interactive shell you can type into.
        """
        anchor = anchor or self.base
        top_level = where == "top" and anchor == self.base
        if top_level and not self._stages:
            self._set_base(self.strip)               # idle screen -> thin strip

        aw, ah = self.dims(anchor)
        horizontal = where in ("left", "right")
        before = where in ("top", "left")
        total = aw if horizontal else ah

        if top_level:
            final = total - self.strip_lines
        else:
            final = int(total * size)
        final = max(final, 6)
        start = min(3, final)

        args = [
            "split-window", "-d", "-P", "-F", "#{pane_id}", "-t", anchor,
            "-h" if horizontal else "-v",
        ]
        if before:
            args.append("-b")
        args += ["-l", str(start)]
        if cwd:
            args += ["-c", str(cwd)]
        if command:
            args.append(command)

        pane = _tmux(*args)
        self._horizontal[pane] = horizontal
        if top_level:
            self._stages.add(pane)
        self.title(pane, f"[ {title} ]")
        self._grow(pane, horizontal, start, final)
        _tmux("select-pane", "-t", pane, check=False)
        return pane

    def close(self, pane: str | None) -> None:
        """Shrink a window away, then kill it. Never touches the base pane."""
        if not pane or pane == self.base:
            return
        horizontal = self._horizontal.pop(pane, False)
        try:
            w, h = self.dims(pane)
            current = w if horizontal else h
        except Exception:
            current = 0   # already gone
        if current:
            if self.animate and current > 3:
                flag = "-x" if horizontal else "-y"
                steps = 8
                for i in range(1, steps + 1):
                    n = max(3, current - (current - 3) * i // steps)
                    _tmux("resize-pane", "-t", pane, flag, str(n), check=False)
                    time.sleep(self.step_delay)
            _tmux("kill-pane", "-t", pane, check=False)
        if pane in self._stages:
            self._stages.discard(pane)
            if not self._stages:
                self._set_base(self.idle)            # strip -> idle screen

    def cleanup(self) -> None:
        """Kill every window except the base. Call before and after scenes."""
        for pane in _tmux("list-panes", "-t", self.session, "-F", "#{pane_id}").splitlines():
            if pane != self.base:
                _tmux("kill-pane", "-t", pane, check=False)
        self._horizontal.clear()
        if self._stages:
            self._stages.clear()
            self._set_base(self.idle)

    def pulse_title(self, pane: str, text: str) -> Pulse:
        return Pulse(self, pane, text)

    # --------------------------------------------------------------- internal
    def _grow(self, pane: str, horizontal: bool, start: int, final: int) -> None:
        flag = "-x" if horizontal else "-y"
        if self.animate and final > start:
            steps = 10
            for i in range(1, steps + 1):
                eased = 1 - (1 - i / steps) ** 2  # ease-out
                n = start + int((final - start) * eased)
                _tmux("resize-pane", "-t", pane, flag, str(n), check=False)
                time.sleep(self.step_delay)
        _tmux("resize-pane", "-t", pane, flag, str(final), check=False)
