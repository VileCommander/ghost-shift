# GHOST SHIFT: HANDOFF BRIEF

## 1. What this is
An art installation on a Raspberry Pi 5 (16 GB, NVMe, active cooler) plugged into a monitor 24/7. It looks like a living 1990s computer used by an AI character. Nothing interacts with it. It must never look the same twice and must run unattended for months.

**Full vision (only part is built):**
- **Day shift (about 07:00-19:00), an IT professional:** writes small programs and saves them to a growing workspace, runs saved programs as dashboards or clocks, answers emails from AI management and coworkers (local Maildir plus mutt), and does maintenance theater (tail logs, df, fake outages).
- **Night shift (about 19:00-07:00), the hacker underground:** writes Phrack-style zines (figlet banners, numbered .txt issues, paged with less) and chats on a local IRC server (ergo or ngircd, in irssi) with 4-8 AI bot personas.
- **Shift changes:** Matrix green rain, then a fake boot log, then a login as the next persona. A nightly 04:00 reboot is staged as a "patch window".
- **Core principle:** separate GENERATION from DISPLAY. The Pi's local LLM only manages about 2-8 tokens/s, so a Generator produces content in the background while a Stage replays it with human-like typing. The screen must never stall or go blank (replay old content as a fallback).
- **Model plan:** a small local model via Ollama (default `qwen2.5-coder:3b`; the user previously tried `qwen3.5:4b` and `qwen2.5-coder:7b`) for short or private tasks. Free cloud APIs (Groq, Gemini, Cerebras, OpenRouter `:free`, Mistral, GitHub Models) for heavy tasks. Plan: an OpenAI-compatible router with a fallback chain, rate-limit tracking, and model names kept in config because free tiers change without notice. Cloud prompts must never contain secrets.

## 2. Environment and working style
- **Hardware and OS:** Pi 5 16 GB. Currently the full Raspberry Pi desktop accessed over WayVNC, with the final target being console kiosk. A screenshot showed GNU nano 8.4, which suggests a Debian 13/Trixie-based Pi OS, not Bookworm. tmux version not verified.
- **Layout:** project root `~/ghost-shift/` contains `config.yaml`, `venv/`, `workspace/`, `install.sh`, `requirements.txt`, `test_program.py`. The Python package is `~/ghost-shift/ghost_shift/`. **Always run as a module from the project root**: `python -m ghost_shift.<name>`.
- **The user can only copy-paste.** They cannot download files. Deliver code as `cat > path <<'EOF' ... EOF` blocks, and edits as small tested patch scripts.
- **Known stray files in the root:** `ghost_shift.director_phase2_test` (extensionless leftover), `test_program.py.save*` (nano emergency backups), `test_program.py`. Safe to delete.

## 3. Files in `~/ghost-shift/ghost_shift/`

