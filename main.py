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
