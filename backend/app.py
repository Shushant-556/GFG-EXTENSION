
import os
import re
import json
import hashlib
import subprocess
import tempfile
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from google import genai
from google.genai import types

# =========================================================
# CONFIGURATION
# =========================================================

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

log = logging.getLogger("autosolver")

app = FastAPI(
    title="GFG AutoSolver Pro",
    version="3.0.0",
)

# Configure CORS.
# For development, "*" is supported.
# For production, set CORS_ORIGINS in .env.


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "chrome-extension://gkbpmjkhkgnfeelbomhgkhbffgmnccll"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



scheduler = BackgroundScheduler(
    timezone=os.getenv("TIMEZONE", "Asia/Kolkata")
)

last_run = {
    "status": "not_run",
    "at": None,
    "detail": None,
}


# =========================================================
# REQUEST MODEL
# =========================================================

class Problem(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    url: str = Field(default="", max_length=2000)
    statement: str = Field(min_length=10, max_length=50000)
    constraints: str = Field(default="", max_length=12000)
    examples: str = Field(default="", max_length=12000)


# =========================================================
# AUTHENTICATION
# =========================================================

def auth(
    x_autosolver_key: Optional[str] = Header(default=None)
):
    expected = os.getenv("AUTOSOLVER_API_KEY", "").strip()

    if not expected:
        log.warning("AUTOSOLVER_API_KEY is not configured")

    if expected and x_autosolver_key != expected:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
        )


# =========================================================
# HELPERS
# =========================================================

def slugify(text: str) -> str:
    slug = re.sub(
        r"[^a-zA-Z0-9]+",
        "-",
        text.strip(),
    ).strip("-").lower()

    return slug[:100] or "daily-problem"


def unique_slug(problem: Problem) -> str:
    base = slugify(problem.title)

    identity = (
        problem.url.strip()
        or problem.title.strip()
        + problem.statement[:500]
    )

    suffix = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:8]

    return f"{base}-{suffix}"


def parse_json_response(text: str) -> dict:
    text = text.strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")

        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])

        raise RuntimeError(
            "OpenAI returned invalid JSON"
        )


# =========================================================
# OPENAI SOLUTION GENERATION
# =========================================================


# =========================================================
# GEMINI SOLUTION GENERATION
# =========================================================

def model_solution(problem: Problem) -> dict:

    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing in .env"
        )

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are an expert competitive programming engineer
specializing in Java and algorithms.

Solve the GeeksforGeeks problem below.

Return a JSON object with these fields:
- class_code: complete Java Solution class
- approach: detailed explanation
- correctness: correctness explanation
- time_complexity: time complexity
- space_complexity: space complexity
- edge_cases: important edge cases
- signature_notes: expected method signature

Requirements:
- Use Java.
- Preserve the expected GFG Solution class and method signature.
- Do not create a main method unless required.
- Do not use unsupported libraries.
- Optimize for the supplied constraints.
- Do not invent input/output formats.
- Explain uncertainty about the expected signature.
- Do not include markdown fences inside class_code.

TITLE:
{problem.title}

URL:
{problem.url}

STATEMENT:
{problem.statement}

CONSTRAINTS:
{problem.constraints}

