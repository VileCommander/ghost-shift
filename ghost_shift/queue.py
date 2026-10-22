import sqlite3
import os
from pathlib import Path

class ContentQueue:
    def __init__(self, db_path="~/.local/share/ghost-shift/content.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scene_type TEXT,
                    content TEXT,
                    filename TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def push(self, scene_type: str, content: str, filename: str = None):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO artifacts (scene_type, content, filename) VALUES (?, ?, ?)",
                (scene_type, content, filename)
            )
            conn.commit()

    def pop_unused(self, scene_type: str):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, content, filename FROM artifacts WHERE scene_type = ? AND used = 0 ORDER BY created_at ASC LIMIT 1",
                (scene_type,)
            )
            row = cursor.fetchone()
            if row:
                art_id, content, filename = row
                conn.execute("UPDATE artifacts SET used = 1 WHERE id = ?", (art_id,))
                conn.commit()
                return content, filename
        return None, None
