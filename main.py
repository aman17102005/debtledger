"""
DebtLedger — Website (V1, piece 4 / step 5)

What this does, in plain words:
    A small website. Someone pastes a public GitHub repo link, clicks
    "Scan", and gets back the ranked "fix this first" debt report —
    the same pipeline we already proved works (duplicate finder +
    git history tracker + debt scorer), just wrapped in a browser page
    instead of a terminal.

Honest scope note for V1:
    - Works with PUBLIC GitHub repos via URL (no login needed yet).
    - "Login with GitHub" (so it could also read PRIVATE repos) is a
      real next step, but it needs a GitHub OAuth App to be registered
      first — a few clicks on GitHub's side that only Aman can do,
      since it has to be tied to his account. Flagged here rather than
      silently skipped.
"""

import os
import shutil
import subprocess
import tempfile
import uuid

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from debt_scorer import score_debt

app = FastAPI(title="DebtLedger")
templates = Jinja2Templates(directory="templates")

SCAN_ROOT = tempfile.gettempdir()

# ---------------------------------------------------------------------------
# PHASE 2: AI-suggested fix.
#
# Important design rule we agreed on: this NEVER edits the user's actual
# code. It only generates a suggested plan/diff as TEXT for a human to read
# and approve. Nothing here writes to GitHub, nothing here runs on its own.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# PHASE 2: AI-suggested fix.
#
# Important design rules we agreed on:
#   1. This NEVER edits the user's actual code — only a suggested plan/diff
#      as TEXT for a human to read and approve.
#   2. The Gemini API key belongs to whoever is USING the website, not the
#      website owner. It's typed in per-request and never saved anywhere
#      (not to disk, not to a database, not logged) — used once for that
#      one request, then forgotten.
# ---------------------------------------------------------------------------

def suggest_fix(files: list, sample_code: str, api_key: str) -> str:
    """
    Asks Gemini to propose a refactor plan for a duplicated code block,
    using the API key the visitor typed in for this one request only.
    Returns plain text: a short, human-readable plan, NOT actual code
    that gets applied anywhere automatically.
    """
    if not api_key or not api_key.strip():
        return "(No API key was entered, so no suggestion could be generated.)"

    import google.generativeai as genai
    try:
        genai.configure(api_key=api_key.strip())
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = f"""You are helping a developer clean up duplicated code in an
Android/Kotlin app built with Jetpack Compose.

The following code block appears duplicated across these files:
{chr(10).join('- ' + f for f in files)}

Sample of the duplicated code:
---
{sample_code}
---

Give a SHORT, plain-English refactor plan (4-6 numbered steps max) for how
a developer should extract this into one shared, reusable piece — without
writing the full final code, just the plan. Be concrete about what to name
the new shared piece and where it should live. Do not add any preamble,
just the numbered plan."""

        response = model.generate_content(
            prompt, request_options={"timeout": 20}
        )
        return response.text
    except Exception as e:
        return (f"(Couldn't get a suggestion — the API key may be invalid, or "
                f"out of free quota for today. Error detail: {e})")


def clone_repo(github_url: str) -> str:
    scan_id = str(uuid.uuid4())[:8]
    dest = os.path.join(SCAN_ROOT, f"debtledger_{scan_id}")
    subprocess.run(
        ["git", "clone", "--depth", "50", github_url, dest],
        capture_output=True, text=True, timeout=120
    )
    return dest


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="home.html", context={})


@app.post("/scan", response_class=HTMLResponse)
def scan(request: Request, repo_url: str = Form(...)):
    error = None
    top_debt = []
    repo_dir = None

    try:
        repo_dir = clone_repo(repo_url)
        if not os.path.isdir(os.path.join(repo_dir, ".git")):
            error = "Couldn't read that repo — check the link is a public GitHub repo URL."
        else:
            top_debt = score_debt(repo_dir, top_n=10)
    except Exception as e:
        error = f"Something went wrong scanning that repo: {e}"
    finally:
        if repo_dir and os.path.isdir(repo_dir):
            shutil.rmtree(repo_dir, ignore_errors=True)

    return templates.TemplateResponse(
        request=request,
        name="report.html",
        context={"repo_url": repo_url, "top_debt": top_debt, "error": error},
    )


@app.post("/suggest-fix", response_class=HTMLResponse)
def suggest_fix_route(
    request: Request,
    files: str = Form(...),
    sample: str = Form(...),
    api_key: str = Form(""),
):
    file_list = files.split("|||")
    plan = suggest_fix(file_list, sample, api_key)
    return templates.TemplateResponse(
        request=request,
        name="suggestion.html",
        context={"files": file_list, "sample": sample, "plan": plan},
    )