EXAMPLES:
{problem.examples}
"""

    try:
        response = client.models.generate_content(
            model=os.getenv(
                "GEMINI_MODEL",
                "gemini-2.5-flash",
            ),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are an expert competitive programming "
                    "engineer specializing in Java algorithms."
                ),
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

    except Exception as error:
        raise RuntimeError(
            f"Gemini API request failed: {error}"
        )

    output = response.text or ""

    if not output.strip():
        raise RuntimeError(
            "Gemini returned an empty response"
        )

    data = parse_json_response(output)

    required_fields = [
        "class_code",
        "approach",
        "correctness",
        "time_complexity",
        "space_complexity",
        "edge_cases",
        "signature_notes",
    ]

    for field in required_fields:
        if field not in data:
            raise RuntimeError(
                f"Gemini response missing field: {field}"
            )

    code = data["class_code"].strip()

    if not code:
        raise RuntimeError(
            "Gemini returned an empty Java solution"
        )

    if "class Solution" not in code:
        raise RuntimeError(
            "Generated code does not contain class Solution"
        )

    data["class_code"] = code

    return data


# =========================================================
# OPTIONAL JAVA COMPILATION
# =========================================================

def compile_java(code: str) -> dict:

    enabled = (
        os.getenv(
            "JAVA_COMPILE_CHECK",
            "false",
        ).lower()
        == "true"
    )

    if not enabled:
        return {
            "enabled": False,
            "ok": None,
        }

    with tempfile.TemporaryDirectory() as temp_dir:

        java_file = os.path.join(
            temp_dir,
            "Solution.java",
        )

        with open(
            java_file,
            "w",
            encoding="utf-8",
        ) as file:
            file.write(code)

        try:
            result = subprocess.run(
                ["javac", java_file],
                capture_output=True,
                text=True,
                timeout=30,
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "Java compilation timed out"
            )

        return {
            "enabled": True,
            "ok": result.returncode == 0,
            "stdout": result.stdout[-3000:],
            "stderr": result.stderr[-5000:],
        }


# =========================================================
# GITHUB API HELPERS
# =========================================================

def github_config():

    token = os.getenv(
        "GITHUB_TOKEN",
        "",
    ).strip()

    repo = os.getenv(
        "GITHUB_REPO",
        "",
    ).strip()

    branch = os.getenv(
        "GITHUB_BRANCH",
        "main",
    ).strip() or "main"

    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is missing"
        )

    if not repo or repo == "owner/repository":
        raise RuntimeError(
            "GITHUB_REPO must be owner/repository"
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    return repo, branch, headers


def github_request(method, url, headers, **kwargs):

    response = requests.request(
        method,
        url,
        headers=headers,
        timeout=35,
        **kwargs,
    )

    if not response.ok:
        raise RuntimeError(
            f"GitHub API error {response.status_code}: "
            f"{response.text[:1500]}"
        )

    return response.json()


# =========================================================
# ATOMIC TWO-FILE GITHUB COMMIT
# =========================================================

def github_commit_files(files: dict, message: str) -> dict:
    """
    Commit multiple files in one GitHub commit using
    GitHub's Git Trees and Git Commits API.

    files example:
    {
        "gfg/problem.java": "...",
        "gfg/problem.md": "..."
    }
    """

    repo, branch, headers = github_config()

    base_url = (
        f"https://api.github.com/repos/{repo}"
    )

    # 1. Read current branch reference.
    ref = github_request(
        "GET",
        f"{base_url}/git/ref/heads/{branch}",
        headers,
    )

    parent_sha = ref["object"]["sha"]

    # 2. Read current commit.
    parent_commit = github_request(
        "GET",
        f"{base_url}/git/commits/{parent_sha}",
        headers,
    )

    base_tree_sha = parent_commit["tree"]["sha"]

    # 3. Create blobs for files.
    tree_entries = []

    for path, content in files.items():

        blob = github_request(
            "POST",
            f"{base_url}/git/blobs",
            headers,
            json={
                "content": content,
                "encoding": "utf-8",
            },
        )

        tree_entries.append({
            "path": path,
            "mode": "100644",
            "type": "blob",
            "sha": blob["sha"],
        })

    # 4. Create a new tree based on existing tree.
    tree = github_request(
        "POST",
        f"{base_url}/git/trees",
        headers,
        json={
            "base_tree": base_tree_sha,
            "tree": tree_entries,
        },
    )

    # 5. Create a commit.
    commit = github_request(
        "POST",
        f"{base_url}/git/commits",
        headers,
        json={
            "message": message,
            "tree": tree["sha"],
            "parents": [parent_sha],
        },
    )

    commit_sha = commit["sha"]

    # 6. Update branch reference.
    github_request(
        "PATCH",
        f"{base_url}/git/refs/heads/{branch}",
        headers,
        json={
            "sha": commit_sha,
            "force": False,
        },
    )

    return {
        "commit_sha": commit_sha,
        "commit_url": commit["html_url"],
        "files": {
            path: (
                f"https://github.com/{repo}/blob/"
                f"{branch}/{path}"
            )
            for path in files
        },
    }


# =========================================================
# PROCESS PROBLEM
# =========================================================

def process_problem(problem: Problem) -> dict:

    log.info(
        "Processing problem: %s",
        problem.title,
    )

    solution = model_solution(problem)

    code = solution["class_code"].strip() + "\n"

    compilation = compile_java(code)

    if (
        compilation["enabled"]
        and not compilation["ok"]
    ):
        raise RuntimeError(
            "Java compilation failed. "
            "Nothing was committed.\n"
            + compilation.get("stderr", "")[-2000:]
        )

    slug = unique_slug(problem)

    generated_at = datetime.now(
        timezone.utc
    ).isoformat()

    notes = f"""# {problem.title}

- Problem URL: {problem.url or 'Not provided'}
- Generated at UTC: {generated_at}
- Java compilation: {compilation}

## Problem Statement

