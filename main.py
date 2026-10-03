"""
CodeSweep — Website

Scan modes:
  1. Paste a public GitHub repo URL — reads code + git history, saves
     result so repeat scans show what changed since last time, and
     powers a live README badge.
  2. Upload code files directly — reads code only, nothing ever stored.

Checks run: duplicated code, overly complex functions, possibly dead
code — combined into one health score.
"""

import os
import shutil
import subprocess
import tempfile
import uuid
from typing import List

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from debt_scorer import score_debt, score_uploaded_debt
from analyzer import analyze_disk_repo, analyze_uploaded
from health_score import compute_health_score
from history_store import save_scan, get_previous_scan, get_latest_scan
from exporters import build_pdf, build_badge_svg

app = FastAPI(title="CodeSweep")
templates = Jinja2Templates(directory="templates")

SCAN_ROOT = tempfile.gettempdir()


def normalize_repo_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url


def clone_repo(github_url: str) -> str:
    scan_id = str(uuid.uuid4())[:8]
    dest = os.path.join(SCAN_ROOT, f"codesweep_{scan_id}")
    subprocess.run(["git", "clone", "--depth", "50", github_url, dest],
                    capture_output=True, text=True, timeout=120)
    return dest


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="home.html", context={})


def _run_full_repo_scan(repo_url: str):
    norm_url = normalize_repo_url(repo_url)
    repo_dir = clone_repo(repo_url)
    try:
        if not os.path.isdir(os.path.join(repo_dir, ".git")):
            return None, "Couldn't read that repo — check the link is a public GitHub repo URL."

        top_debt = score_debt(repo_dir, top_n=10)
        complex_fns, dead_fns, file_contents = analyze_disk_repo(repo_dir)
        health = compute_health_score(len(top_debt), len(complex_fns), len(dead_fns), len(file_contents))

        save_scan(norm_url, health)
        previous = get_previous_scan(norm_url)

        return {
            "repo_url": repo_url, "norm_url": norm_url, "top_debt": top_debt,
            "complex_fns": complex_fns[:10], "dead_fns": dead_fns[:10],
            "health": health, "previous": previous,
        }, None
    finally:
        if os.path.isdir(repo_dir):
            shutil.rmtree(repo_dir, ignore_errors=True)


@app.post("/scan", response_class=HTMLResponse)
def scan(request: Request, repo_url: str = Form(...)):
    try:
        result, error = _run_full_repo_scan(repo_url)
    except Exception as e:
        result, error = None, f"Something went wrong scanning that repo: {e}"

    context = {"repo_url": repo_url, "error": error, "providers": PROVIDERS,
               "top_debt": [], "complex_fns": [], "dead_fns": [], "health": None, "previous": None}
    if result:
        context.update(result)

    return templates.TemplateResponse(request=request, name="report.html", context=context)


@app.post("/export-pdf")
def export_pdf(repo_url: str = Form(...)):
    try:
        result, error = _run_full_repo_scan(repo_url)
    except Exception as e:
        result, error = None, str(e)

    if not result:
        return Response(content=f"Could not generate PDF: {error}", status_code=400)

    pdf_bytes = build_pdf(result["repo_url"], result["health"], result["top_debt"],
                            result["complex_fns"], result["dead_fns"])
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=codesweep_report.pdf"},
    )


@app.get("/badge/{owner}/{repo}")
def badge(owner: str, repo: str):
    norm_url = normalize_repo_url(f"https://github.com/{owner}/{repo}")
    latest = get_latest_scan(norm_url)
    score = latest["score"] if latest else -1
    svg = build_badge_svg(score)
    return Response(content=svg, media_type="image/svg+xml",
                     headers={"Cache-Control": "no-cache"})


@app.post("/scan-files", response_class=HTMLResponse)
async def scan_files(request: Request, files: List[UploadFile] = File(...)):
    error = None
    top_debt = []
    skipped = []
    filenames = []
    complex_fns = []
    dead_fns = []
    health = None

    try:
        in_memory_files = []
        for f in files:
            raw = await f.read()
            in_memory_files.append((f.filename, raw))
            filenames.append(f.filename)
        if not in_memory_files:
            error = "No files were uploaded."
        else:
            top_debt, skipped = score_uploaded_debt(in_memory_files, top_n=10)
            complex_fns, dead_fns, file_contents = analyze_uploaded(in_memory_files)
            complex_fns, dead_fns = complex_fns[:10], dead_fns[:10]
            health = compute_health_score(len(top_debt), len(complex_fns), len(dead_fns), len(in_memory_files))
    except Exception as e:
        error = f"Something went wrong scanning those files: {e}"

    return templates.TemplateResponse(
        request=request, name="upload_report.html",
        context={
            "filenames": filenames, "top_debt": top_debt, "skipped": skipped,
            "complex_fns": complex_fns, "dead_fns": dead_fns, "health": health,
            "error": error, "providers": PROVIDERS,
        },
    )


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
