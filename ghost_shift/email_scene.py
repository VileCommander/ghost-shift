"""
ghost_shift/email_scene.py
--------------------------
The day-shift mail scene, staged in a titled desk window:

    open window -> type `mutt` -> scroll to the unread message -> read it ->
    reply -> type the PREPARED reply into nano -> save, send -> quit -> close.

Self-contained: it writes its own mutt config (it never touches ~/.muttrc) and a
fake `sendmail` that files outgoing mail under mail-sent/ instead of delivering.
"""

import random
import time
from pathlib import Path

from ghost_shift import email_engine as mail
from ghost_shift.util import (SHELLS, log, pane_command, pane_text, send,
                              wait_for_text, wait_until)

RC_PATH = mail.DATA_DIR / "muttrc"
SENDMAIL_PATH = mail.DATA_DIR / "ghost-sendmail"
RC_DISPLAY = "~/.local/share/ghost-shift/muttrc"   # what appears on screen

SENDMAIL_SCRIPT = """#!/bin/sh
# Ghost Shift: "send" mail by filing it away instead of delivering it.
d="$HOME/.local/share/ghost-shift/mail-sent"
mkdir -p "$d"
cat > "$d/$(date +%s).$$.eml"
exit 0
"""

MUTT_RC = """# Ghost Shift mutt configuration (generated; edits are overwritten)
set mbox_type=Maildir
set folder="{mail_dir}"
set spoolfile="{mail_dir}"
set mbox="{mail_dir}"
set realname="Ed (Ghost Shift IT)"
set from="{addr}"
set use_from=yes
set sendmail="{sendmail}"
set copy=no
set sort=reverse-date
set sort_aux=reverse-date
set editor="nano -I -E -w"
set autoedit=yes
set fast_reply=yes
set include=no
set edit_headers=no
set askcc=no
set askbcc=no
set move=no
set confirmappend=no
set quit=yes
set delete=yes
set sleep_time=0
set mail_check=0
set wait_key=no
set help=no
set markers=no
set pager_index_lines=0
set charset="utf-8"
set date_format="%b %d"
set index_format="%4C %Z %{{%b %d}} %-20.20L  %s"
folder-hook . 'push <first-entry>'

color normal green black
color indicator black green
color status black green
color tree green black
color error brightred black
color message green black
color hdrdefault green black
color header brightgreen black "^(From|Subject):"
color quoted green black
color index brightgreen black ~N
color index green black ~O
"""


def write_support_files() -> Path:
    """(Re)write the mutt config and the fake sendmail. Returns the rc path."""
    mail.ensure_maildir()
    SENDMAIL_PATH.write_text(SENDMAIL_SCRIPT)
    SENDMAIL_PATH.chmod(0o755)
    RC_PATH.write_text(MUTT_RC.format(
        mail_dir=str(mail.MAIL_DIR), addr=mail.MY_ADDR, sendmail=str(SENDMAIL_PATH)))
    return RC_PATH


def _snapshot(pane: str, why: str) -> None:
    """Record what is on screen when something goes wrong (for debugging)."""
    text = pane_text(pane).rstrip()
    log(f"[!] {why}; screen was:\n" + "\n".join(text.splitlines()[-18:]))


def _bail(pane: str) -> None:
    """Best-effort exit from whatever is on screen so the window can close."""
    for keys in (("C-c",), ("q",), ("q",)):
        try:
            send(pane, *keys)
        except Exception:
            return
        time.sleep(0.3)


def _sent_count() -> int:
    return len(list(mail.SENT_DIR.glob("*.eml")))


def run_scene(desk, typist, config: dict) -> bool:
    """Run one mail scene. Returns False if there was nothing to do or it failed."""
    mail.ensure_maildir()
    mail.seed_inbox_if_empty()
    unread = mail.unread_messages()
    if not unread:
        log("[*] mail scene skipped: no unread mail")
        return False

    target = unread[0]                       # oldest unread first
    info = mail.read_message(target)
    prepared = mail.load_prepared(target)
    reply = (prepared or {}).get("reply") or mail.canned_reply(info["from"].split("<")[0].strip() or "there")
    reply_text = mail.wrap_text(reply)
    position = mail.position_in_index(target)
    subject = info["subject"]
    write_support_files()

    log(f"[*] scene: MAIL :: {subject!r} (row {position}, {len(unread)} unread)")
    pane = desk.open(f"MAIL :: {len(unread)} unread", where="top", cwd=str(Path.home()))
    ok = False
    try:
        time.sleep(0.5)
        typist.type_text(pane, f"mutt -F {RC_DISPLAY}\n")
        if not wait_until(lambda: pane_command(pane) == "mutt", timeout=15):
            _snapshot(pane, "mutt did not start (is it installed? sudo apt install mutt)")
            return False
        time.sleep(2.0)

        for _ in range(position):                       # scan down the inbox
            send(pane, "Down")
            time.sleep(random.uniform(0.25, 0.7))
        time.sleep(0.8)

        desk.title(pane, f"[ MAIL :: {subject[:44]} ]")
        send(pane, "Enter")                              # open the message
        if not wait_for_text(pane, subject[:25], timeout=8):
            _snapshot(pane, "the message did not open as expected")
        time.sleep(min(12.0, 3.0 + len(info["body"]) / 40.0))   # "read" it

        send(pane, "r")                                  # reply -> nano opens
        # nano runs inside mutt's process group, so tmux keeps reporting "mutt"
        # as the pane command. Look for nano's title bar on screen instead.
        if not wait_for_text(pane, "GNU nano", timeout=20):
            _snapshot(pane, "reply editor did not open")
            _bail(pane)
            return False
        desk.title(pane, f"[ COMPOSE :: RE: {subject[:40]} ]")
        time.sleep(0.8)

        typist.type_text(pane, reply_text)
        time.sleep(1.0)

        send(pane, "C-o")                                # save
        time.sleep(0.8)
        send(pane, "Enter")
        time.sleep(0.8)
        send(pane, "C-x")                                # back to mutt's compose menu
        if not wait_for_text(pane, "Compose", timeout=15):
            _snapshot(pane, "did not return to the compose menu")
            _bail(pane)
            return False
        time.sleep(1.2)

        before = _sent_count()
        send(pane, "y")                                  # send
        delivered = wait_until(lambda: _sent_count() > before, timeout=10)
        if delivered:
            log(f"[+] reply sent for {subject!r}")
            desk.title(pane, "[ MAIL SENT ]")
        else:
            _snapshot(pane, "reply was not delivered (y did not send)")
        time.sleep(1.0)

        send(pane, "q")                                  # pager -> index
        time.sleep(0.6)
        send(pane, "q")                                  # quit mutt
        wait_until(lambda: pane_command(pane) in SHELLS or pane_command(pane) == "",
                   timeout=15)
        time.sleep(1.0)
        ok = delivered
        return delivered
    finally:
        desk.close(pane)
        mail.mark_read(target)           # never show the same email forever
        mail.discard_prepared(target)
        if not ok:
            log("[!] mail scene ended early")
