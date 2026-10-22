GHOST SHIFT: COMPLETE SYSTEM BRIEF & TECHNICAL DOCUMENTATION

1. System Vision & Core Operating Principles

Ghost Shift is a 24/7 autonomous terminal art installation running on a dedicated Raspberry Pi 5 (16GB RAM, NVMe storage, active cooling). It simulates a living 1990s computer environment operated by an AI entity across two distinct personas:

Day Shift (07:00–19:00): The IT Professional

Writes small utility programs (system monitors, ASCII clocks, log parsers, packet sniffers, bouncing ball visualizations).

Executes saved scripts in terminal windows as live visual dashboards.

Performs maintenance theater (df -h, free -m, uptime, tail -f logs, service restarts, fake system diagnostics).

Reads and responds to synthetic IT support tickets and corporate management emails using mutt and a local Maildir spool.

Night Shift (19:00–07:00): The Hacker Underground

Writes Phrack-style hacker zines (figlet/toilet banners, numbered .txt issues, rants, harmless pseudo-code exploits) paged with less.

Chats on a local-only IRC server (ngircd/ergo + irssi) with 4–8 AI bot personas.

Shift Changes & Maintenance

Matrix-style falling green code interludes (cmatrix).

Fake retro BIOS/boot logs transitioning into persona login prompts.

Nightly 04:00 system reboot staged as a "scheduled patch window".

Primary Architecture Principle: Separate Generation from Display

Local LLM generation on the Raspberry Pi 5 runs at ~2–8 tokens/second. The display path must never stall, flicker, or go blank:

Background Generator Worker (generator_worker.py): Pre-generates, validates, and queues content into ~/.local/share/ghost-shift/library/ready/.

Stage & Typist (typist.py / director_desk.py): Replays queued items with realistic human typing simulation into active tmux windows.

Fail-Safe Replay: If queues deplete or models fail, the system falls back to archived programs, previous emails, or maintenance filler.

2. System Environment & Execution Constraints

Target Hardware: Raspberry Pi 5 (16GB RAM, NVMe boot drive).

OS / Base Image: Debian 13 / Trixie-based Raspberry Pi OS.

Project Root: ~/ghost-shift/

Virtual Environment: ~/ghost-shift/venv/

Package Name: ghost_shift (~/ghost-shift/ghost_shift/)

Execution Protocol: All commands must be executed as Python modules from the project root:

cd ~/ghost-shift && source venv/bin/activate
python3 -m ghost_shift.<module_name>


Delivery Style: Deliver code via copy-paste cat << 'EOF' > path blocks or patch scripts.

3. Complete Codebase & File Map

/home/ed/
├── workspace/                       # Executed runtime Python scripts (sys_monitor_*.py)
├── .local/share/ghost-shift/        # Data storage & library cache
│   ├── library/
│   │   ├── ready/                  # Validated scripts ready for display
│   │   └── archive/                # Historical replay archives
│   ├── mail/
│   │   ├── new/                    # Incoming synthetic Maildir emails
│   │   ├── cur/                    # Processed / read emails
│   │   └── tmp/
│   ├── commands_pool.json          # Investigative typing command pool
│   ├── codegen_state.json          # Task shuffle-bag state tracking
│   └── ghost.log                   # Persistent system log file
│
└── ghost-shift/                    # PROJECT ROOT
    ├── README.md                   # Full repository documentation
    ├── README_HANDOFF.md           # This comprehensive system brief
    ├── config.yaml                 # Master system configuration
    ├── requirements.txt            # Dependencies (PyYAML, psutil)
    ├── install.sh                  # Setup script
    ├── .gitignore                  # Git exclude list
    └── ghost_shift/                # Core Python Package
        ├── __init__.py             # Package marker
        ├── config.py               # Config YAML loader
        ├── codegen.py              # Task shuffle-bag prompt engine
        ├── desk.py                 # Tiling tmux window layout manager
        ├── director_desk.py        # Master Director orchestration loop
        ├── email_engine.py         # Corporate IT email generator
        ├── email_scene.py          # Interactive mutt display & reply scene
        ├── generator_worker.py     # Background queue generator worker
        ├── local_llm.py            # Fast streaming Ollama HTTP client
        ├── sandbox.py              # AST-based Python code validator
        ├── stage.py                # Tmux session initialization & matrix rain
        ├── telemetry.py            # Wait-state investigative typing commands
        └── typist.py               # Human typing engine with mistakes/repairs


Detailed Module Descriptions

ghost_shift/config.py: Loads configuration settings from config.yaml.

