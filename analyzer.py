"""
CodeSweep — Complexity & Dead Code Analyzer

Two more "read, don't run" checks, same philosophy as the duplicate
detector:

  1. Complex functions — a function with too many nested decisions
     (if/else/when/for/while/&&/||) is harder to understand and more
     likely to hide bugs. We count these decision points per function
     as a simple, honest stand-in for "how complicated is this" — not
     a perfect academic complexity score, just a useful signal.

  2. Dead code — a function that is DEFINED but never CALLED anywhere
     else in the codebase is very likely unused leftover code. We check
     this by counting how many times the function's name appears
     elsewhere in the project, outside its own definition.

Honest limits (same spirit as the rest of the project):
  - This is pattern-matching on text, not a real compiler. It can miss
    functions called through reflection, dynamic dispatch, or frameworks
    that call things by convention (e.g. Android lifecycle methods like
    onCreate). We deliberately whitelist a few extremely common
    "framework-called" names so they aren't wrongly flagged as dead.
"""

import os
import re
from pathlib import Path

CODE_EXTENSIONS = {".kt", ".java", ".py", ".js", ".ts", ".tsx", ".jsx", ".swift", ".go"}

# Function-definition patterns, chosen by file type so one language's
# syntax doesn't produce false matches in another.
KOTLIN_PATTERN = re.compile(r'\bfun\s+(?:<[^>]*>\s*)?(?:[\w<>?,\s]+\.)?(\w+)\s*\(')
PYTHON_PATTERN = re.compile(r'\bdef\s+(\w+)\s*\(')
JS_PATTERN = re.compile(r'\bfunction\s+(\w+)\s*\(')
C_LIKE_PATTERN = re.compile(r'\b(?:public|private|protected|static|final|void|int|long|double|float|boolean|String|[A-Z]\w*)\s+(\w+)\s*\([^;{]*\)\s*(?:throws [\w., ]+)?\{')

PATTERNS_BY_EXT = {
    ".kt": [KOTLIN_PATTERN],
    ".py": [PYTHON_PATTERN],
    ".js": [JS_PATTERN], ".jsx": [JS_PATTERN], ".ts": [JS_PATTERN], ".tsx": [JS_PATTERN],
    ".java": [C_LIKE_PATTERN], ".swift": [re.compile(r'\bfunc\s+(\w+)\s*\(')],
    ".go": [re.compile(r'\bfunc\s+(?:\([^)]*\)\s*)?(\w+)\s*\(')],
}

# Words that can look like a function name to a simple text pattern but
# are really language keywords or common built-in helpers.
NOT_REAL_FUNCTIONS = {
    "if", "else", "for", "while", "when", "switch", "catch", "return", "try",
    "remember", "rememberSaveable", "derivedStateOf", "mutableStateOf", "launch",
    "async", "lazy", "run", "let", "apply", "also", "with", "use",
}

DECISION_KEYWORDS = re.compile(
    r'\b(if|else if|else|when|switch|case|for|while|catch)\b|&&|\|\|'
)

# Common framework-called function names — never flag these as dead, since
# something outside the repo's own text calls them (Android, Flask, etc.)
FRAMEWORK_WHITELIST = {
    "main", "onCreate", "onStart", "onResume", "onPause", "onStop", "onDestroy",
    "onViewCreated", "onCreateView", "onBindViewHolder", "onCreateViewHolder",
    "__init__", "__str__", "__repr__", "setUp", "tearDown", "componentDidMount",
    "render", "build", "equals", "hashCode", "toString", "compareTo",
    # Android pieces the system calls by itself
    "doWork", "onReceive", "onBind", "onStartCommand", "onNewIntent", "onActivityResult",
    "onRequestPermissionsResult", "onSaveInstanceState", "onConfigurationChanged",
    "onBackPressed", "onCreateOptionsMenu", "onOptionsItemSelected", "attachBaseContext",
}

# Parts of a file path that mean "this is test code, not real app code".
TEST_PATH_PARTS = {"test", "tests", "androidtest", "__tests__", "spec", "specs"}


def is_test_file(path: str) -> bool:
    parts = [p.lower() for p in re.split(r"[\\/]", path)]
    if any(p in TEST_PATH_PARTS for p in parts[:-1]):
        return True
    name = parts[-1]
    return (
        name.startswith("test_") or name.endswith("_test.py")
        or name.endswith(("test.kt", "tests.kt", "test.java", "tests.java"))
        or ".test." in name or ".spec." in name
    )

