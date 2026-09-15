"""
DebtLedger — Git History Tracker (V1, piece 2)

What this does, in plain words:
    Reads the project's saved git history (the record of every past change)
    and, for each file, works out:
        - when it was first added
        - how many times it has been changed since
        - how many different people have changed it
        - when it was last touched

    This is what lets DebtLedger later say things like "this file has been
    touched 27 times by 4 different people since it was added" — the
    "tracking over time" part that a normal one-time code scanner can't do.

No code is executed here either — git log just reads saved history, same
idea as reading a diary of past events.
"""

import subprocess
from collections import defaultdict
from datetime import datetime


def run_git(repo_path: str, *args):
    result = subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True, text=True
    )
    return result.stdout


def file_history(repo_path: str):
    """
    Returns a dict: filepath -> {
        'first_seen': date,
        'last_touched': date,
        'touch_count': int,
        'authors': set of author names,
    }
    """
    # --follow tracks a file even if renamed; --name-only lists files per commit
    log_output = run_git(
        repo_path, "log",
        "--pretty=format:__COMMIT__%H|%an|%ad",
        "--date=short",
        "--name-only"
    )

    history = defaultdict(lambda: {
        "first_seen": None,
        "last_touched": None,
        "touch_count": 0,
        "authors": set(),
    })

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


def report(repo_path: str, top_n: int = 15):
    history = file_history(repo_path)
    today = datetime.today()

    rows = []
    for fpath, info in history.items():
        if not fpath.endswith((".kt", ".java", ".py", ".js", ".ts", ".tsx")):
            continue
        age_days = (today - info["first_seen"]).days if info["first_seen"] else 0
        rows.append({
            "file": fpath,
            "age_days": age_days,
            "touch_count": info["touch_count"],
            "author_count": len(info["authors"]),
            "last_touched": info["last_touched"].date() if info["last_touched"] else None,
        })

    # most-touched files first — these are the "hot" files most likely to
    # be where debt accumulates, since every change to them is a chance to
    # make the mess worse (or better)
    rows.sort(key=lambda r: -r["touch_count"])

    print(f"Repo: {repo_path}")
    print(f"Tracked code files: {len(rows)}\n")
    print(f"{'File':<65} {'Age(days)':>10} {'Touches':>8} {'Authors':>8} {'Last touched':>13}")
    print("-" * 108)
    for r in rows[:top_n]:
        print(f"{r['file']:<65} {r['age_days']:>10} {r['touch_count']:>8} {r['author_count']:>8} {str(r['last_touched']):>13}")

    return rows


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    report(target)