**Original (user's, mostly unchanged, I have not seen all of them):**
- `config.py`: `load_config()`.
- `queue.py`: `ContentQueue().push(kind, content, filename)`.
- `stage.py`: `init_tmux_session(name)`, `run_matrix_rain(seconds)`.
- `sandbox.py`: `validate_code(code)` returns a 3-tuple `(_, _, cleaned_code)`. It is AST-based, strips markdown fences, and blocks os, sys, subprocess, shutil, ctypes and similar. **The exact allowlist is unknown**; time, random, math, curses and psutil are known to be allowed.
- `telemetry.py`: `run_investigative_typing(session_name, typist)` types commands from a pool (`~/.local/share/ghost-shift/commands_pool.json`, defaults like df -h, free -m, uptime) while the LLM works. It polls the flag file `/tmp/ghost_llm_ready.flag` between commands. It also does `Path("workspace").mkdir()` relative to cwd (harmless but messy).
- `router.py`: OLD. It shells out to `ollama run` and **swallows errors, returning its own canned script** ("DECK TELEMETRY" text), which is why the user originally saw only fallbacks. It is now bypassed.
- `cleaner.py`, `director_phase1_test.py`, `director_phase2.py`: old.

**Written in this conversation (delivered via paste commands; the user confirmed the desk and generation flow runs, so confirm the later files below with `ls`):**
- `local_llm.py`: streaming Ollama HTTP client.
  - `generate_local(prompt, model, system=None, max_tokens=700, total_deadline=2400, idle_timeout=300, num_thread=3, num_ctx=2048, temperature=0.8, on_token=None, log=print)`.
  - It fails only on idle (no tokens for 5 minutes) or a hard 40-minute deadline.
  - It sends `think:false` (and retries without it on HTTP 400), `keep_alive:-1`, and `num_predict` caps.
  - It logs real tokens/s.
  - `strip_noise()` removes think blocks, markdown fences and chatty preambles.
- `director_phase2_test.py` (revised): the older single-pane director. It also exports shared helpers used by the newer one: `log` (writes to `~/.local/share/ghost-shift/ghost.log`, because stdout is invisible under `tmux attach`), `wait_until`, `SHELLS`, `RUN_SECONDS=150`, `STOP_FLAG`, `FALLBACK_CODE`. Its own `generate_program` and `fallback_program` are superseded by `codegen.py`.
- `desk.py`: a tiling "window manager" on tmux panes.
  - A permanent SYSLOG base pane, with a 9-line strip left visible.
  - Titled windows (`pane-border-status top`, double borders, `allow-set-title off`).
  - `open(title, where, anchor, size, command, cwd)` returns a pane id.
  - Windows grow out of the screen edge and shrink away. `close()` never touches the base. `cleanup()` kills all non-base panes. `pulse_title()` animates `[ THINKING...  02:41 ]`.
- `director_desk.py`: the main director.
  - Run with `python -m ghost_shift.director_desk [--loop] [--no-rain] [--no-anim]`.
  - **Per-cycle scenes:**
    1. THINKING (titles are random: THINKING, NEURAL SYNTHESIS, COGNITION, PLANNING): the telemetry typing runs here, plus an htop window "NEURAL LOAD" on the right if the screen is 140 columns or wider.
    2. EDITOR (`nano -I -E -l -w file`): the code is typed, saved with pauses (C-o, Enter, C-x), nano exit is confirmed, and the file is rewritten from the canonical code if the buffer differs (compared with `.strip()`).
    3. TESTING (or EXECUTING, QA SANDBOX, RUNNING TESTS): the program runs under `timeout 150 python3 file`, with an htop "SYSTEM LOAD" window.
    4. SCREENSAVER: `cmatrix` interlude if installed.
  - All typing targets pane ids, not the session name.
- `codegen.py`: the prompt and task engine.
  - 28 tasks across 3 difficulty levels (1 easy, 2 medium, 3 hard), each with a one-sentence implementation hint.
  - A persistent SHUFFLE BAG so nothing repeats until all have been shown. State is in `~/.local/share/ghost-shift/codegen_state.json`.
  - Random comment persona, 5 random vocabulary words (avoiding recent ones), a banned-word list (heap, buffer, allocate, neural, quantum) plus a comment scrubber, random visual style, and random run length (45-90 s) and frame delay.
  - No example comments in the prompt (an earlier example, `# [ALLOCATING HEAP BUFFER]`, was copied verbatim by the model and caused repetition).
  - Attempt 1 is a full-size task (70 lines, 1100 tokens); on failure, attempt 2 is a random EASY task (40 lines, 650 tokens).
  - API: `generate_program(config)` returns code or None, `fallback_program(workspace)` returns `(code, "archived"|"static")`, `slug()`.
  - Default allowed imports are time, random and math, overridable with `codegen.allowed_modules`.
  - `python -m ghost_shift.codegen` prints sample prompts without calling the model.
  - **`director_desk.py` was patched by a script** to import `generate_program` and `fallback_program` from `codegen` and to name files `{slug}_{timestamp}_{4hex}.py`. If `grep -c "ghost_shift.codegen" director_desk.py` prints 0, the patch is not applied.
- `typist.py` (v3, replaces the user's original):
  - Burst typing of 1-5 characters per tmux call, with code typed at 3x the shell-command speed.
  - Indentation is sent instantly.
  - Neighbor-key typos.
  - Syntax mistakes in code blocks that get noticed and repaired:
    - `misspell`: retrun, pritn, true; fixed at line end by walking Left, BSpace, retype, End.
    - `eq`: `==` typed as `=`.
    - `missing`: a forgotten colon, bracket or quote, fixed after Enter via Up, End, type, Down.
    - `closer`: the wrong closing bracket, backspaced and corrected.
  - Defaults: 15% of lines get a mistake, capped at 5 per block.
  - Config keys under `typist:` (all optional): base_wpm, variance, typo_chance, code_typo_chance, code_speed, burst, mistake_chance, max_mistakes_per_block, notice_min, notice_max, pause_punctuation, pause_newline, correction_delay_min, correction_delay_max.
  - **A `typist:` section already in the user's `config.yaml` overrides these defaults.**

## 4. Config keys in use
```yaml
llm:
  local_model: qwen2.5-coder:3b   # must exist in `ollama list`, else 404 means fallback
  deadline_s: 2400
codegen:
  allowed_modules: [time, random, math]
system:
  workspace_dir: ~/workspace      # default; note ~/ghost-shift/workspace also exists
desk:
  animate: true
  syslog_cmd: "tail -n 40 -F ~/.local/share/ghost-shift/ghost.log"
typist: {}                        # see keys above
```

## 5. Bugs found and fixed (don't reintroduce)
1. The `ollama run` subprocess through `router.py` gave timeouts, hidden fallbacks and 4 cores pinned. It is replaced by the streaming HTTP client.
2. The director's 3-second join of the telemetry thread let it keep typing into nano. The new code waits up to 90 s and then clears the flag.
3. Sending C-o, Enter, C-x as one burst raced with nano, which is how the `.save` emergency files appeared. The new code pauses between keys and confirms nano exited before touching the file.
4. A user nanorc with autoindent would mangle typed code, so nano is launched with `-I`.
5. tmux attached after typing started, so the pane resized mid-typing. The worker now waits for `session_attached`.
6. The old typist's `code.replace("\\n", "\n")` broke any code containing `"\n"` in a string. It now only un-escapes a single-line input.
7. A literal LF (Ctrl-J) was sent instead of the Enter key. In nano, Ctrl-J is Justify. Enter is now sent as the key.
8. tmux treats an argument ending in `;` as a command separator, so semicolons were likely dropped. The new code sends `\;`. A literal argument starting with `-` is split so tmux doesn't parse it as an option.
9. Static fallback programs were pushed to the content queue as if they were LLM output. Only real output is pushed now.

## 6. Verified vs unverified
- **Confirmed by the user on the real Pi:** the desk windows, the streaming LLM path generating code, and the prompt repetition complaint (which led to `codegen.py`).
- **Tested only against a mock tmux or a simulated nano (my sandbox had no tmux):**
  - The `desk.py` open/close logic.
  - The typist: 300 heavy-mistake runs with 0 buffer mismatches, edge cases for `;`, leading `-`, quotes and braces, and about 5x faster typing (278 s down to 50 s for a 58-line program, scheduled delay only).
  - The codegen shuffle bag and comment scrubber.
- **OPEN ITEM (resolve first):** the real-nano typist test printed `DIFFERENT`, but the pasted output looked identical to the intended code.
  - The most likely cause is a trailing-newline difference in the saved file. That is harmless, because the director compares with `.strip()`.
  - It is NOT yet confirmed. The user has not run the diagnostic.
  - The diagnostic prints `got == code`, `got.strip() == code.strip()`, the last 12 characters of each, the first differing index, and `cat -A /tmp/typist_test.py`.
  - If the strip comparison is also False, a Left/Up/End/Down repair misbehaves in real nano. Then fix the key handling in `typist.py` `_fix_in_line` or `type_code_block`.
  - Note: I wrongly said "that matches" once before the user pasted a result, so verify rather than assume.
- **Also unverified:** whether `codegen.py` and its patch to `director_desk.py` are applied on the Pi, whether the user's `config.yaml` has an overriding `typist:` section, the real tokens/s of the chosen model (check `[llm] ... tok/s` in `ghost.log`), and the real success rate of difficulty-3 tasks on a 3B model (check the `task=... diff=...` log lines).

## 7. Operating it
```bash
cd ~/ghost-shift && source venv/bin/activate
tail -f ~/.local/share/ghost-shift/ghost.log                  # second terminal
python -m ghost_shift.director_desk --no-rain                 # one cycle (add --loop for forever)
```
Log lines to look for: `task=<slug> diff=N`, `[llm] ... tok/s`, `program source: llm|archived|static`, `generation attempt failed: ...`, `nano buffer differed ...`.
Optional installs: `sudo apt install -y htop cmatrix`. Reset the no-repeat state with `rm ~/.local/share/ghost-shift/codegen_state.json`.

## 8. Remaining roadmap (suggested order)
1. Resolve the typist diagnostic in section 6.
2. **Decouple generation from the show.** Build a background Generator worker (nice 10, CPU affinity cores 0-2, the Stage on core 3) that keeps a `library/ready/` queue of validated programs, plus an `archive/` for replay and "edit" scenes. Right now generation happens inline during the THINKING scene (about 5 minutes for a hard task). Also suggested but not confirmed applied: an Ollama systemd override (`OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`, `CPUAffinity=0 1 2`, `Nice=10`) and warming the model at boot.
3. **Cloud offload.** An OpenAI-compatible router with a fallback chain (cloud first for code, then local, then archive replay), per-provider requests-per-minute and per-day tracking with backoff on 429, and model names in config. Consider LiteLLM.
4. A "deliberate bug" scene: leave one real bug in, save, run, show the real traceback in the TESTING window, reopen the editor, and fix it (needs the sandbox to allow one deliberate failure per cycle).
5. The day/night schedule and shift-change transitions (Matrix rain, fake boot, login), a persona file (YAML), daily-summary memory in SQLite, and random events.
6. Mail scene (Maildir plus mutt with persona-driven replies), IRC scene (ergo or ngircd plus irssi plus a bot-runner with personas and join/quit/netsplit events), and a zine writer (figlet or toilet banners, numbered issues).
7. Hardening: sandbox generated code as an unprivileged user (bwrap, firejail or `systemd-run`) with CPU, memory, no-network and wall-clock limits; systemd units with `Restart=always` and the hardware watchdog; tmpfs for logs and scratch; workspace pruning; console autologin kiosk; OLED burn-in shifting; a nightly reboot staged as a patch window; a `status` command.

## 9. Constraints to keep
- Python 3.11+, minimal dependencies (`requests`, `pyyaml`, `psutil` plus the standard library). Everything configurable in `config.yaml`, secrets only via environment variables.
- Generated and typed code must stay harmless. Zine content is fictional and non-operational.
- The display path must stay smooth while the model generates, so limit Ollama threads to 3.
- Deliver changes as paste-ready heredocs or small patch scripts, and test them in a sandbox first where possible.