ghost_shift/local_llm.py: Streaming HTTP client communicating directly with Ollama (http://localhost:11434/api/generate). Avoids CLI subprocess timeouts. Features strip_noise() to strip thinking blocks and markdown wrappers.

ghost_shift/sandbox.py: Uses ast.parse() to statically validate generated Python scripts. Strips backticks and enforces security restrictions (blocking os, sys, subprocess, shutil, ctypes) while allowing standard libraries (time, random, math, curses, psutil).

ghost_shift/codegen.py: Manages a persistent task shuffle-bag (28 tasks across 3 difficulty tiers) so prompts never repeat until all tasks are displayed. Implements comment scrubbing, random visual styles, variable execution lengths, and fallback script generation.

ghost_shift/generator_worker.py: Independent background process that continuously invokes local_llm.py, validates scripts via sandbox.py, and maintains a ready queue inside ~/.local/share/ghost-shift/library/ready/.

ghost_shift/typist.py: Simulates realistic human typing into tmux using character bursts, variable WPM, neighbor-key typos, and syntax error self-repairs (misspellings, missing colons/brackets, incorrect equality operators).

ghost_shift/desk.py: Manages tiled tmux window layouts, titled window status borders, pane splitting, dynamic window expansion/decay, and thinking animations.

ghost_shift/telemetry.py: Drives human-like investigative commands (df -h, free -m, uptime, ps aux, ls -la) during generation wait states using commands_pool.json.

ghost_shift/email_engine.py: Generates synthetic corporate IT emails (support tickets, server alerts, quota warnings) using local_llm.py and formats them into standard RFC-822 messages stored directly in Maildir (~/.local/share/ghost-shift/mail/new/).

ghost_shift/email_scene.py: Executes the visual email scene inside tmux: opens mutt, navigates the unread message, simulates reading, pre-generates a concise reply with generate_local, and updates message status to cur/.

ghost_shift/director_desk.py: The main orchestration loop connecting all components: runs wait-state telemetry $\rightarrow$ pops pre-generated programs from generator_worker $\rightarrow$ opens nano $\rightarrow$ types code line-by-line $\rightarrow$ executes in sandbox window $\rightarrow$ runs interludes.

4. System Configuration Reference (config.yaml)

system:
  workspace_dir: "~/workspace"
  data_dir: "~/.local/share/ghost-shift"
  terminal:
    font: "Lat2-Terminus16"
    color_scheme: "amber"

llm:
  local_model: "qwen2.5-coder:3b"
  deadline_s: 2400

codegen:
  allowed_modules: ["time", "random", "math", "psutil", "curses"]

desk:
  animate: true
  syslog_cmd: "tail -n 40 -F ~/.local/share/ghost-shift/ghost.log"

typist:
  base_wpm: 65
  variance: 25
  typo_chance: 0.04
  code_typo_chance: 0.12
  code_speed: 3.0
  burst: 3
  mistake_chance: 0.15
  max_mistakes_per_block: 5
  notice_min: 0.1
  notice_max: 0.3
  pause_punctuation: 0.4
  pause_newline: 0.8
  correction_delay_min: 0.1
  correction_delay_max: 0.3


5. Critical Resolved Issues & Safeguards

Ollama Process Lockup: Replaced ollama run CLI subprocess calls with a direct streaming HTTP API client (local_llm.py).

Nano Buffer Race Conditions: Added key sequence delay buffers and process state verification (wait_until) before exiting nano to eliminate .save backup files.

Autoindent Mangling: nano is explicitly launched with -I (nano -I -E -l -w) to disable auto-indentation during automated typing.

Typist Telemetry Overlap: Fixed thread join behavior using /tmp/ghost_llm_ready.flag so investigative typing immediately yields when a payload is ready.

Tmux Escape Sequences: Semicolons and special characters are escaped (\;) to avoid tmux send-keys argument parsing failures.

6. System Operation Commands

Running the Full System

cd ~/ghost-shift && source venv/bin/activate

# Terminal 1: Background Queue Worker
python3 -m ghost_shift.generator_worker

# Terminal 2: Master Director Display
python3 -m ghost_shift.director_desk --loop --no-rain


Testing Work Email Integration

cd ~/ghost-shift && source venv/bin/activate

# 1. Generate new IT mail item into Maildir spool
python3 -m ghost_shift.email_engine

# 2. Initialize ghost tmux session
python3 -c "from ghost_shift.stage import init_tmux_session; init_tmux_session('ghost')"

# 3. Run interactive mutt email scene
python3 -m ghost_shift.email_scene


Monitoring System Logs

tail -f ~/.local/share/ghost-shift/ghost.log


7. Remaining Implementation Roadmap

Phase 4: Cloud API Router Offloading

Build an OpenAI-compatible fallback router (LiteLLM or custom) chaining free cloud providers (Groq, Gemini, Cerebras, OpenRouter) down to local Ollama.

Phase 5: Night Shift Persona & Hacker Zines

Implement Phrack-style text zine generator (figlet/toilet banners, numbered .txt files in ~/.local/share/ghost-shift/zines/) and less pager viewer scene.

Phase 6: Local IRC Server & Multi-Bot Chatters

Configure local ngircd/ergo server and irssi client scene. Run 4–8 automated background IRC personas exchanging technical banter, topic changes, and netsplits.

Phase 7: Kiosk Deployment & System Hardening

Configure Linux console autologin, systemd services with hardware watchdog (Restart=always), sandboxed unprivileged execution (bwrap/firejail), workspace pruning, and automated nightly reboots.
