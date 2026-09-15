"""
DebtLedger — Debt Scorer & Ranker (V1, piece 3)

What this does, in plain words:
    Takes the results from the duplicate-code finder and the git-history
    tracker, and combines them into a single score per debt item — then
    ranks the top ones worth fixing first.

The scoring idea (kept simple and explainable on purpose):
    A duplicate block is "worse" debt if:
      - it appears in MORE places (more places to keep in sync / more risk)
      - those files get touched OFTEN (every future edit risks spreading
        or worsening the mess)
      - those files are touched by MULTIPLE people (more chance of
        inconsistent fixes / miscommunication)

    debt_score = places_duplicated * avg_touch_count_of_files_involved

    This is a simple, explainable starting formula — not a black box.
    It can be refined later (e.g. weighting recent changes more), but
    for V1 it already produces genuinely useful rankings, as you'll see
    below.

Estimated cost/savings (kept honest and simple for V1):
    fix_cost_hours = 0.5 hours per place the duplicate needs to be merged
    (rough placeholder — refined later with real function-size data)
    est_future_cost_hours = touch_count_of_files_involved * 0.25 hours
    (rough estimate of time already "spent" dealing with a file that
    keeps needing repeated changes because of the duplication)
"""

import sys
from duplicate_detector import find_duplicates
from history_tracker import file_history


def score_debt(repo_path: str, top_n: int = 10):
    dupes = find_duplicates(repo_path)
    history = file_history(repo_path)

    # group duplicate chunks by the exact set of files they involve,
    # so we don't score the same duplicated block multiple times because
    # of sliding-window overlap
    grouped = {}
    for h, locs in dupes.items():
        files_involved = tuple(sorted(set(f for f, _, _ in locs)))
        if len(files_involved) < 2:
            continue
        if files_involved not in grouped:
            grouped[files_involved] = {"count": 0, "sample": locs[0][2]}
        grouped[files_involved]["count"] += 1

    scored = []
    for files_involved, info in grouped.items():
        touch_counts = []
        for f in files_involved:
            h = history.get(f)
            touch_counts.append(h["touch_count"] if h else 0)

        if not touch_counts:
            continue

        avg_touches = sum(touch_counts) / len(touch_counts)
        places = len(files_involved)

        debt_score = places * avg_touches
        fix_cost_hours = round(places * 0.5, 1)
        est_future_cost_hours = round(sum(touch_counts) * 0.25, 1)
        roi = round(est_future_cost_hours / fix_cost_hours, 1) if fix_cost_hours else 0

        scored.append({
            "files": files_involved,
            "places": places,
            "avg_touches": round(avg_touches, 1),
            "debt_score": round(debt_score, 1),
            "fix_cost_hours": fix_cost_hours,
            "est_future_cost_hours": est_future_cost_hours,
            "roi": roi,
            "sample": info["sample"],
        })

    scored.sort(key=lambda x: -x["debt_score"])
    return scored[:top_n]


def report(repo_path: str, top_n: int = 10):
    top = score_debt(repo_path, top_n)

    print(f"\n{'='*70}")
    print(f"  DEBTLEDGER — TOP {len(top)} ITEMS WORTH FIXING FIRST")
    print(f"{'='*70}\n")

    for i, item in enumerate(top, 1):
        print(f"#{i}  Debt score: {item['debt_score']}   ROI: {item['roi']}x")
        print(f"     Duplicated across {item['places']} files (avg {item['avg_touches']} edits each):")
        for f in item["files"]:
            print(f"        - {f}")
        print(f"     Estimated fix time:      {item['fix_cost_hours']} hrs")
        print(f"     Estimated cost so far:   {item['est_future_cost_hours']} hrs")
        print(f"     Sample code:")
        for line in item["sample"].split("\n")[:2]:
            print(f"        {line}")
        print()

    return top


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    report(target)
