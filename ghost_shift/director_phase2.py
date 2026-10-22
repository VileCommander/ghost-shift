"""
ghost_shift/director_phase2.py
------------------------------
This script is the master coordinator for Phase 2. 
It orchestrates the full sequence of the art installation:
1. Plays the Matrix rain interlude.
2. Initializes a clean full-screen tmux session.
3. Requests an AI-generated retro script from the LLM Router.
4. Runs the CodeValidator sandbox check to ensure safety.
5. Saves the script into the workspace directory with a unique filename.
6. Uses the Typist module to open 'nano' full-screen and type the code like a human.
7. Automatically saves and exits nano, then clears the screen and runs the script live.
"""

import threading
import time
import subprocess
import uuid
from pathlib import Path

# Import our modular Ghost Shift components
from ghost_shift.config import load_config
from ghost_shift.router import LLMRouter
from ghost_shift.sandbox import validate_code
from ghost_shift.queue import ContentQueue
from ghost_shift.stage import init_tmux_session, run_matrix_rain
from ghost_shift.typist import Typist

def main():
    # Load configuration from config.yaml
    config = load_config()
    
    # Initialize our core tools
    router = LLMRouter(config)
    queue = ContentQueue()
    typist = Typist(config)

    print("[*] Starting Phase 2 workflow...")

    # Step 1: Play Matrix rain interlude for 3 seconds
    print("[*] Initializing Matrix Rain interlude...")
    run_matrix_rain(3)

    # Step 2: Initialize a full-screen tmux session named 'ghost'
    print("[*] Initializing full-screen tmux session...")
    init_tmux_session("ghost")

    def ai_coding_workflow():
        # Give tmux a moment to render after attaching
        time.sleep(2.0)
        
        # Step 3: Ask the LLM Router to write a retro program
        prompt = "Write a short, standalone Python script for a retro terminal system monitor or digital clock using time and random modules. Output ONLY python code."
        print("[*] Requesting code generation from router...")
        code = router.generate("code", prompt)
        
        # Step 4: Validate code safety using our sandbox AST checker
        is_safe, violations = validate_code(code)
        if not is_safe:
            print(f"[-] Code failed sandbox checks: {violations}")
            # Fallback safe script if violations are found
            code = '''import time\nwhile True:\n    print("SECURE MODE: SYSTEM NOMINAL")\n    time.sleep(2)'''
        else:
            print("[+] Code passed sandbox security checks.")
            
        # Step 5: Save the code to ~/workspace/ with a unique filename to avoid overwrites
        workspace_path = config.get("system", {}).get("workspace_dir", "~/workspace")
        workspace = Path(workspace_path).expanduser()
        workspace.mkdir(parents=True, exist_ok=True)
        
        unique_suffix = uuid.uuid4().hex[:6]
        filename = f"sys_monitor_{int(time.time())}_{unique_suffix}.py"
        file_path = workspace / filename
        
        with open(file_path, "w") as f:
            f.write(code)
            
        # Store in our SQLite content queue history
        queue.push("code", code, filename)
        print(f"[*] Saved artifact to {file_path}")
        
        # Step 6: Open full-screen nano and type the code with human cadence
        print("[*] Opening nano and typing code...")
        typist.type_text("ghost", f"nano {file_path}\n")
        time.sleep(1.0)
        typist.type_text("ghost", code)
        time.sleep(1.0)
        
        # Send nano keyboard shortcuts to save and exit (Ctrl+O, Enter, Ctrl+X)
        subprocess.run(["tmux", "send-keys", "-t", "ghost", "C-o", "Enter", "C-x"], check=True)
        time.sleep(1.0)
        
        # Step 7: Clear the screen and execute the script full-frame
        print("[*] Executing script live...")
        typist.type_text("ghost", f"clear && python3 {file_path}\n")

    # Run the AI workflow inside a background thread so the main thread can attach to tmux
    t = threading.Thread(target=ai_coding_workflow)
    t.start()

    print("[*] Attaching to full-screen session immediately...")
    time.sleep(0.5)

    # Attach to tmux so you can watch the entire sequence unfold live on your monitor
    subprocess.run(["tmux", "attach", "-t", "ghost"])

if __name__ == "__main__":
    main()
