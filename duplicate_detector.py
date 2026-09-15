"""
DebtLedger — Duplicate Code Detector (V1, piece 1)

What this does, in plain words:
    Reads every code file, breaks it into small "chunks" (groups of lines),
    and checks if the same chunk appears more than once anywhere in the
    codebase. No code is ever executed — this is pure reading/comparison,
    like finding repeated paragraphs in an essay.

Why chunk-based hashing:
    Works the same way regardless of programming language (Kotlin, Python,
    JS, whatever) since it just compares normalized text, not language
    grammar. That keeps V1 simple and language-agnostic.
"""

import hashlib
import os
from collections import defaultdict
from pathlib import Path

CHUNK_SIZE = 6          # lines per chunk — small enough to catch real duplication
MIN_CHUNK_CHARS = 40    # ignore trivial chunks (blank lines, single braces, etc.)
CODE_EXTENSIONS = {".kt", ".java", ".py", ".js", ".ts", ".tsx", ".jsx"}


def normalize_line(line: str) -> str:
    """Strip whitespace so indentation differences don't break matches."""
    return line.strip()


def is_noise_chunk(lines: list) -> bool:
    """
    Returns True for chunks that are 'normal' expected repetition, not
    real debt — e.g. import statements, or chunks that are almost
    entirely punctuation/braces with barely any real logic in them.
    """
    non_trivial = [l for l in lines if l and l not in {"}", "{", ")", "(", ""}]
    if not non_trivial:
        return True

    import_lines = sum(1 for l in lines if l.startswith("import "))
    if import_lines >= len(lines) * 0.5:
        return True  # mostly import statements — expected, not debt

    return False


def iter_code_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        # skip build/dependency folders — not real source code
        dirnames[:] = [d for d in dirnames if d not in
                        {".git", "build", ".gradle", "node_modules", "dist", "__pycache__"}]
        for fname in filenames:
            if Path(fname).suffix in CODE_EXTENSIONS:
                yield os.path.join(dirpath, fname)


def chunk_file(filepath: str):
    """Yield (start_line, chunk_text) tuples for a file."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = [normalize_line(l) for l in f.readlines()]

    for i in range(len(lines) - CHUNK_SIZE + 1):
        window = lines[i:i + CHUNK_SIZE]
        # skip chunks that are mostly blank/trivial lines
        joined = "".join(window)
        if len(joined) < MIN_CHUNK_CHARS:
            continue
        if is_noise_chunk(window):
            continue
        yield i + 1, "\n".join(window)


def find_duplicates(root: str):
    """
    Returns a dict: hash -> list of (filepath, start_line, chunk_text)
    for every chunk that appears 2+ times.
    """
    seen = defaultdict(list)

    for filepath in iter_code_files(root):
        rel = os.path.relpath(filepath, root)
        for start_line, chunk_text in chunk_file(filepath):
            h = hashlib.sha1(chunk_text.encode("utf-8")).hexdigest()
            seen[h].append((rel, start_line, chunk_text))

    duplicates = {h: locs for h, locs in seen.items() if len(locs) > 1}
    return duplicates


def report(root: str):
    dupes = find_duplicates(root)

    # Merge overlapping/adjacent duplicate chunks per file-pair so we don't
    # spam the report with every sliding-window overlap of the same block.
    grouped = []
    for h, locs in dupes.items():
        files_involved = sorted(set(f for f, _, _ in locs))
        grouped.append((len(locs), files_involved, locs[0][2]))

    grouped.sort(key=lambda x: -x[0])

    print(f"Scanned: {root}")
    print(f"Duplicate chunks found (raw, before merging overlaps): {len(dupes)}\n")

    shown = 0
    seen_pairs = set()
    for count, files_involved, sample_text in grouped:
        pair_key = tuple(files_involved)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        if shown >= 15:
            break
        shown += 1
        print(f"--- Duplicate block seen in {count} places ---")
        for f in files_involved:
            print(f"    {f}")
        print("    sample:")
        for line in sample_text.split("\n")[:3]:
            print(f"        {line}")
        print()

    return dupes


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    report(target)
