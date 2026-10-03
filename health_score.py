"""
CodeSweep — Health Score

Turns everything we found (duplication, complex functions, dead code)
into one simple number out of 100, so someone can tell at a glance how
messy a codebase is before digging into specifics.

The formula is deliberately simple and explainable — not a black box:
  Start at 100.
  Subtract a fixed penalty per issue found, scaled against codebase size
  so a 500-file project with 10 issues isn't judged the same as a
  20-file project with 10 issues.
"""


def compute_health_score(duplicate_count: int, complex_count: int, dead_count: int, total_files: int) -> dict:
    total_files = max(total_files, 1)  # avoid divide-by-zero on tiny uploads

    issue_density = (duplicate_count + complex_count + dead_count) / total_files

    # Each "issue per file" on average costs up to ~18 points, capped so
    # the score never goes below 0 or above 100.
    penalty = min(issue_density * 18, 100)
    score = round(max(100 - penalty, 0))

    if score >= 85:
        verdict = "Clean"
    elif score >= 65:
        verdict = "Decent, a few things worth fixing"
    elif score >= 40:
        verdict = "Getting messy"
    else:
        verdict = "Needs real attention"

    return {
        "score": score,
        "verdict": verdict,
        "duplicate_count": duplicate_count,
        "complex_count": complex_count,
        "dead_count": dead_count,
        "total_files": total_files,
    }
