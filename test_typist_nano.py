import subprocess
import time
from pathlib import Path
from ghost_shift.typist import Typist
from ghost_shift.config import load_config

def run_diagnostic():
    config = load_config()
    typist = Typist(config)
    
    test_code = (
        "import time\n"
        "import random\n\n"
        "# [DIAGNOSTIC TEST BLOCK]\n"
        "def check_system():\n"
        "    for i in range(3):\n"
        "        print(f'[*] Node {i}: OK')\n"
        "        time.sleep(0.5)\n\n"
        "check_system()\n"
    )
    
    test_file = Path("/tmp/typist_nano_test.py")
    if test_file.exists():
        test_file.unlink()
        
    session = "ghost_test"
    subprocess.run(["tmux", "new-session", "-d", "-s", session], check=True)
    
    try:
        # Open nano
        subprocess.run(["tmux", "send-keys", "-t", session, f"nano -I -E -l -w {test_file}", "Enter"], check=True)
        time.sleep(1.0)
        
        # Type test code block
        typist.type_code_block(session, test_code)
        time.sleep(1.0)
        
        # Save and exit nano (Ctrl+O, Enter, Ctrl+X)
        subprocess.run(["tmux", "send-keys", "-t", session, "C-o", "Enter", "C-x"], check=True)
        time.sleep(1.0)
        
        # Verify file content on disk
        if test_file.exists():
            saved_content = test_file.read_text()
            exact_match = (saved_content == test_code)
            stripped_match = (saved_content.strip() == test_code.strip())
            
            print("\n" + "="*50)
            print(f"[*] EXACT MATCH    : {exact_match}")
            print(f"[*] STRIPPED MATCH : {stripped_match}")
            print("="*50)
            
            if not stripped_match:
                print("\n[-] DIFFERENCE DETECTED!")
                print(f"Expected len: {len(test_code)} | Saved len: {len(saved_content)}")
                # Find first mismatch index
                for idx, (c1, c2) in enumerate(zip(test_code, saved_content)):
                    if c1 != c2:
                        print(f"[*] First difference at character index {idx}: expected {repr(c1)}, got {repr(c2)}")
                        break
        else:
            print("[-] Test file was not created by nano.")
            
    finally:
        subprocess.run(["tmux", "kill-session", "-t", session], check=False)

if __name__ == "__main__":
    run_diagnostic()
