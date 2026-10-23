# Ghost Shift

**A 1990s hacker terminal that never repeats, run by a tiny AI on a Raspberry Pi.**

Ghost Shift is a 24/7 art installation. Plug a Raspberry Pi 5 into a monitor, start it, and walk away. The screen shows a retro terminal where an AI "programmer" works through its shift: it writes programs and runs them live, and it answers work email from a cast of difficult colleagues. Everything is typed line by line at human speed, mistakes included. All the writing is done by a small language model running **locally on the Pi**, so the piece needs no cloud account and keeps working offline.

<!-- TODO: add a screenshot or GIF here, e.g. docs/demo.gif -->

## What you see

Each scene plays out in separate, titled windows that grow out of the screen edge and shrink away when they are done.

**Code scenes**

| Window | What happens |
|---|---|
| **THINKING** (or NEURAL SYNTHESIS, COGNITION, PLANNING) | "Investigative" commands (`df -h`, `free -m`, `uptime`, ...) are typed with a live htop beside them |
| **EDITOR :: file.py** | The program is typed into `nano` at human speed, with typos and syntax mistakes that get noticed and fixed |
| **TESTING** (or EXECUTING, QA SANDBOX, RUNNING TESTS) | The finished program runs live: Game of Life, a Mandelbrot zoom, a packet simulator, ... |

**Mail scenes**

| Window | What happens |
|---|---|
| **MAIL :: N unread** | `mutt` opens a green inbox, the cursor scrolls to an unread message, and it is read |
| **COMPOSE :: RE: subject** | A reply is typed into `nano`, sent, and `mutt` quits |

Between scenes a **SYSLOG** strip stays visible along the bottom, and an optional **SCREENSAVER** window shows matrix-style green rain (needs `cmatrix`).

Programs come from a catalogue of 28 tasks at three difficulty levels. A shuffle bag makes sure none repeats until all have been shown, and random "voices" and vocabulary keep the code comments from sounding alike. The mail comes from seven recurring personas, such as a passive-aggressive ops lead, a chatty sysadmin, an alarmist security team, and a finance manager who distrusts every expense. Their emails sometimes refer to programs the AI actually wrote.

