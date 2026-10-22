# Ghost Shift

**A 1990s hacker terminal that never repeats, run by a tiny AI on a Raspberry Pi.**

Ghost Shift is a 24/7 art installation. Plug a Raspberry Pi 5 into a monitor, start it, and walk away. The screen shows a retro terminal where an AI "programmer" works through its shift: it thinks, opens an editor, types out a program line by line (making and fixing realistic mistakes along the way), and runs it live. Every program is written by a small language model running **locally on the Pi**, so the piece needs no cloud account and keeps working offline.

<!-- TODO: add a screenshot or GIF here, e.g. docs/demo.gif -->

## What you see

Each cycle is a short play in separate, titled windows that grow out of the screen edge and shrink away when they are done:

| Window | What happens |
|---|---|
| **THINKING** (or NEURAL SYNTHESIS, COGNITION, PLANNING) | "Investigative" commands (`df -h`, `free -m`, `uptime`, ...) are typed while the model works, with a live htop beside them |
| **EDITOR :: file.py** | The program is typed into `nano` line by line at human speed, with typos and syntax mistakes that get noticed and fixed |
| **TESTING** (or EXECUTING, QA SANDBOX, RUNNING TESTS) | The finished program runs live: Game of Life, a Mandelbrot zoom, a packet simulator, ... |
| **SCREENSAVER** | Matrix-style green rain between scenes (needs `cmatrix`) |
| **SYSLOG** | A log strip that always stays visible along the bottom |

Programs come from a catalogue of 28 tasks at three difficulty levels. A shuffle bag makes sure none repeats until all have been shown, and random "voices" and vocabulary keep the code comments from sounding the same.

