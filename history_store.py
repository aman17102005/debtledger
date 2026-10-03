"""
CodeSweep — Scan History Store

Remembers past scan results so we can:
  1. Show "compared to last scan, you fixed X, Y appeared" after a
     repeat scan of the same repo.
  2. Serve a live README badge without re-scanning on every badge load.

No login needed: a GitHub repo URL is already a unique, public
identifier, so we use it directly as the lookup key — like a library
using a book's own title instead of issuing library cards.

Honest limit: this uses a small SQLite file sitting next to the app.
On Render's free tier, that file can be wiped if the service gets
redeployed (a new code push rebuilds the container from scratch), so
history may occasionally reset. It survives normal restarts/sleep-wake
cycles fine — just not a guaranteed-forever archive. For long-term,
guaranteed-safe history, swapping this for a small free Postgres
database (Supabase) would be the next upgrade.
"""

import sqlite3
import time
from contextlib import contextmanager

DB_PATH = "codesweep_history.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_url TEXT NOT NULL,
                scanned_at REAL NOT NULL,
                score INTEGER NOT NULL,
                duplicate_count INTEGER NOT NULL,
                complex_count INTEGER NOT NULL,
                dead_count INTEGER NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_repo_url ON scans(repo_url)")


def save_scan(repo_url: str, health: dict):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO scans (repo_url, scanned_at, score, duplicate_count, complex_count, dead_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (repo_url, time.time(), health["score"], health["duplicate_count"],
             health["complex_count"], health["dead_count"]),
        )


def get_previous_scan(repo_url: str):
    """Returns the most recent PRIOR scan for this repo (before the one
    just performed), or None if this is the first time we've seen it."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM scans WHERE repo_url = ? ORDER BY scanned_at DESC LIMIT 2",
            (repo_url,),
        ).fetchall()
    if len(rows) < 2:
        return None
    return dict(rows[1])  # rows[0] is the one we just saved; rows[1] is the one before it


def get_latest_scan(repo_url: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM scans WHERE repo_url = ? ORDER BY scanned_at DESC LIMIT 1",
            (repo_url,),
        ).fetchone()
    return dict(row) if row else None


init_db()