Planned: a night shift with Phrack-style zines and an IRC channel full of AI users (see the [roadmap](#roadmap)).

## How it works

The core idea is that **generation and display are separate.** A small model on a Pi manages only a few tokens per second, so the screen never waits on the AI live. A background worker keeps two queues full, and the director only takes finished items from them.

```
 generator_worker ──┬─► ready programs ──┐
   (local LLM via   │                    ├─► director_desk ──► tmux "desk" windows ──► monitor
    Ollama)         └─► unread mail  ────┘    (scenes, timing)   (typist types into them)
                        + prepared replies
```

| Module | Role |
|---|---|
| `local_llm.py` | Streaming client for Ollama with an idle timeout and a hard deadline |
| `codegen.py` | Chooses what program to write: task catalogue, shuffle bag, personas, vocabulary, prompts |
| `sandbox.py` | AST-based validator for generated Python (import allowlist, blocks dangerous modules) |
| `generator_worker.py` | Background process that keeps ready programs and unread mail topped up |
| `email_engine.py` | Writes persona emails into a real Maildir, each with a prepared reply |
| `email_scene.py` | The mutt scene: read a message, type the reply, send, quit |
| `director_desk.py` | Orchestrates the scenes and decides between code and mail |
| `desk.py` | Tiling window manager on tmux panes: titled windows that open and close with animation |
| `typist.py` | Human typing: bursts, neighbour-key typos, and syntax mistakes repaired on screen |
| `telemetry.py` | Wait-state typing of "investigative" shell commands |
| `stage.py` | tmux session setup and matrix rain |
| `util.py` | Shared helpers: file logging, tmux calls, polling |
| `config.py` | Loads `config.yaml` |

## Requirements

- Raspberry Pi 5 (16 GB recommended; a 3B model needs a few GB of RAM) with active cooling. NVMe storage is advised.
- Raspberry Pi OS based on Debian 13 (Trixie), which is the author's setup. Other Debian-based systems should work.
- [Ollama](https://ollama.com/download) with a small coding model (default `qwen2.5-coder:3b`).
- `tmux`, `nano`, `mutt`, and Python 3.11+. `install.sh` installs these, plus the optional `htop` and `cmatrix`.

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

# terminal 1: background generator (programs and mail)
python3 -m ghost_shift.generator_worker

# terminal 2: the show
python3 -m ghost_shift.director_desk --loop --no-rain
```

Flags for `director_desk`:

| Flag | Effect |
|---|---|
| `--loop` | Run forever |
| `--no-rain` | Skip the startup rain |
| `--no-anim` | No window grow/shrink animation |
| `--scene code` or `--scene mail` | Run only that kind of scene, handy for testing. A mail test creates an unread message if the inbox is empty |

`tmux attach` hides normal program output, so everything is logged to a file. To watch what is happening behind the scenes:

```bash
tail -f ~/.local/share/ghost-shift/ghost.log
```

Look for `task=... diff=...` (what is being written), `[llm] ... tok/s` (model speed), `popped program: source=...` (a fresh program, a replay, or the built-in fallback), and `scene: MAIL :: ...` (a mail scene). The worker needs a few minutes to prepare the first programs and emails on a Pi; until then the show replays older material or uses canned messages.

To preview the program prompts without calling the model, run `python3 -m ghost_shift.codegen`.

## Configuration

Everything lives in `config.yaml`, and every key is optional.

| Section | Keys | Notes |
|---|---|---|
| `llm` | `local_model`, `deadline_s` | The model must appear in `ollama list`, otherwise Ollama returns a 404 and the show falls back to replayed material |
| `typist` | `base_wpm`, `typo_chance`, `code_speed`, `mistake_chance`, `max_mistakes_per_block`, ... | Full list in the docstring at the top of `ghost_shift/typist.py`. `mistake_chance: 0` turns syntax mistakes off |
| `director` | `think_seconds`, `run_seconds` | Length of the THINKING window, and the hard cap on a live program run |
| `mail` | `enabled`, `every_min`, `every_max`, `target_unread`, `max_read` | A mail scene runs after every `every_min` to `every_max` code scenes when unread mail is waiting |
| `codegen` | `allowed_modules` | Imports the model is told it may use (the sandbox must allow them too) |
| `sandbox` | `allowed_modules`, `max_execution_time` | Static validator settings |
| `desk` | `animate`, `syslog_cmd` | Window animation, and what the SYSLOG strip shows |
| `system` | `workspace_dir`, `data_dir` | Where programs and data are stored |

Where things live:

```
~/workspace/                         programs the AI has written and run (named by task)
~/.local/share/ghost-shift/
  ghost.log                          the log
  codegen_state.json                 shuffle-bag state (delete it to reshuffle)
  commands_pool.json                 commands typed during THINKING
  library/ready, library/archive     queued and replayable programs
  mail/                              the Maildir that mutt opens (new, cur, tmp)
  mail-replies/                      prepared replies for unread mail
  mail-sent/                         copies of replies the AI "sent"
  muttrc, ghost-sendmail             generated mutt config and fake sendmail
```

## Safety

Ghost Shift **runs code written by an AI model**. The current protections are modest:

- Generated code is statically checked with `ast` and must stay within an import allowlist (`os`, `sys`, `subprocess`, `ctypes`, and similar are blocked).
- Programs run under a hard `timeout`.

The static check is not a security boundary. Run this on a dedicated Pi that holds nothing you care about, and keep API keys in environment variables, never in the repo. OS-level sandboxing (unprivileged user, resource limits, no network) is on the roadmap.

**No real email is sent.** The mail scene uses its own mutt config (your `~/.muttrc` is never touched), and its `sendmail` is replaced by a script that files each reply under `mail-sent/` instead of delivering it. The senders are fictional and use `.local` addresses.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Always the built-in fallback program | Check `ghost.log` for `generation attempt failed`. A 404 means the model name does not match `ollama list` |
| `ModuleNotFoundError: ghost_shift` | Run from the project root with `python3 -m ghost_shift.<module>` |
| Screen is stuck or garbled after a crash | `tmux kill-session -t ghost`, then start again |
| `*.save` files appear | nano was closed with unsaved changes; they are safe to delete |
| Windows look cramped | Side windows only open on screens at least 140 columns wide |
| `mutt did not start` in the log | Install it with `sudo apt install mutt` |
| `mail scene skipped: no unread mail` | The worker has not produced mail yet; test with `--scene mail`, which creates a message |
| The mail scene stops on an unexpected mutt prompt | Note the version with `mutt -v \| head -1`, then open an issue; the settings are in `ghost_shift/email_scene.py` |
| Start the mailbox over | `rm -r ~/.local/share/ghost-shift/mail*` (the worker reseeds it) |

## Roadmap

- [x] **Phase 1:** stage and typist (tmux window manager, human typing, matrix rain)
- [x] **Phase 2:** local LLM integration, background generation queue, AST sandbox
- [x] **Phase 3:** work emails (persona-driven Maildir, mutt scene with prepared replies, code and mail scheduler)
- [ ] **Phase 4:** cloud API offload (free-tier OpenAI-compatible providers with fallback)
- [ ] **Phase 5:** night shift (Phrack-style zines, day/night schedule, shift-change transitions)
- [ ] **Phase 6:** local IRC server with AI bot personas
- [ ] **Phase 7:** kiosk deployment (systemd services, console autologin, watchdog, nightly "patch window" reboot)

More detail is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

MIT. See [LICENSE](LICENSE).
