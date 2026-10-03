"""
CodeSweep — Git History Tracker

Reads a cloned repo's git history to find each file's age, how many times
it's been touched, and by how many people. No code is executed — this
only reads saved history, like reading a diary of past events.

Note: this only applies to GitHub repo scans. Files a visitor uploads
directly have no git history attached, so this module is not used for
the upload flow.
"""

import subprocess
from collections import defaultdict
from datetime import datetime


def run_git(repo_path: str, *args):
    result = subprocess.run(["git", "-C", repo_path, *args], capture_output=True, text=True)
    return result.stdout


def file_history(repo_path: str):
    log_output = run_git(
        repo_path, "log", "--pretty=format:__COMMIT__%H|%an|%ad", "--date=short", "--name-only"
    )
    history = defaultdict(lambda: {"first_seen": None, "last_touched": None, "touch_count": 0, "authors": set()})
    current_author = None
    current_date = None

    for line in log_output.splitlines():
        if line.startswith("__COMMIT__"):
            _, meta = line.split("__COMMIT__", 1)
            _, current_author, current_date = meta.split("|")
        elif line.strip():
            fpath = line.strip()
            entry = history[fpath]
            entry["touch_count"] += 1
            entry["authors"].add(current_author)
            d = datetime.strptime(current_date, "%Y-%m-%d")
            if entry["first_seen"] is None or d < entry["first_seen"]:
                entry["first_seen"] = d
            if entry["last_touched"] is None or d > entry["last_touched"]:
                entry["last_touched"] = d

    return history
