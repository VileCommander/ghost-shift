"""
ghost_shift/cleaner.py
-----------------------
This module handles maintenance and cleanup tasks for the Ghost Shift project.
Because this art installation runs 24/7 unattended on a Raspberry Pi 5, 
we must prevent storage from filling up over months of continuous operation.
"""

import os
import sqlite3
from pathlib import Path
import logging

# Set up logging so we can track what files and database records get deleted
logger = logging.getLogger("ghost_shift.cleaner")

def prune_workspace(workspace_dir: str, max_files: int = 50):
    """
    Cleans up the ~/workspace/ folder where the AI saves its generated Python scripts.
    If the number of files exceeds 'max_files', it deletes the oldest ones first.
    """
    # Expand '~' to the user's actual home directory (e.g., /home/ed/workspace)
    ws = Path(workspace_dir).expanduser()
    if not ws.exists():
        return
    
    # Find all Python (.py) files in the workspace and sort them by modification time (oldest first)
    py_files = sorted([f for f in ws.glob("*.py")], key=lambda x: x.stat().st_mtime)
    
    # If we have more files than our maximum limit, delete the excess oldest files
    if len(py_files) > max_files:
        excess = len(py_files) - max_files
        logger.info(f"Workspace has {len(py_files)} files. Pruning oldest {excess} files...")
        for file_to_delete in py_files[:excess]:
            try:
                file_to_delete.unlink() # Deletes the file from disk
                logger.info(f"Pruned old workspace file: {file_to_delete.name}")
            except Exception as e:
                logger.error(f"Failed to delete {file_to_delete}: {e}")

def prune_database(db_path: str, max_records: int = 200):
    """
    Trims old artifact history from the SQLite database to keep it lightweight.
    If total records exceed 'max_records', it deletes the oldest entries.
    """
    db = Path(db_path).expanduser()
    if not db.exists():
        return
        
    try:
        # Connect to the SQLite database file
        conn = sqlite3.connect(str(db))
        cursor = conn.cursor()
        
        # Check how many saved artifacts currently exist in the table
        cursor.execute("SELECT COUNT(*) FROM artifacts")
        count = cursor.fetchone()[0]
        
        # If we exceed our limit, delete the oldest records based on creation timestamp
        if count > max_records:
            excess = count - max_records
            logger.info(f"Database has {count} records. Pruning oldest {excess} records...")
            cursor.execute("""
                DELETE FROM artifacts 
                WHERE id IN (
                    SELECT id FROM artifacts ORDER BY created_at ASC LIMIT ?
                )
            """, (excess,))
            conn.commit() # Save changes to the database
        conn.close()
    except Exception as e:
        logger.error(f"Database pruning failed: {e}")

if __name__ == "__main__":
    # Configure logging output format for manual execution
    logging.basicConfig(level=logging.INFO)
    print("[*] Running manual maintenance cleanup...")
    
    # Run workspace and database pruners with conservative limits
    prune_workspace("~/workspace", max_files=30)
    prune_database("~/.local/share/ghost-shift/content.db", max_records=100)
    
    print("[+] Maintenance cleanup complete.")