Planned: a day/night schedule with work emails by day, and Phrack-style zines plus an IRC channel full of AI users by night (see the [roadmap](#roadmap)).

## How it works

The core idea is that **generation and display are separate.** A small model on a Pi manages only a few tokens per second, so the screen never waits on the AI live.

```
 generator_worker ──► validated programs ──► director_desk ──► tmux "desk" windows ──► monitor
   (local LLM via        (library/ready)       (scenes, timing)    (typist types into them)
    Ollama, sandbox
    validation)
```

| Module | Role |
|---|---|
| `local_llm.py` | Streaming client for Ollama with an idle timeout and a hard deadline; strips thinking blocks and markdown from the output |
| `codegen.py` | Chooses what to write: task catalogue, shuffle bag, personas, vocabulary, prompt building |
| `sandbox.py` | AST-based validator for generated Python (import allowlist, blocks dangerous modules) |
| `generator_worker.py` | Background process that keeps a queue of ready-to-show programs |
| `director_desk.py` | Orchestrates the scenes |
| `desk.py` | Tiling window manager on tmux panes: titled windows that open and close with animation |
| `typist.py` | Human typing: bursts, neighbour-key typos, and syntax mistakes repaired on screen |
| `telemetry.py` | Wait-state typing of "investigative" shell commands |
| `stage.py` | tmux session setup and matrix rain |
| `email_engine.py`, `email_scene.py` | Work-email scene with `mutt` (in progress) |
| `config.py` | Loads `config.yaml` |

## Requirements

- Raspberry Pi 5 (16 GB recommended; a 3B model needs a few GB of RAM) with active cooling. NVMe storage is advised.
- Raspberry Pi OS based on Debian 13 (Trixie), which is the author's setup. Other Debian-based systems should work.
- [Ollama](https://ollama.com/download) with a small coding model (default `qwen2.5-coder:3b`).
- `tmux`, `nano`, and Python 3.11+. `install.sh` installs what it can; `htop`, `cmatrix`, and `mutt` are optional extras it also installs.

## Quick start

```bash
git clone https://github.com/VileCommander/ghost-shift.git
cd ghost-shift
./install.sh                      # system packages + Python virtualenv
# install Ollama from https://ollama.com/download, then:
ollama pull qwen2.5-coder:3b
```

Run it from the project root, as Python modules:

```bash
cd ~/ghost-shift && source venv/bin/activate

# terminal 1: background generator
python3 -m ghost_shift.generator_worker

# terminal 2: the show
python3 -m ghost_shift.director_desk --loop --no-rain
```

Flags for `director_desk`: `--loop` (run forever), `--no-rain` (skip the startup rain), `--no-anim` (no window grow/shrink animation).

`tmux attach` hides normal program output, so everything is logged to a file. To watch what is happening behind the scenes:

```bash
tail -f ~/.local/share/ghost-shift/ghost.log
```

Look for `task=... diff=...` (what is being written), `[llm] ... tok/s` (model speed), and `program source: llm`, `archived`, or `static` (real AI output, a replayed program, or the built-in fallback). The first program can take several minutes on a Pi while the model writes it.

To preview the prompts without calling the model, run `python3 -m ghost_shift.codegen`.

## Configuration

Everything lives in `config.yaml`, and every key is optional.

| Section | Keys | Notes |
|---|---|---|
| `llm` | `local_model`, `deadline_s` | The model must appear in `ollama list`, otherwise Ollama returns a 404 and the show falls back to replayed programs |
| `typist` | `base_wpm`, `typo_chance`, `code_speed`, `mistake_chance`, `max_mistakes_per_block`, ... | Full list in the docstring at the top of `ghost_shift/typist.py`. `mistake_chance: 0` turns syntax mistakes off |
| `codegen` | `allowed_modules` | Imports the model is told it may use (the sandbox must allow them too) |
| `sandbox` | `allowed_modules`, `max_execution_time` | Static validator settings |
| `desk` | `animate`, `syslog_cmd` | Window animation, and what the SYSLOG strip shows |
| `system` | `workspace_dir`, `data_dir` | Where programs and data are stored |

Where things live:

```
~/workspace/                         programs the AI has written and run
~/.local/share/ghost-shift/
  ghost.log                          the log
  codegen_state.json                 shuffle-bag state (delete it to reshuffle)
  commands_pool.json                 commands typed during THINKING
  library/ready, library/archive     queued and replayable programs
  mail/                              synthetic Maildir for the email scene
```

## Safety

Ghost Shift **runs code written by an AI model**. The current protections are modest:

- Generated code is statically checked with `ast` and must stay within an import allowlist (`os`, `sys`, `subprocess`, `ctypes`, and similar are blocked).
- Programs run under a hard `timeout`.

The static check is not a security boundary. Run this on a dedicated Pi that holds nothing you care about, and keep API keys in environment variables, never in the repo. OS-level sandboxing (unprivileged user, resource limits, no network) is on the roadmap.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Always the built-in fallback program | Check `ghost.log` for `generation attempt failed`. A 404 means the model name does not match `ollama list` |
| `ModuleNotFoundError: ghost_shift` | Run from the project root with `python3 -m ghost_shift.<module>` |
| Screen is stuck or garbled after a crash | `tmux kill-session -t ghost`, then start again |
| `*.save` files appear | nano was closed with unsaved changes; they are safe to delete |
| Windows look cramped | Side windows only open on screens at least 140 columns wide |

## Roadmap

- [x] **Phase 1:** stage and typist (tmux window manager, human typing, matrix rain)
- [x] **Phase 2:** local LLM integration, background generation queue, AST sandbox
- [ ] **Phase 3:** work emails (Maildir spool and `mutt` scene built; director integration in progress)
- [ ] **Phase 4:** cloud API offload (free-tier OpenAI-compatible providers with fallback)
- [ ] **Phase 5:** night shift (Phrack-style zines, day/night schedule, shift-change transitions)
- [ ] **Phase 6:** local IRC server with AI bot personas
- [ ] **Phase 7:** kiosk deployment (systemd services, console autologin, watchdog, nightly "patch window" reboot)

More detail is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

MIT. See [LICENSE](LICENSE).