COMPLEXITY_THRESHOLD = 8   # decision points before we call a function "complex"


def iter_code_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in
                        {".git", "build", ".gradle", "node_modules", "dist", "__pycache__"}]
        for fname in filenames:
            if Path(fname).suffix in CODE_EXTENSIONS:
                yield os.path.join(dirpath, fname)


def extract_functions(text: str, filename: str = ""):
    """
    Very approximate function-boundary extraction: finds each function
    definition line, then grabs the lines up to the next definition as that
    function's rough body. Good enough for a V1 signal, not a real parser.
    """
    patterns = PATTERNS_BY_EXT.get(Path(filename).suffix, [KOTLIN_PATTERN, PYTHON_PATTERN, JS_PATTERN])
    lines = text.splitlines()
    matches = []
    for i, line in enumerate(lines):
        for pattern in patterns:
            m = pattern.search(line)
            if m and m.group(1) not in NOT_REAL_FUNCTIONS:
                matches.append((i, m.group(1)))
                break

    functions = []
    for idx, (start_line, name) in enumerate(matches):
        end_line = matches[idx + 1][0] if idx + 1 < len(matches) else len(lines)
        body = "\n".join(lines[start_line:end_line])
        header = lines[start_line]
        above = " ".join(lines[max(0, start_line - 3):start_line])
        functions.append({"name": name, "start_line": start_line + 1, "body": body,
                          "header": header, "above": above})
    return functions


def analyze_complexity(file_contents: list):
    """
    file_contents: list of (filename, text) tuples.
    Returns a ranked list of the most complex functions found.
    """
    results = []
    for filename, text in file_contents:
        if is_test_file(filename):
            continue
        for fn in extract_functions(text, filename):
            decisions = len(DECISION_KEYWORDS.findall(fn["body"]))
            if decisions >= COMPLEXITY_THRESHOLD:
                results.append({
                    "file": filename, "function": fn["name"],
                    "line": fn["start_line"], "decision_points": decisions,
                })
    results.sort(key=lambda r: -r["decision_points"])
    return results


def analyze_dead_code(file_contents: list):
    """
    file_contents: list of (filename, text) tuples (the WHOLE codebase,
    since we need to search every file for calls to each function).
    Returns a list of functions that are defined once and never
    referenced anywhere else.
    """
    all_text = "\n".join(text for _, text in file_contents)
    results = []

    for filename, text in file_contents:
        if is_test_file(filename):
            continue   # test code is allowed to be "uncalled" — the test runner calls it
        for fn in extract_functions(text, filename):
            name = fn["name"]
            if name in FRAMEWORK_WHITELIST or name.startswith("test") or name.startswith("_"):
                continue
            if name.startswith("Preview") or name.endswith("Preview"):
                continue
            # "override" functions and annotated entry points are called by
            # the framework, not by our own code
            if re.search(r"\boverride\b", fn["header"]):
                continue
            if re.search(r"@(Preview|Test|Override|JvmStatic|BindingAdapter|OnLifecycleEvent|Provides|Binds)", fn["above"] + " " + fn["header"]):
                continue
            # count occurrences of the name as a whole word, anywhere in the
            # codebase, then subtract 1 for its own definition line
            occurrences = len(re.findall(r'\b' + re.escape(name) + r'\b', all_text))
            if occurrences <= 1:
                results.append({"file": filename, "function": name, "line": fn["start_line"]})

    return results


def analyze_disk_repo(root: str):
    """Disk-based entry point (for cloned GitHub repos)."""
    file_contents = []
    for filepath in iter_code_files(root):
        rel = os.path.relpath(filepath, root)
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            file_contents.append((rel, f.read()))
    app_files = [(f, t) for f, t in file_contents if not is_test_file(f)]
    return analyze_complexity(file_contents), analyze_dead_code(file_contents), app_files


def analyze_uploaded(uploaded_files: list):
    """
    In-memory entry point (for uploaded files). uploaded_files is a list
    of (filename, raw_bytes) — we only analyze the ones that decode as
    text; binary files are skipped (caller already knows which were
    skipped from the duplicate-detector pass).
    """
    file_contents = []
    for filename, raw in uploaded_files:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if Path(filename).suffix in CODE_EXTENSIONS:
            file_contents.append((filename, text))
    app_files = [(f, t) for f, t in file_contents if not is_test_file(f)]
    return analyze_complexity(file_contents), analyze_dead_code(file_contents), app_files