{problem.statement}

## Constraints

{problem.constraints or 'Not provided'}

## Examples

{problem.examples or 'Not provided'}

## Approach

{solution['approach']}

## Correctness

{solution['correctness']}

## Complexity

- Time: {solution['time_complexity']}
- Space: {solution['space_complexity']}

## Edge Cases

{solution['edge_cases']}

## Signature Notes

{solution['signature_notes']}
"""

    files = {
        f"gfg/{slug}.java": code,
        f"gfg/{slug}.md": notes,
    }

    github_result = github_commit_files(
        files,
        f"GFG AutoSolver: {problem.title}",
    )

    log.info(
        "GitHub commit successful: %s",
        github_result["commit_sha"],
    )

    return {
        "title": problem.title,
        "java_url": github_result["files"][
            f"gfg/{slug}.java"
        ],
        "notes_url": github_result["files"][
            f"gfg/{slug}.md"
        ],
        "commit_url": github_result["commit_url"],
        "commit_sha": github_result["commit_sha"],
        "compile": compilation,
        "solution": solution,
        "sha256": hashlib.sha256(
            code.encode("utf-8")
        ).hexdigest(),
    }


# =========================================================
# DAILY PROBLEM FEED
# =========================================================

def feed_problem() -> Problem:

    feed_url = os.getenv(
        "PROBLEM_FEED_URL",
        "",
    ).strip()

    if not feed_url:
        raise RuntimeError(
            "PROBLEM_FEED_URL is not configured"
        )

    response = requests.get(
        feed_url,
        timeout=25,
    )

    response.raise_for_status()

    return Problem(**response.json())


def run_daily():

    global last_run

    try:
        result = process_problem(
            feed_problem()
        )

        last_run = {
            "status": "success",
            "at": datetime.now(
                timezone.utc
            ).isoformat(),
            "detail": result,
        }

        log.info(
            "Daily run completed: %s",
            result["title"],
        )

    except Exception as error:

        last_run = {
            "status": "error",
            "at": datetime.now(
                timezone.utc
            ).isoformat(),
            "detail": str(error),
        }

        log.exception(
            "Daily execution failed"
        )


# =========================================================
# SCHEDULER
# =========================================================

@app.on_event("startup")
def startup():

    enabled = (
        os.getenv(
            "ENABLE_SCHEDULER",
            "false",
        ).lower()
        == "true"
    )

    feed_url = os.getenv(
        "PROBLEM_FEED_URL",
        "",
    ).strip()

    if not enabled:
        log.info(
            "Scheduler disabled"
        )
        return

    if not feed_url:
        log.warning(
            "Scheduler enabled but no feed URL configured"
        )
        return

    try:

        hour, minute = os.getenv(
            "DAILY_TIME",
            "07:00",
        ).split(":")

        timezone_name = os.getenv(
            "TIMEZONE",
            "Asia/Kolkata",
        )

        scheduler.add_job(
            run_daily,
            CronTrigger(
                hour=int(hour),
                minute=int(minute),
                timezone=timezone_name,
            ),
            id="daily",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        scheduler.start()

        log.info(
            "Scheduler active: %s (%s)",
            os.getenv("DAILY_TIME", "07:00"),
            timezone_name,
        )

    except Exception:

        log.exception(
            "Scheduler initialization failed"
        )

        raise


@app.on_event("shutdown")
def shutdown():

    if scheduler.running:
        scheduler.shutdown(
            wait=False
        )

        log.info(
            "Scheduler stopped"
        )


# =========================================================
# API ENDPOINTS
# =========================================================

@app.get("/health")
def health():

    return {
        "ok": True,
        "service": "GFG AutoSolver Pro",
        "version": "3.0.0",
        "scheduler": scheduler.running,
        "time": datetime.now(
            timezone.utc
        ).isoformat(),
    }


@app.get(
    "/daily/status",
    dependencies=[Depends(auth)],
)
def daily_status():

    return last_run


@app.post(
    "/solve",
    dependencies=[Depends(auth)],
)
def solve(problem: Problem):

    try:

        return process_problem(
            problem
        )

    except Exception as error:

        log.exception(
            "Solve request failed"
        )

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


@app.post(
    "/daily/run",
    dependencies=[Depends(auth)],
)
def daily_run():

    global last_run

    try:

        result = process_problem(
            feed_problem()
        )

        last_run = {
            "status": "success",
            "at": datetime.now(
                timezone.utc
            ).isoformat(),
            "detail": result,
        }

        return result

    except Exception as error:

        log.exception(
            "Manual daily run failed"
        )

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )
