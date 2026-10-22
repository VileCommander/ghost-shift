import threading
import time
import subprocess
from ghost_shift.config import load_config
from ghost_shift.stage import init_tmux_session, run_matrix_rain
from ghost_shift.typist import Typist

config = load_config()

# 1. Matrix Rain Interlude (Full screen)
print("Initializing Matrix Rain interlude...")
run_matrix_rain(3)

# 2. Init Full-Screen Session
print("Initializing full-screen tmux session...")
init_tmux_session("ghost")

typist = Typist(config)

def dynamic_workflow():
    time.sleep(2.0)
    
    # Scene A: Writing code full-screen in nano
    typist.type_text("ghost", "nano test_program.py\n")
    time.sleep(1.5)
    typist.type_text("ghost", "# System monitor heartbeat\nimport time\nwhile True:\n    print('SYSTEM OK - MEM: 42% - LOAD: 0.12')\n    time.sleep(2)\n")
    time.sleep(1)
    
    # Save and exit nano (Ctrl+O, Enter, Ctrl+X)
    subprocess.run(["tmux", "send-keys", "-t", "ghost", "C-o", "Enter", "C-x"], check=True)
    time.sleep(1)
    
    # Scene B: Clear screen and run the program full-frame like a true terminal artifact
    typist.type_text("ghost", "clear && python3 test_program.py\n")

# Run the dynamic sequence in the background
t = threading.Thread(target=dynamic_workflow)
t.start()

print("Attaching to full-screen session immediately...")
time.sleep(0.5)

# Attach immediately to watch the dynamic full-screen performance
subprocess.run(["tmux", "attach", "-t", "ghost"])
