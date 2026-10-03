"""
CodeSweep (formerly DebtLedger) — Website

Two ways to scan:
  1. Paste a public GitHub repo URL — reads code + git history.
  2. Upload code files directly — reads code only (no history exists for
     uploads). Uploaded files are processed fully in memory and are
     NEVER written to disk or stored anywhere — read once, scanned, and
     discarded as soon as the response is sent.
"""

import os
import shutil
import subprocess
import tempfile
import uuid

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List

from debt_scorer import score_debt, score_uploaded_debt

app = FastAPI(title="CodeSweep")
templates = Jinja2Templates(directory="templates")

SCAN_ROOT = tempfile.gettempdir()


def clone_repo(github_url: str) -> str:
    scan_id = str(uuid.uuid4())[:8]
    dest = os.path.join(SCAN_ROOT, f"codesweep_{scan_id}")
    subprocess.run(["git", "clone", "--depth", "50", github_url, dest],
                    capture_output=True, text=True, timeout=120)
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
        request=request, name="report.html",
        context={"repo_url": repo_url, "top_debt": top_debt, "error": error, "providers": PROVIDERS},
    )


@app.post("/scan-files", response_class=HTMLResponse)
async def scan_files(request: Request, files: List[UploadFile] = File(...)):
    """
    Reads every uploaded file straight into memory, scans for duplication,
    then the bytes go out of scope and are gone — nothing is written to
    disk, nothing is saved to any database.
    """
    error = None
    top_debt = []
    skipped = []
    filenames = []

    try:
        in_memory_files = []
        for f in files:
            raw = await f.read()           # read into memory only
            in_memory_files.append((f.filename, raw))
            filenames.append(f.filename)
        if not in_memory_files:
            error = "No files were uploaded."
        else:
            top_debt, skipped = score_uploaded_debt(in_memory_files, top_n=10)
    except Exception as e:
        error = f"Something went wrong scanning those files: {e}"
    # nothing to clean up on disk — nothing was ever written there

    return templates.TemplateResponse(
        request=request, name="upload_report.html",
        context={
            "filenames": filenames, "top_debt": top_debt, "skipped": skipped,
            "error": error, "providers": PROVIDERS,
        },
    )


# ---------------------------------------------------------------------------
# AI-suggested fix — works with any of 5 providers, visitor's own key,
# never saved. Text suggestion only, never edits real code.
# ---------------------------------------------------------------------------
import requests

PROVIDERS = {
    "gemini": {"label": "Gemini (Google)", "type": "gemini", "default_model": "gemini-3.6-flash"},
    "openai": {"label": "ChatGPT (OpenAI)", "type": "openai_compatible", "base_url": "https://api.openai.com/v1", "default_model": "gpt-5.1"},
    "grok": {"label": "Grok (xAI)", "type": "openai_compatible", "base_url": "https://api.x.ai/v1", "default_model": "grok-4"},
    "perplexity": {"label": "Perplexity", "type": "openai_compatible", "base_url": "https://api.perplexity.ai", "default_model": "sonar-pro"},
    "claude": {"label": "Claude (Anthropic)", "type": "anthropic", "base_url": "https://api.anthropic.com/v1", "default_model": "claude-sonnet-5"},
}


def build_prompt(files: list, sample_code: str) -> str:
    return f"""You are helping a developer clean up duplicated code.

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


def call_gemini(api_key: str, model: str, prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def call_openai_compatible(base_url: str, api_key: str, model: str, prompt: str) -> str:
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    r = requests.post(url, json=body, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def call_anthropic(api_key: str, model: str, prompt: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    body = {"model": model, "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]}
    r = requests.post(url, json=body, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def suggest_fix(files: list, sample_code: str, provider: str, api_key: str, model_override: str = "") -> str:
    if not api_key or not api_key.strip():
        return "(No API key was entered, so no suggestion could be generated.)"
    provider_info = PROVIDERS.get(provider)
    if not provider_info:
        return f"(Unknown provider: {provider})"
    model = model_override.strip() if model_override and model_override.strip() else provider_info["default_model"]
    prompt = build_prompt(files, sample_code)
    api_key = api_key.strip()
    try:
        if provider_info["type"] == "gemini":
            return call_gemini(api_key, model, prompt)
        elif provider_info["type"] == "openai_compatible":
            return call_openai_compatible(provider_info["base_url"], api_key, model, prompt)
        elif provider_info["type"] == "anthropic":
            return call_anthropic(api_key, model, prompt)
    except Exception as e:
        return (f"(Couldn't get a suggestion from {provider_info['label']} — the key may be "
                f"invalid, out of quota, or the model name '{model}' may have changed. Error detail: {e})")


@app.post("/suggest-fix", response_class=HTMLResponse)
def suggest_fix_route(
    request: Request, files: str = Form(...), sample: str = Form(...),
    provider: str = Form("gemini"), api_key: str = Form(""), model_override: str = Form(""),
):
    file_list = files.split("|||")
    plan = suggest_fix(file_list, sample, provider, api_key, model_override)
    return templates.TemplateResponse(
        request=request, name="suggestion.html",
        context={"files": file_list, "sample": sample, "plan": plan,
                  "provider_label": PROVIDERS.get(provider, {}).get("label", provider)},
    )
