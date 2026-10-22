"""
ghost_shift/email_engine.py
---------------------------
Corporate IT Email Generator & Maildir Manager for Day Shift.
Creates synthetic IT support tickets, management updates, and coworker requests.
"""

import time
import email.utils
import random
import uuid
import logging
from pathlib import Path

from ghost_shift.config import load_config
from ghost_shift.local_llm import generate_local, strip_noise

logger = logging.getLogger("ghost_shift.email")

MAILDIR_NEW = Path("~/.local/share/ghost-shift/mail/new").expanduser()

SENDERS = [
    ("Sarah Vance (IT Ops Lead)", "svance@corp-net.local"),
    ("DevOps Bot", "no-reply@ci-cd.corp-net.local"),
    ("Marcus Chen (SysAdmin)", "mchen@corp-net.local"),
    ("Helpdesk Dispatch", "tickets@corp-net.local"),
    ("Security Operations", "secops@corp-net.local")
]

SUBJECT_TEMPLATES = [
    "[TICKET #4829] Scheduled maintenance on core switch stack",
    "[ALERT] High memory usage detected on node-04",
    "RE: Request for additional NVMe storage quota",
    "URGENT: SSL Certificate renewal pending for internal LDAP",
    "Weekly Infrastructure Health Check Summary",
    "[TICKET #4912] Printer spooler service unresponsive in West Wing"
]

def generate_synthetic_email(config: dict) -> Path:
    """
    Generates a realistic corporate IT email and writes it directly to Maildir.
    """
    MAILDIR_NEW.mkdir(parents=True, exist_ok=True)

    sender_name, sender_addr = random.choice(SENDERS)
    subject = random.choice(SUBJECT_TEMPLATES)
    
    prompt = (
        f"Write a realistic, short corporate IT email from {sender_name} regarding '{subject}'.\n"
        "RULES:\n"
        "1. Max 4 to 6 sentences.\n"
        "2. Professional, slightly urgent or routine IT tone.\n"
        "3. Ask for a status update, system confirmation, or log review.\n"
        "4. Output ONLY the email body. Do not include headers or markdown wrappers."
    )
    
    system_prompt = "You write professional corporate IT emails. Output plain text body only."
    
    llm_cfg = config.get("llm", {})
    model = llm_cfg.get("local_model", "qwen2.5-coder:3b")

    try:
        raw_body = generate_local(
            prompt,
            model=model,
            system=system_prompt,
            max_tokens=250,
            total_deadline=300
        )
        body = strip_noise(raw_body)
    except Exception as e:
        logger.warning(f"[-] Email generation fallback triggered: {e}")
        body = (
            "Hi Ed,\n\n"
            "Please confirm when the overnight diagnostic cycle on the primary node finishes.\n"
            "We need to clear the heap buffers before the 09:00 AM shift deployment.\n\n"
            "Thanks,\nIT Infrastructure Team"
        )

    # Format standard RFC-822 Email Message
    msg_id = f"{int(time.time())}.{uuid.uuid4().hex[:6]}.rpi5"
    email_content = (
        f"From: {sender_name} <{sender_addr}>\n"
        f"To: Ed (Ghost Shift IT) <ed@rpi5.local>\n"
        f"Subject: {subject}\n"
        f"Date: {email.utils.formatdate(localtime=True)}\n"
        f"Message-ID: <{msg_id}>\n"
        f"Content-Type: text/plain; charset=utf-8\n\n"
        f"{body}\n"
    )

    mail_file = MAILDIR_NEW / msg_id
    mail_file.write_text(email_content)
    print(f"[+] Generated new IT mail item: {subject}")
    return mail_file

if __name__ == "__main__":
    cfg = load_config()
    generate_synthetic_email(cfg)
