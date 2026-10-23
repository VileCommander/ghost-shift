"""
ghost_shift/email_engine.py
---------------------------
Synthetic work email for the day shift.

Messages come from recurring personas with their own voices, are written into a
real Maildir that mutt opens, and each one arrives with a PRE-WRITTEN REPLY so
the on-screen mail scene never waits on the model.

Layout under ~/.local/share/ghost-shift/:
    mail/{new,cur,tmp}        the Maildir (mutt moves read mail from new/ to cur/)
    mail-replies/<id>.json    prepared reply for each message
    mail-sent/                copies of messages "sent" from mutt
"""

import email
import email.utils
import json
import os
import random
import re
import textwrap
import time
import uuid
from datetime import datetime
from pathlib import Path

from ghost_shift.local_llm import generate_local
from ghost_shift.util import log

DATA_DIR = Path("~/.local/share/ghost-shift").expanduser()
MAIL_DIR = DATA_DIR / "mail"
NEW_DIR = MAIL_DIR / "new"
CUR_DIR = MAIL_DIR / "cur"
TMP_DIR = MAIL_DIR / "tmp"
REPLY_DIR = DATA_DIR / "mail-replies"
SENT_DIR = DATA_DIR / "mail-sent"

MY_NAME = "Ed"
MY_ADDR = "ed@rpi5.local"

SERVICES = ["LDAP", "DNS", "NFS", "the VPN gateway", "the backup job",
            "the mail relay", "the build server", "monitoring", "the print server"]

PERSONAS = [
    {"name": "Sarah Vance", "role": "IT Ops Lead", "addr": "svance@corp-net.local",
     "style": "polite but passive-aggressive; keeps asking for status updates and never says anything directly",
     "subjects": ["Following up on #{ticket}", "Quick question about {svc}",
                  "Status of the {svc} work?", "RE: RE: {svc} maintenance window",
                  "Any update on {node}?", "Per my last email re: {svc}"],
     "bodies": ["Hi Ed,\n\nJust circling back on {svc}. I know you are busy, but the steering group asks about it every morning. Could you send a short status when you get a moment?\n\nThanks so much,\nSarah",
                "Ed,\n\nNo pressure at all, but {node} came up in the leadership sync again. A quick update from you would help me a lot.\n\nBest,\nSarah"]},
    {"name": "Marcus Chen", "role": "SysAdmin", "addr": "mchen@corp-net.local",
     "style": "upbeat and chatty; over-explains and likes sports metaphors",
     "subjects": ["Heads up: {node} rebooted itself", "Rotating the {svc} credentials today",
                  "{svc} backup finished (finally)", "Lunch order + {svc} patch",
                  "Big win on {svc} this morning"],
     "bodies": ["Hey Ed!\n\nBig news: {node} rebooted itself at 3am, which is basically a fumble on the goal line. Everything came back clean though. Can you glance at the logs and tell me if you see anything weird?\n\nCheers,\nMarcus",
                "Ed,\n\nI am rotating the {svc} credentials this afternoon. Total team effort, we have got this. Shout if anything of yours breaks.\n\nMarcus"]},
    {"name": "Helpdesk Dispatch", "role": "Ticketing System", "addr": "tickets@corp-net.local",
     "style": "terse automated ticket text with a reference number and a priority line",
     "subjects": ["[TICKET #{ticket}] {svc} unresponsive on {node}",
                  "[TICKET #{ticket}] User cannot reach {svc}",
                  "[TICKET #{ticket}] Request for additional NVMe quota",
                  "[TICKET #{ticket}] Printer queue stuck in West Wing"],
     "bodies": ["Ticket assigned to: ed\nPriority: P3\nSummary: {svc} reported as unresponsive on {node}.\nPlease acknowledge within 4 business hours and attach relevant log excerpts.\n\n-- Helpdesk Dispatch",
                "A new ticket is waiting in your queue.\nPriority: P2\nSummary: user cannot reach {svc}.\nSLA clock is running. Please update the ticket with your findings.\n\n-- Helpdesk Dispatch"]},
    {"name": "DevOps Bot", "role": "CI/CD", "addr": "no-reply@ci-cd.corp-net.local",
     "style": "automated; short key=value style lines, no greetings, no personality",
     "subjects": ["[ALERT] Disk usage 91% on {node}", "[CI] Build #{ticket} failed on main",
                  "[ALERT] {svc} latency above threshold", "[CI] Nightly job finished with warnings"],
     "bodies": ["status=FAILED\nhost={node}\nservice={svc}\nthreshold_exceeded=true\nrunbook=https://wiki.corp-net.local/runbooks/{ticket}\n\nThis is an automated message. Do not reply.",
                "status=WARNING\nhost={node}\nretries=3\nnext_run=02:00\n\nReview the job log and acknowledge this alert."]},
    {"name": "Security Operations", "role": "SecOps", "addr": "secops@corp-net.local",
     "style": "formal and mildly alarmist; uses words like 'immediately' and 'compliance'",
     "subjects": ["ACTION REQUIRED: rotate credentials for {svc}",
                  "Certificate expiring: {svc}", "Unusual login pattern on {node}",
                  "Phishing simulation results"],
     "bodies": ["Ed,\n\nOur scanners flagged {svc} for an expiring certificate. Per policy this must be resolved immediately to remain compliant. Please confirm completion by end of day.\n\nSecurity Operations",
                "Ed,\n\nWe observed an unusual login pattern on {node}. Please review the access logs and confirm that the activity was authorised.\n\nSecurity Operations"]},
    {"name": "Greg Hollis", "role": "Finance", "addr": "ghollis@corp-net.local",
     "style": "wants numbers and justification; suspicious of every expense",
     "subjects": ["Budget justification for {svc}", "Why is {node} costing us this much?",
                  "Quarterly hardware spend review", "Invoice question re: #{ticket}"],
     "bodies": ["Ed,\n\nI am looking at the line item for {svc} and the figure looks high. Can you send me a justification, ideally with numbers, by Friday?\n\nGreg",
                "Ed,\n\nFinance is reviewing hardware spend and {node} stands out. What exactly are we paying for, and could it be cheaper?\n\nGreg"]},
    {"name": "Priya Nair", "role": "QA", "addr": "pnair@corp-net.local",
     "style": "precise and methodical; always asks for reproduction steps and exact versions",
     "subjects": ["Can you reproduce this on {node}?", "Flaky test report",
                  "{svc} regression after Tuesday's patch"],
     "bodies": ["Hi Ed,\n\nI am seeing a regression in {svc} since Tuesday's patch. Could you reproduce it on {node} and tell me the exact version you are running? Reproduction steps are attached in the ticket.\n\nPriya",
                "Ed,\n\nThe nightly run flagged an intermittent failure related to {svc}. Do you have logs from {node} around 02:00?\n\nPriya"]},
]

CANNED_REPLIES = [
    "Hi {first},\n\nOn it. I will have an update for you by end of day.\n\nEd",
    "{first},\n\nThanks for flagging this. I am checking the logs now and will report back shortly.\n\nEd",
    "Hi {first},\n\nAcknowledged. Looks routine so far, but I will confirm once I have verified it on the box.\n\nEd",
    "{first},\n\nGot it. Give me an hour to dig into this and I will send you what I find.\n\nEd",
    "Hi {first},\n\nThanks. I will take care of it and follow up when it is done.\n\nEd",
]

# Words the small model overuses, swapped for grammatical alternatives.
BANNED_SUBS = [
    (re.compile(r"\bheap buffers\b", re.I), "caches"),
    (re.compile(r"\bheap buffer\b", re.I), "cache"),
    (re.compile(r"\bbuffers\b", re.I), "caches"),
    (re.compile(r"\bbuffering\b", re.I), "caching"),
    (re.compile(r"\bbuffer\b", re.I), "cache"),
    (re.compile(r"\bheap\b", re.I), "stack"),
    (re.compile(r"\bneural\b", re.I), "network"),
    (re.compile(r"\bquantum\b", re.I), "batch"),
]

PLACEHOLDER_WORDS = ("insert", "enter", "your", "recipient", "sender", "company",
                     "placeholder", "fill in", "tbd", "name", "date", "time",
                     "ticket", "node", "service", "system", "signature", "xx")

EMAIL_SYSTEM = "You write realistic, concise workplace emails. Output the email body only."
REPLY_SYSTEM = "You write short, natural workplace replies. Output the reply text only."

_last_ts = 0


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------
def fix_placeholders(text: str) -> str:
    """Replace or drop placeholder text such as [insert date] or [Your Name]."""
    def swap(match):
        inner = match.group(0)[1:-1].lower()
        if re.search(r"\d", inner) or not any(w in inner for w in PLACEHOLDER_WORDS):
            return match.group(0)            # e.g. [OK], [ALERT], [TICKET #4521]
        if "date" in inner:
            return time.strftime("%B %d")
        if "time" in inner:
            return random.choice(["10am", "2pm", "4pm", "end of day"])
        if "ticket" in inner:
            return f"#{random.randint(4000, 5999)}"
        if "node" in inner:
            return f"node-{random.randint(1, 19):02d}"
        if any(w in inner for w in ("service", "system", "application", "software")):
            return random.choice(SERVICES)
        return ""                            # names, signatures, "insert ..." etc.
    text = re.sub(r"\[[^\]\n]{1,40}\]", swap, text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    return "\n".join(ln.rstrip() for ln in text.splitlines())


def clean_body(text: str) -> str:
    """Strip thinking blocks, fences, header lines and banned words."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"<think>.*\Z", "", text, flags=re.S)
    fenced = re.search(r"```(?:\w+)?\s*\n(.*?)(?:```|\Z)", text, re.S)
    if fenced:
        text = fenced.group(1)
    lines = [ln.rstrip() for ln in text.splitlines()
             if not re.match(r"\s*(subject|from|to|date|cc)\s*:", ln, re.I)]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    text = fix_placeholders(text)
    for pattern, replacement in BANNED_SUBS:
        text = pattern.sub(replacement, text)
    return text


def wrap_text(text: str, width: int = 70) -> str:
    """Hard-wrap paragraphs (nano is run without soft wrap); keep short lines."""
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in para.splitlines()]
        if len(lines) > 1 and all(len(ln) < 40 for ln in lines):
            out.append("\n".join(lines))
        else:
            out.append(textwrap.fill(" ".join(lines), width))
    return "\n\n".join(out) + "\n"


def _fill(template: str) -> str:
    return template.format(
        ticket=random.randint(4000, 5999),
        node=f"node-{random.randint(1, 19):02d}",
        svc=random.choice(SERVICES),
    )


def _first(name: str) -> str:
    return name.split()[0]


def canned_reply(sender_name: str) -> str:
    return random.choice(CANNED_REPLIES).format(first=_first(sender_name))


# --------------------------------------------------------------------------
# Maildir plumbing
# --------------------------------------------------------------------------
def ensure_maildir() -> None:
    for d in (NEW_DIR, CUR_DIR, TMP_DIR, REPLY_DIR, SENT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _next_ts() -> int:
    global _last_ts
    _last_ts = max(_last_ts + 1, int(time.time()))
    return _last_ts


def _message(sender_name: str, sender_addr: str, subject: str, body: str, ts: int):
    msg_id = f"{ts}.{uuid.uuid4().hex[:6]}.rpi5"
    text = (
        f"From: {sender_name} <{sender_addr}>\n"
        f"To: {MY_NAME} <{MY_ADDR}>\n"
        f"Subject: {subject}\n"
        f"Date: {email.utils.formatdate(ts, localtime=True)}\n"
        f"Message-ID: <{msg_id}@rpi5.local>\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "Content-Transfer-Encoding: 8bit\n\n"
        f"{body.strip()}\n"
    )
    return msg_id, text


def _deliver(msg_id: str, text: str, read: bool = False) -> Path:
    """Write via tmp/ then rename, the way Maildir delivery is meant to work."""
    ensure_maildir()
    tmp = TMP_DIR / msg_id
    tmp.write_text(text, encoding="utf-8")
    dest = (CUR_DIR / f"{msg_id}:2,S") if read else (NEW_DIR / msg_id)
    os.replace(tmp, dest)
    return dest


def unique_id(path) -> str:
    """Maildir unique name; mutt keeps it when it moves new/ -> cur/."""
    return Path(path).name.split(":")[0]


def read_message(path) -> dict:
    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f)
    payload = msg.get_payload(decode=True) or b""
    return {"id": unique_id(path), "from": msg.get("From", ""),
            "subject": msg.get("Subject", ""), "date": msg.get("Date", ""),
            "body": payload.decode("utf-8", "replace")}


def _sent_timestamp(path) -> float:
    try:
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f)
        return email.utils.parsedate_to_datetime(msg["Date"]).timestamp()
    except Exception:
        return Path(path).stat().st_mtime


def all_messages() -> list:
    ensure_maildir()
    return [p for d in (NEW_DIR, CUR_DIR) for p in d.iterdir() if p.is_file()]


def mailbox_order() -> list:
    """Messages in the order mutt shows them (sort=reverse-date: newest first)."""
    return sorted(all_messages(), key=_sent_timestamp, reverse=True)


def position_in_index(path) -> int:
    """0-based row of a message in mutt's index."""
    uid = unique_id(path)
    for i, p in enumerate(mailbox_order()):
        if unique_id(p) == uid:
            return i
    return 0


def unread_messages() -> list:
    """Unread mail, oldest first."""
    ensure_maildir()
    files = [p for p in NEW_DIR.iterdir() if p.is_file()]
    return sorted(files, key=_sent_timestamp)


def mark_read(path) -> None:
    """Move a message from new/ to cur/ as read (what mutt does on exit).

    Used when a scene fails, so the same email is not shown forever."""
    p = Path(path)
    if p.exists() and p.parent == NEW_DIR:
        os.replace(p, CUR_DIR / f"{p.name}:2,S")


# --------------------------------------------------------------------------
# prepared replies
# --------------------------------------------------------------------------
def _save_prepared(msg_id: str, data: dict) -> None:
    ensure_maildir()
    (REPLY_DIR / f"{msg_id}.json").write_text(json.dumps(data))


def load_prepared(path):
    try:
        return json.loads((REPLY_DIR / f"{unique_id(path)}.json").read_text())
    except Exception:
        return None


def discard_prepared(path) -> None:
    (REPLY_DIR / f"{unique_id(path)}.json").unlink(missing_ok=True)


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------
def _recent_project():
    """Describe a program the AI recently wrote, so mail can refer to it."""
    archive = DATA_DIR / "library" / "archive"
    try:
        files = sorted(archive.glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]
    except OSError:
        return None
    slugs = [p.stem.rsplit("_", 2)[0] for p in files if p.stem.count("_") >= 2]
    slugs = [s for s in slugs if s not in ("gen", "sys_monitor", "sysmon")]
    if not slugs:
        return None
    slug = random.choice(slugs)
    desc = ""
    try:
        from ghost_shift.codegen import BY_SLUG
        desc = BY_SLUG.get(slug, {}).get("desc", "")
    except Exception:
        pass
    return f"'{slug}'" + (f" ({desc[:70]})" if desc else "")


def _llm_text(prompt: str, system: str, model: str, max_tokens: int):
    try:
        raw = generate_local(prompt, model=model, system=system,
                             max_tokens=max_tokens, total_deadline=600, log=log)
        return clean_body(raw)
    except Exception as exc:
        log(f"[!] mail generation failed: {exc}")
        return None


def _body_prompt(persona: dict, subject: str, project) -> str:
    lines = [
        f"Write a short workplace email from {persona['name']} ({persona['role']}) to Ed, an IT engineer.",
        f"Subject: {subject}",
        f"Voice: {persona['style']}.",
        "Rules: 3 to 5 sentences. Plain text only. No subject line, no headers, no markdown. "
        "Greet Ed and sign off with the sender's first name.",
        "Never use the words heap, buffer, neural or quantum.",
        "Use concrete details. Never write placeholders in square brackets such as [insert date] or [Your Name].",
    ]
    if project:
        lines.insert(3, f"Refer to Ed's recent work: {project}.")
    return "\n".join(lines)


def _reply_prompt(persona: dict, subject: str, body: str) -> str:
    return (
        "Write Ed's reply to the email below. Ed is a calm, slightly sarcastic IT engineer.\n"
        "Rules: 2 to 4 sentences, plain text, first person, no headers, no markdown, "
        "sign off with just 'Ed'. Never use the words heap, buffer, neural or quantum. "
        "Never write placeholders in square brackets such as [insert date].\n\n"
        f"From: {persona['name']}\nSubject: {subject}\n\n{body}\n\n"
        "Reply:"
    )


def generate_synthetic_email(config: dict, allow_llm: bool = True) -> Path:
    """Create one unread email plus its prepared reply; return the mail file."""
    ensure_maildir()
    persona = random.choice(PERSONAS)
    subject = _fill(random.choice(persona["subjects"]))
    model = config.get("llm", {}).get("local_model", "qwen2.5-coder:3b")

    body = reply = None
    if allow_llm:
        project = _recent_project() if random.random() < 0.5 else None
        body = _llm_text(_body_prompt(persona, subject, project), EMAIL_SYSTEM, model, 220)
    if not body or len(body) < 25:
        body = _fill(random.choice(persona["bodies"]))
    if allow_llm:
        reply = _llm_text(_reply_prompt(persona, subject, body), REPLY_SYSTEM, model, 160)
    if not reply or len(reply) < 15:
        reply = canned_reply(persona["name"])

    msg_id, text = _message(persona["name"], persona["addr"], subject, body, _next_ts())
    path = _deliver(msg_id, text)
    _save_prepared(msg_id, {"sender": persona["name"], "subject": subject, "reply": reply})
    log(f"[+] new mail from {persona['name']}: {subject}")
    return path


def fill_mail_queue(config: dict, target_unread: int = 3, max_new: int = 1) -> int:
    """Top up unread mail; returns how many messages were created."""
    ensure_maildir()
    made = 0
    while len(unread_messages()) < target_unread and made < max_new:
        generate_synthetic_email(config)
        made += 1
    return made


def ensure_unread(config: dict) -> list:
    """Guarantee at least one unread message (canned, no model call)."""
    if not unread_messages():
        generate_synthetic_email(config, allow_llm=False)
    return unread_messages()


def seed_inbox(count: int = 6) -> None:
    """Fill the inbox with already-read mail so the index looks lived in."""
    ensure_maildir()
    now = int(time.time())
    used = set()
    for k in range(count):
        persona = random.choice(PERSONAS)
        ts = now - 3600 * (5 + k * 7) - random.randint(0, 1800)
        while ts in used:
            ts -= 1
        used.add(ts)
        body = _fill(random.choice(persona["bodies"]))
        msg_id, text = _message(persona["name"], persona["addr"],
                                _fill(random.choice(persona["subjects"])), body, ts)
        _deliver(msg_id, text, read=True)


def seed_inbox_if_empty() -> None:
    ensure_maildir()
    if not any(p.is_file() for p in CUR_DIR.iterdir()):
        seed_inbox()


def prune(max_read: int = 30, max_sent: int = 50) -> None:
    """Keep the mailbox bounded so months of uptime never fill the disk."""
    ensure_maildir()
    read = sorted((p for p in CUR_DIR.iterdir() if p.is_file()), key=_sent_timestamp)
    for p in read[:max(0, len(read) - max_read)]:
        p.unlink(missing_ok=True)
    sent = sorted((p for p in SENT_DIR.iterdir() if p.is_file()),
                  key=lambda p: p.stat().st_mtime)
    for p in sent[:max(0, len(sent) - max_sent)]:
        p.unlink(missing_ok=True)
    cutoff = time.time() - 3 * 86400
    for p in REPLY_DIR.glob("*.json"):
        if p.stat().st_mtime < cutoff:
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    from ghost_shift.config import load_config
    print(generate_synthetic_email(load_config()))
