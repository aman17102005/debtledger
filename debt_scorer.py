"""
CodeSweep — Debt Scorer & Ranker

Two scorers:
  score_debt()            — for a cloned GitHub repo (has git history,
                             so we can estimate real cost/ROI).
  score_uploaded_debt()    — for files a visitor uploaded directly (no
                             history exists, so we can only rank by how
                             widely duplicated the code is, honestly,
                             with no invented cost numbers).
"""

from duplicate_detector import find_duplicates, find_duplicates_in_memory
from history_tracker import file_history


def _group_by_files(dupes: dict):
    grouped = {}
    for h, locs in dupes.items():
        files_involved = tuple(sorted(set(f for f, _, _ in locs)))
        if len(files_involved) < 2:
            continue
        if files_involved not in grouped:
            grouped[files_involved] = {"count": 0, "sample": locs[0][2]}
        grouped[files_involved]["count"] += 1
    return grouped


def score_debt(repo_path: str, top_n: int = 10):
    dupes = find_duplicates(repo_path)
    history = file_history(repo_path)
    grouped = _group_by_files(dupes)

    scored = []
    for files_involved, info in grouped.items():
        touch_counts = [history.get(f, {}).get("touch_count", 0) for f in files_involved]
        if not touch_counts:
            continue
        avg_touches = sum(touch_counts) / len(touch_counts)
        places = len(files_involved)
        debt_score = places * avg_touches
        fix_cost_hours = round(places * 0.5, 1)
        est_future_cost_hours = round(sum(touch_counts) * 0.25, 1)
        roi = round(est_future_cost_hours / fix_cost_hours, 1) if fix_cost_hours else 0

        # Debt timeline: when each file involved first shows up in the git
        # history we read. This is an honest approximation — it tells us when
        # each file was added, not the exact moment the duplicated block
        # was pasted into it.
        timeline = []
        for f in files_involved:
            first = history.get(f, {}).get("first_seen")
            if first:
                timeline.append({"date": first.strftime("%d %b %Y"), "sort": first.timestamp(), "file": f.split("/")[-1]})
        timeline.sort(key=lambda t: t["sort"])

        scored.append({
            "files": files_involved, "places": places, "avg_touches": round(avg_touches, 1),
            "debt_score": round(debt_score, 1), "fix_cost_hours": fix_cost_hours,
            "est_future_cost_hours": est_future_cost_hours, "roi": roi, "sample": info["sample"],
            "timeline": timeline,
        })

    scored.sort(key=lambda x: -x["debt_score"])
    return scored[:top_n]


def score_uploaded_debt(uploaded_files: list, top_n: int = 10):
    """
    uploaded_files: list of (filename, raw_bytes) tuples.
    No git history exists for these, so this ranks purely by how many
    places the same code block appears in — no fabricated time/cost
    numbers are shown for uploads, since we have no real data for those.
    """
    dupes, skipped = find_duplicates_in_memory(uploaded_files)
    grouped = _group_by_files(dupes)

    scored = []
    for files_involved, info in grouped.items():
        places = len(files_involved)
        scored.append({
            "files": files_involved,
            "places": places,
            "debt_score": places,  # honest: just "how many places", no history to weight it
            "sample": info["sample"],
        })

    scored.sort(key=lambda x: -x["debt_score"])
    return scored[:top_n], skipped
