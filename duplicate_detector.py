"""
CodeSweep — Duplicate Code Detector

Reads code as text and compares small chunks to find duplication.
No code is ever executed. Works in two modes:
  1. On a cloned GitHub repo (disk-based, iter_code_files)
  2. On files a visitor uploaded directly (in-memory, never written to disk)
"""

import hashlib
import os
from collections import defaultdict
from pathlib import Path

CHUNK_SIZE = 6
MIN_CHUNK_CHARS = 40
CODE_EXTENSIONS = {".kt", ".java", ".py", ".js", ".ts", ".tsx", ".jsx",
                    ".css", ".html", ".xml", ".json", ".swift", ".go", ".rb", ".c", ".cpp", ".h"}


def normalize_line(line: str) -> str:
    return line.strip()


def is_noise_chunk(lines: list) -> bool:
    non_trivial = [l for l in lines if l and l not in {"}", "{", ")", "(", ""}]
    if not non_trivial:
        return True
    import_lines = sum(1 for l in lines if l.startswith("import "))
    if import_lines >= len(lines) * 0.5:
        return True
    return False


def chunk_lines(lines: list):
    """Yield (start_line, chunk_text) tuples from an already-split list of lines."""
    norm = [normalize_line(l) for l in lines]
    for i in range(len(norm) - CHUNK_SIZE + 1):
        window = norm[i:i + CHUNK_SIZE]
        joined = "".join(window)
        if len(joined) < MIN_CHUNK_CHARS:
            continue
        if is_noise_chunk(window):
            continue
        yield i + 1, "\n".join(window)


# --- disk-based mode (cloned GitHub repos) ---------------------------------

def iter_code_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in
                        {".git", "build", ".gradle", "node_modules", "dist", "__pycache__"}]
        for fname in filenames:
            if Path(fname).suffix in CODE_EXTENSIONS:
                yield os.path.join(dirpath, fname)


def chunk_file(filepath: str):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    yield from chunk_lines(lines)


def find_duplicates(root: str):
    seen = defaultdict(list)
    for filepath in iter_code_files(root):
        rel = os.path.relpath(filepath, root)
        for start_line, chunk_text in chunk_file(filepath):
            h = hashlib.sha1(chunk_text.encode("utf-8")).hexdigest()
            seen[h].append((rel, start_line, chunk_text))
    return {h: locs for h, locs in seen.items() if len(locs) > 1}


# --- in-memory mode (files a visitor uploaded, never written to disk) -----

def is_probably_text(raw: bytes) -> bool:
    """Quick check so we don't try to chunk binary files (PDFs, images) as
    if they were code — that would just produce garbage matches."""
    if b"\x00" in raw[:2000]:
        return False
    try:
        raw[:4000].decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def find_duplicates_in_memory(uploaded_files: list):
    """
    uploaded_files: list of (filename, raw_bytes) tuples, already read into
    memory by the caller. Nothing here touches disk.
    Returns: (duplicates dict, skipped_files list of filenames that were
    binary/not analyzable as code)
    """
    seen = defaultdict(list)
    skipped = []

    for filename, raw in uploaded_files:
        if not is_probably_text(raw):
            skipped.append(filename)
            continue
        text = raw.decode("utf-8", errors="ignore")
        lines = text.splitlines(keepends=True)
        for start_line, chunk_text in chunk_lines(lines):
            h = hashlib.sha1(chunk_text.encode("utf-8")).hexdigest()
            seen[h].append((filename, start_line, chunk_text))

    duplicates = {h: locs for h, locs in seen.items() if len(locs) > 1}
    return duplicates, skipped
