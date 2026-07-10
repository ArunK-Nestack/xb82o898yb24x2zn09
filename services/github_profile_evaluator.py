import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

GITHUB_API = "https://api.github.com"

MAX_REPOS = int(os.getenv("PROFILE_MAX_REPOS", "10"))
README_MAX = int(os.getenv("PROFILE_README_MAX_LEN", "800"))
RECENT_COMMITS = int(os.getenv("PROFILE_RECENT_COMMITS", "5"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

GENERIC_COMMIT_MESSAGES = [
    "initial commit",
    "first commit",
    "add files via upload",
    "create readme",
    "create readme.md",
    "update readme",
    "readme update",
    "uploaded files",
    "create temp",
]


def github_headers(accept: str | None = None) -> dict:
    token = os.getenv("GITHUB_TOKEN", "")

    headers = {
        "Accept": accept or "application/vnd.github+json",
        "User-Agent": "nestack-github-profile-evaluator",
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


def github_get(path_or_url: str, accept: str | None = None):
    url = path_or_url if path_or_url.startswith("http") else f"{GITHUB_API}{path_or_url}"

    response = requests.get(
        url,
        headers=github_headers(accept),
        timeout=30,
    )

    if response.status_code == 404:
        return None

    if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        reset = response.headers.get("x-ratelimit-reset")
        reset_text = datetime.fromtimestamp(int(reset)).isoformat() if reset else "unknown"
        raise RuntimeError(f"GitHub rate limit reached. Reset time: {reset_text}")

    response.raise_for_status()
    return response


def trim_text(text: str = "", max_chars: int = 800) -> str:
    if not text:
        return ""

    cleaned = str(text).replace("\r\n", "\n").strip()

    if len(cleaned) <= max_chars:
        return cleaned

    return cleaned[: max_chars - 3] + "..."


def parse_link_header(link_header: str | None) -> dict:
    links = {}

    if not link_header:
        return links

    for part in link_header.split(","):
        part = part.strip()
        if 'rel="' not in part:
            continue

        try:
            url_part, rel_part = part.split(";", 1)
            url = url_part.strip()[1:-1]
            rel = rel_part.split('rel="', 1)[1].split('"', 1)[0]
            links[rel] = url
        except Exception:
            continue

    return links


def get_commit_message(commit: dict | None) -> str:
    if not commit:
        return ""

    message = commit.get("commit", {}).get("message", "")
    first_line = message.split("\n")[0].strip()

    return trim_text(first_line, 200)


def get_commit_date(commit: dict | None) -> str:
    if not commit:
        return ""

    return (
        commit.get("commit", {}).get("author", {}).get("date")
        or commit.get("commit", {}).get("committer", {}).get("date")
        or ""
    )


def format_duration(start_iso: str | None, end_iso: str | None) -> str:
    if not start_iso or not end_iso:
        return ""

    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    except Exception:
        return ""

    days = abs((end - start).days)

    if days < 1:
        return "Less than 1 day"

    years = days // 365
    months = (days % 365) // 30
    remaining_days = days % 30

    parts = []

    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")

    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")

    if remaining_days:
        parts.append(f"{remaining_days} day{'s' if remaining_days != 1 else ''}")

    return ", ".join(parts) if parts else "Less than 1 day"


def format_languages(language_map: dict | None) -> str:
    if not language_map or not isinstance(language_map, dict):
        return ""

    total = sum(language_map.values())

    if total <= 0:
        return ""

    parts = []

    for language, byte_count in sorted(language_map.items(), key=lambda item: item[1], reverse=True):
        percent = round((byte_count / total) * 100)
        parts.append(f"{language} {percent}%")

    return ", ".join(parts)


def fetch_user_repositories(username: str) -> list[dict]:
    repos = []
    path = f"/users/{username}/repos?sort=updated&per_page=100&type=owner"

    while path:
        response = github_get(path)

        if not response:
            break

        data = response.json()

        if not isinstance(data, list):
            break

        for repo in data:
            if not repo.get("fork"):
                repos.append(repo)

        links = parse_link_header(response.headers.get("link"))
        next_url = links.get("next")

        if not next_url:
            break

        path = next_url

    return repos


def fetch_commit_metadata(username: str, repo_name: str) -> dict:
    response = github_get(f"/repos/{username}/{repo_name}/commits?per_page=1")

    if not response:
        return {
            "commits": 0,
            "duration": "",
            "firstMessage": "",
            "recentCommits": "",
            "firstDate": "",
            "lastDate": "",
        }

    newest_list = response.json()

    if not newest_list:
        return {
            "commits": 0,
            "duration": "",
            "firstMessage": "",
            "recentCommits": "",
            "firstDate": "",
            "lastDate": "",
        }

    newest_commit = newest_list[0]
    oldest_commit = newest_commit
    commit_count = 1

    links = parse_link_header(response.headers.get("link"))
    last_url = links.get("last")

    if last_url:
        try:
            if "page=" in last_url:
                commit_count = int(last_url.split("page=", 1)[1].split("&", 1)[0])
        except Exception:
            commit_count = 1

        last_response = github_get(last_url)
        if last_response:
            last_page = last_response.json()
            if last_page:
                oldest_commit = last_page[-1]
    else:
        bulk_response = github_get(f"/repos/{username}/{repo_name}/commits?per_page=100")
        if bulk_response:
            bulk_data = bulk_response.json()
            commit_count = len(bulk_data)
            if bulk_data:
                oldest_commit = bulk_data[-1]

    recent_response = github_get(
        f"/repos/{username}/{repo_name}/commits?per_page={RECENT_COMMITS}"
    )

    recent_messages = []

    if recent_response:
        for commit in recent_response.json():
            message = get_commit_message(commit)
            if message:
                recent_messages.append(message)

    first_date = get_commit_date(oldest_commit)
    last_date = get_commit_date(newest_commit)

    return {
        "commits": commit_count,
        "duration": format_duration(first_date, last_date),
        "firstMessage": get_commit_message(oldest_commit),
        "recentCommits": " | ".join(recent_messages),
        "firstDate": first_date,
        "lastDate": last_date,
    }


def fetch_readme(username: str, repo_name: str) -> str:
    response = github_get(
        f"/repos/{username}/{repo_name}/readme",
        accept="application/vnd.github.raw",
    )

    if not response:
        return ""

    return trim_text(response.text, README_MAX)


def fetch_languages(username: str, repo_name: str) -> str:
    response = github_get(f"/repos/{username}/{repo_name}/languages")

    if not response:
        return ""

    return format_languages(response.json())


def fetch_active_weeks(username: str, repo_name: str) -> int:
    path = f"/repos/{username}/{repo_name}/stats/participation"

    for attempt in range(1, 5):
        response = github_get(path)

        if not response:
            return 0

        if response.status_code == 202:
            time.sleep(2 + attempt)
            continue

        data = response.json()

        if isinstance(data, dict) and isinstance(data.get("owner"), list):
            return len([week for week in data["owner"] if week and week > 0])

        return 0

    return 0


def fetch_repo_profile(username: str, repo: dict, repo_num: int) -> dict:
    repo_name = repo.get("name", "")
    repo_url = repo.get("html_url", f"https://github.com/{username}/{repo_name}")

    commit_data = fetch_commit_metadata(username, repo_name)

    return {
        "repoNum": repo_num,
        "repoName": repo_name,
        "repoUrl": repo_url,
        "commits": commit_data.get("commits", 0),
        "duration": commit_data.get("duration", ""),
        "firstMessage": commit_data.get("firstMessage", ""),
        "recentCommits": commit_data.get("recentCommits", ""),
        "languages": fetch_languages(username, repo_name),
        "readmeExcerpt": fetch_readme(username, repo_name),
        "lastPushed": (repo.get("pushed_at") or "")[:10],
        "activeWeeks": fetch_active_weeks(username, repo_name),
        "enrichStatus": "ok",
    }


def safe_number(value, default=0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def is_short_duration(repo: dict) -> bool:
    return "less than 1 day" in str(repo.get("duration", "")).lower()


def has_generic_commit(repo: dict) -> bool:
    text = f"{repo.get('firstMessage', '')} {repo.get('recentCommits', '')}".lower()
    return any(message in text for message in GENERIC_COMMIT_MESSAGES)


def has_useful_readme(repo: dict) -> bool:
    readme = str(repo.get("readmeExcerpt", "")).lower().strip()

    if len(readme) < 150:
        return False

    useful_markers = [
        "installation",
        "setup",
        "usage",
        "features",
        "api",
        "architecture",
        "overview",
        "technologies",
        "dependencies",
        "how to run",
        "getting started",
        "screenshots",
        "deployment",
        "database",
        "routes",
        "endpoints",
        "description",
        "project",
    ]

    return any(marker in readme for marker in useful_markers)


def has_backend_or_api_signal(repo: dict) -> bool:
    text = " ".join([
        str(repo.get("repoName", "")),
        str(repo.get("languages", "")),
        str(repo.get("readmeExcerpt", "")),
    ]).lower()

    markers = [
        "api",
        "backend",
        "server",
        "express",
        "node",
        "fastapi",
        "flask",
        "django",
        "spring",
        "database",
        "mongodb",
        "mysql",
        "postgres",
        "sqlite",
        "auth",
        "rest",
        "graphql",
    ]

    return any(marker in text for marker in markers)


def has_frontend_signal(repo: dict) -> bool:
    text = " ".join([
        str(repo.get("repoName", "")),
        str(repo.get("languages", "")),
        str(repo.get("readmeExcerpt", "")),
    ]).lower()

    markers = [
        "react",
        "next",
        "vite",
        "frontend",
        "ui",
        "dashboard",
        "html",
        "css",
        "tailwind",
        "typescript",
        "javascript",
        "portfolio",
    ]

    return any(marker in text for marker in markers)


def has_ai_ml_data_signal(repo: dict) -> bool:
    text = " ".join([
        str(repo.get("repoName", "")),
        str(repo.get("languages", "")),
        str(repo.get("readmeExcerpt", "")),
    ]).lower()

    markers = [
        "ai",
        "ml",
        "machine learning",
        "model",
        "prediction",
        "forecast",
        "jupyter",
        "notebook",
        "data",
        "classification",
        "regression",
        "nlp",
        "llm",
        "rag",
    ]

    return any(marker in text for marker in markers)


def is_recently_pushed(repo: dict, months: int = 12) -> bool:
    pushed = str(repo.get("lastPushed", "")).strip()

    if not pushed:
        return False

    try:
        pushed_date = datetime.fromisoformat(pushed[:10])
        now = datetime.utcnow()
        return (now - pushed_date).days <= months * 30
    except Exception:
        return False


def repo_strength_score(repo: dict) -> float:
    commits = safe_number(repo.get("commits"))
    active_weeks = safe_number(repo.get("activeWeeks"))

    score = 0

    if commits >= 50:
        score += 2
    elif commits >= 10:
        score += 1
    elif commits >= 3:
        score += 0.5

    if active_weeks >= 8:
        score += 1.5
    elif active_weeks >= 3:
        score += 1
    elif active_weeks >= 1:
        score += 0.5

    if has_useful_readme(repo):
        score += 1

    if has_backend_or_api_signal(repo) or has_frontend_signal(repo) or has_ai_ml_data_signal(repo):
        score += 1

    if is_recently_pushed(repo):
        score += 0.5

    if is_short_duration(repo):
        score -= 1

    if has_generic_commit(repo):
        score -= 0.5

    return round(max(0, score), 2)


def repo_concern_score(repo: dict) -> float:
    commits = safe_number(repo.get("commits"))
    active_weeks = safe_number(repo.get("activeWeeks"))

    score = 0

    if commits <= 1:
        score += 2
    elif commits <= 3:
        score += 1

    if is_short_duration(repo):
        score += 2

    if has_generic_commit(repo):
        score += 1

    if active_weeks == 0:
        score += 0.5

    if not has_useful_readme(repo):
        score += 0.5

    return round(score, 2)


def repo_signal_label(repo: dict) -> str:
    strength = repo_strength_score(repo)
    concern = repo_concern_score(repo)

    if strength >= 3 and concern <= 1.5:
        return "Strong evidence"
    if concern >= 3:
        return "Concern"
    if strength >= 2:
        return "Moderate evidence"
    return "Weak or limited evidence"


def build_repo_evidence_line(repo: dict) -> str:
    parts = []

    commits = int(safe_number(repo.get("commits")))
    duration = str(repo.get("duration", "")).strip()
    first_message = str(repo.get("firstMessage", "")).strip()
    active_weeks = repo.get("activeWeeks")
    languages = str(repo.get("languages", "")).strip()

    parts.append(f"{commits} commit{'s' if commits != 1 else ''}")

    if duration:
        parts.append(f"duration: {duration}")

    if active_weeks != "" and active_weeks is not None:
        parts.append(f"active weeks: {active_weeks}")

    if languages:
        parts.append(f"languages: {languages}")

    if first_message:
        parts.append(f"first commit: {first_message}")

    if has_useful_readme(repo):
        parts.append("useful README")

    if is_short_duration(repo):
        parts.append("short-duration repo")

    if has_generic_commit(repo):
        parts.append("generic commit messages")

    return "; ".join(parts)


def calculate_score_breakdown(metrics: dict) -> list[dict]:
    total = metrics["reposAnalyzed"] or 1

    useful_project_ratio = metrics["usefulProjectReposCount"] / total
    generic_ratio = metrics["genericCommitReposCount"] / total
    short_ratio = metrics["shortDurationReposCount"] / total
    single_commit_ratio = metrics["singleCommitReposCount"] / total
    useful_readme_ratio = metrics["usefulReadmeReposCount"] / total
    recent_ratio = metrics["recentlyPushedReposCount"] / total
    zero_active_ratio = metrics["zeroActiveWeekReposCount"] / total

    repository_depth = round(clamp(0.4 + useful_project_ratio * 1.6, 0, 2), 1)
    commit_quality = round(clamp(2 - generic_ratio * 1.0 - single_commit_ratio * 0.8, 0, 2), 1)
    development_timeline = round(clamp(2 - short_ratio * 1.5 - zero_active_ratio * 0.5, 0, 2), 1)
    documentation_quality = round(clamp(useful_readme_ratio * 1.5, 0, 1.5), 1)
    tech_relevance = round(clamp(0.3 + useful_project_ratio * 0.7, 0, 1), 1)
    recent_activity = round(clamp(recent_ratio, 0, 1), 1)
    authenticity_signal = round(
        clamp(0.5 - short_ratio * 0.25 - generic_ratio * 0.15 - single_commit_ratio * 0.1, 0, 0.5),
        1,
    )

    return [
        {
            "category": "Repository Depth",
            "score": repository_depth,
            "maxScore": 2,
            "evidence": f"{metrics['usefulProjectReposCount']} of {total} repos show useful project/technical depth signals.",
        },
        {
            "category": "Commit Quality",
            "score": commit_quality,
            "maxScore": 2,
            "evidence": f"{metrics['genericCommitReposCount']} of {total} repos show generic commit-message patterns; {metrics['singleCommitReposCount']} repos have only one commit.",
        },
        {
            "category": "Development Timeline",
            "score": development_timeline,
            "maxScore": 2,
            "evidence": f"{metrics['shortDurationReposCount']} of {total} repos were completed in less than one day; {metrics['zeroActiveWeekReposCount']} repos have zero active weeks.",
        },
        {
            "category": "README / Documentation",
            "score": documentation_quality,
            "maxScore": 1.5,
            "evidence": f"{metrics['usefulReadmeReposCount']} of {total} repos include useful README/documentation signals.",
        },
        {
            "category": "Tech Relevance",
            "score": tech_relevance,
            "maxScore": 1,
            "evidence": f"Detected backend/API repos: {metrics['backendOrApiReposCount']}, frontend repos: {metrics['frontendReposCount']}, AI/ML/data repos: {metrics['aiMlDataReposCount']}.",
        },
        {
            "category": "Recent Activity",
            "score": recent_activity,
            "maxScore": 1,
            "evidence": f"{metrics['recentlyPushedReposCount']} of {total} repos were pushed within the recent activity window.",
        },
        {
            "category": "Authenticity Signal",
            "score": authenticity_signal,
            "maxScore": 0.5,
            "evidence": "Based on short-duration repo ratio, generic commit ratio, and single-commit repo ratio.",
        },
    ]


def verdict_from_rating(rating: float, metrics: dict) -> str:
    if metrics["reposAnalyzed"] == 0:
        return "Insufficient Data"

    if rating >= 8:
        return "Strong Manual Portfolio"

    if rating >= 6.5:
        return "Probably Manual"

    if rating >= 4.5:
        return "Mixed / Needs Review"

    if rating >= 3:
        return "Weak Public Evidence"

    return "Possible Bulk Upload Pattern"


def confidence_from_metrics(metrics: dict) -> str:
    if metrics["reposAnalyzed"] < 3:
        return "low"

    if metrics["reposAnalyzed"] >= 8 and metrics["enrichedReposCount"] >= 6:
        return "medium"

    return "low"


def work_style_from_metrics(metrics: dict, rating: float) -> str:
    if metrics["shortDurationReposCount"] >= 5 or metrics["genericCommitReposCount"] >= 6:
        return "Mixed"

    if rating >= 7:
        return "Manual"

    if rating <= 3:
        return "Bulk Upload"

    return "Mixed"


def analyze_profile_metrics(profile: dict) -> dict:
    repos = profile.get("repos", []) or []
    total = len(repos)

    single_commit_repos = []
    short_duration_repos = []
    generic_commit_repos = []
    zero_active_week_repos = []
    useful_readme_repos = []
    backend_or_api_repos = []
    frontend_repos = []
    ai_ml_data_repos = []
    recently_pushed_repos = []
    useful_project_repos = []
    enriched_repos = []

    repo_evidence = []

    for repo in repos:
        repo_name = repo.get("repoName") or f"Repo {repo.get('repoNum')}"
        commits = safe_number(repo.get("commits"))
        active_weeks = safe_number(repo.get("activeWeeks"))

        if str(repo.get("enrichStatus", "")).lower() == "ok":
            enriched_repos.append(repo_name)

        if commits <= 1:
            single_commit_repos.append(repo_name)

        if is_short_duration(repo):
            short_duration_repos.append(repo_name)

        if has_generic_commit(repo):
            generic_commit_repos.append(repo_name)

        if active_weeks == 0:
            zero_active_week_repos.append(repo_name)

        if has_useful_readme(repo):
            useful_readme_repos.append(repo_name)

        if has_backend_or_api_signal(repo):
            backend_or_api_repos.append(repo_name)

        if has_frontend_signal(repo):
            frontend_repos.append(repo_name)

        if has_ai_ml_data_signal(repo):
            ai_ml_data_repos.append(repo_name)

        if is_recently_pushed(repo):
            recently_pushed_repos.append(repo_name)

        if (
            has_useful_readme(repo)
            or has_backend_or_api_signal(repo)
            or has_frontend_signal(repo)
            or has_ai_ml_data_signal(repo)
            or commits >= 10
            or active_weeks >= 2
        ):
            useful_project_repos.append(repo_name)

        repo_evidence.append({
            "repoName": repo_name,
            "signal": repo_signal_label(repo),
            "strengthScore": repo_strength_score(repo),
            "concernScore": repo_concern_score(repo),
            "evidence": build_repo_evidence_line(repo),
        })

    strongest_repos = sorted(
        repo_evidence,
        key=lambda item: item["strengthScore"],
        reverse=True,
    )[:5]

    concern_repos = sorted(
        repo_evidence,
        key=lambda item: item["concernScore"],
        reverse=True,
    )[:5]

    metrics = {
        "repositoryCount": profile.get("repositoryCount", 0),
        "reposAnalyzed": total,
        "enrichedReposCount": len(enriched_repos),
        "singleCommitReposCount": len(single_commit_repos),
        "singleCommitRepos": single_commit_repos,
        "shortDurationReposCount": len(short_duration_repos),
        "shortDurationRepos": short_duration_repos,
        "genericCommitReposCount": len(generic_commit_repos),
        "genericCommitRepos": generic_commit_repos,
        "zeroActiveWeekReposCount": len(zero_active_week_repos),
        "zeroActiveWeekRepos": zero_active_week_repos,
        "usefulReadmeReposCount": len(useful_readme_repos),
        "usefulReadmeRepos": useful_readme_repos,
        "backendOrApiReposCount": len(backend_or_api_repos),
        "backendOrApiRepos": backend_or_api_repos,
        "frontendReposCount": len(frontend_repos),
        "frontendRepos": frontend_repos,
        "aiMlDataReposCount": len(ai_ml_data_repos),
        "aiMlDataRepos": ai_ml_data_repos,
        "recentlyPushedReposCount": len(recently_pushed_repos),
        "recentlyPushedRepos": recently_pushed_repos,
        "usefulProjectReposCount": len(useful_project_repos),
        "usefulProjectRepos": useful_project_repos,
        "strongestRepos": strongest_repos,
        "concernRepos": concern_repos,
        "repoEvidence": repo_evidence,
    }

    score_breakdown = calculate_score_breakdown(metrics)
    rating = round(sum(item["score"] for item in score_breakdown), 1)

    metrics["computedScoreBreakdown"] = score_breakdown
    metrics["computedGithubPortfolioRating"] = rating
    metrics["computedPortfolioVerdict"] = verdict_from_rating(rating, metrics)
    metrics["computedConfidence"] = confidence_from_metrics(metrics)
    metrics["computedWorkStyleSignal"] = work_style_from_metrics(metrics, rating)

    metrics["suggestedInterviewChecks"] = [
        "Ask the candidate to explain the architecture and implementation choices of one strongest repo.",
        "Ask why some repositories have very short duration or only one commit.",
        "Ask the candidate to walk through one project from first commit to final state.",
    ]

    return metrics


def compute_profile_hints(repos: list[dict]) -> dict:
    short_duration_repos = []
    generic_message_repos = []
    zero_active_week_repos = []

    for repo in repos:
        repo_name = repo.get("repoName") or f"Repo {repo.get('repoNum')}"

        if is_short_duration(repo):
            short_duration_repos.append(repo_name)

        if has_generic_commit(repo):
            generic_message_repos.append(repo_name)

        if repo.get("activeWeeks") == 0:
            zero_active_week_repos.append(repo_name)

    return {
        "shortDurationRepos": short_duration_repos,
        "genericMessageRepos": generic_message_repos,
        "zeroActiveWeekRepos": zero_active_week_repos,
    }


def collect_github_profile(username: str, exclude_repo_name: str | None = None) -> dict:
    try:
        repos = fetch_user_repositories(username)
    except Exception as error:
        return {
            "username": username,
            "githubUrl": f"https://github.com/{username}",
            "repositoryCount": 0,
            "reposAnalyzed": 0,
            "repos": [],
            "hints": {},
            "excludedRepoName": exclude_repo_name,
            "error": str(error),
        }

    if exclude_repo_name:
        repos = [
            repo for repo in repos
            if repo.get("name", "").lower() != exclude_repo_name.lower()
        ]

    selected_repos = repos[:MAX_REPOS]
    enriched_repos = []

    for index, repo in enumerate(selected_repos, start=1):
        try:
            enriched_repos.append(fetch_repo_profile(username, repo, index))
        except Exception as error:
            enriched_repos.append({
                "repoNum": index,
                "repoName": repo.get("name", ""),
                "repoUrl": repo.get("html_url", ""),
                "commits": 0,
                "duration": "",
                "firstMessage": "",
                "recentCommits": "",
                "languages": "",
                "readmeExcerpt": "",
                "lastPushed": (repo.get("pushed_at") or "")[:10],
                "activeWeeks": 0,
                "enrichStatus": f"failed: {error}",
            })

    return {
        "username": username,
        "githubUrl": f"https://github.com/{username}",
        "repositoryCount": len(repos),
        "reposAnalyzed": len(enriched_repos),
        "repos": enriched_repos,
        "hints": compute_profile_hints(enriched_repos),
        "excludedRepoName": exclude_repo_name,
        "error": None,
    }


def parse_json_response(text: str) -> dict:
    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.replace("```json", "", 1).strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```", "", 1).strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    first = cleaned.find("{")
    last = cleaned.rfind("}")

    if first != -1 and last != -1:
        cleaned = cleaned[first:last + 1]

    return json.loads(cleaned)


def build_profile_evaluation_prompt(profile: dict, metrics: dict) -> str:
    return f"""
Create a GitHub Profile Evaluation report.

This GitHub evaluation must look like a technical assessment report, not a generic recruiter paragraph.

Important:
- Use OpenAI only to write the final evidence-based report.
- Use the computed metrics and computed score breakdown as the main source of truth.
- Do not invent GitHub facts.
- Use only the provided profile evidence and computed metrics.
- Use cautious language such as "suggests", "likely", "may indicate".
- Never claim certainty about AI usage.
- Do not reject a candidate only because public GitHub evidence is weak.
- This GitHub rating is separate from the assignment score.

Computed rating:
{metrics.get("computedGithubPortfolioRating")} / 10

Computed verdict:
{metrics.get("computedPortfolioVerdict")}

Computed work style signal:
{metrics.get("computedWorkStyleSignal")}

Computed confidence:
{metrics.get("computedConfidence")}

Required report sections:
1. Overall GitHub Rating
2. Portfolio Verdict
3. Work Style Signal
4. Confidence
5. Reason
6. Strong Points
7. Weak Points
8. Score Breakdown
9. Repo-wise Evidence
10. Suggested Interview Checks
11. Review Recommendation
12. Detailed Summary

Rules:
- githubPortfolioRating must match the computed rating.
- portfolioVerdict must match the computed verdict.
- workStyleSignal must match the computed work style signal.
- confidence must match the computed confidence.
- scoreBreakdown must use the computed score breakdown.
- Strong points must cite exact repo names or exact metrics.
- Weak points must cite exact repo names or exact metrics.
- Repo-wise evidence must include strongest repos and concern repos.
- Suggested interview checks must be specific to the candidate's repos.
- Review recommendation must clearly say GitHub profile is a supporting signal only.

GitHub profile raw evidence:
{json.dumps(profile, indent=2)}

Computed GitHub metrics:
{json.dumps(metrics, indent=2)}

Return JSON only.
""".strip()


def insufficient_profile_result(username: str, reason: str, status: str = "local") -> dict:
    return {
        "username": username,
        "githubPortfolioRating": 0,
        "portfolioVerdict": "Insufficient Data",
        "workStyleSignal": "Unknown",
        "confidence": "low",
        "reason": reason,
        "strongPoints": [],
        "weakPoints": [reason],
        "scoreBreakdown": [],
        "repoWiseEvidence": [],
        "suggestedInterviewChecks": [],
        "reviewRecommendation": "Use GitHub profile as supporting signal only.",
        "detailedSummary": reason,
        "evalStatus": status,
    }


def build_repo_wise_fallback(metrics: dict) -> list[dict]:
    items = []

    for repo in metrics.get("strongestRepos", [])[:3]:
        items.append({
            "repoName": repo.get("repoName", ""),
            "signal": "Stronger repo evidence",
            "evidence": repo.get("evidence", ""),
        })

    for repo in metrics.get("concernRepos", [])[:3]:
        items.append({
            "repoName": repo.get("repoName", ""),
            "signal": "Concern or weak evidence",
            "evidence": repo.get("evidence", ""),
        })

    return items


def evaluate_github_profile(username: str, exclude_repo_name: str | None = None) -> dict:
    profile = collect_github_profile(username, exclude_repo_name=exclude_repo_name)

    if profile.get("error"):
        return {
            "profile": profile,
            "metrics": {},
            "evaluation": insufficient_profile_result(
                username,
                profile["error"],
                "local",
            ),
        }

    if not profile.get("repos"):
        return {
            "profile": profile,
            "metrics": {},
            "evaluation": insufficient_profile_result(
                username,
                "No public non-fork repositories found.",
                "local",
            ),
        }

    metrics = analyze_profile_metrics(profile)

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return {
            "profile": profile,
            "metrics": metrics,
            "evaluation": insufficient_profile_result(
                username,
                "OPENAI_API_KEY missing.",
                "failed",
            ),
        }

    client = OpenAI(api_key=api_key)

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a technical recruiter assistant evaluating GitHub profiles "
                        "for internship candidates. Use cautious language. Use only provided "
                        "evidence. Return a structured technical evaluation."
                    ),
                },
                {
                    "role": "user",
                    "content": build_profile_evaluation_prompt(profile, metrics),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "github_profile_report",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "username": {"type": "string"},
                            "githubPortfolioRating": {"type": "number"},
                            "portfolioVerdict": {
                                "type": "string",
                                "enum": [
                                    "Strong Manual Portfolio",
                                    "Probably Manual",
                                    "Mixed / Needs Review",
                                    "Weak Public Evidence",
                                    "Possible Bulk Upload Pattern",
                                    "Insufficient Data",
                                ],
                            },
                            "workStyleSignal": {
                                "type": "string",
                                "enum": [
                                    "Manual",
                                    "AI-Assisted",
                                    "Bulk Upload",
                                    "Mixed",
                                    "Unknown",
                                ],
                            },
                            "confidence": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                            },
                            "reason": {"type": "string"},
                            "strongPoints": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "weakPoints": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "scoreBreakdown": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "category": {"type": "string"},
                                        "score": {"type": "number"},
                                        "maxScore": {"type": "number"},
                                        "evidence": {"type": "string"},
                                    },
                                    "required": [
                                        "category",
                                        "score",
                                        "maxScore",
                                        "evidence",
                                    ],
                                },
                            },
                            "repoWiseEvidence": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "repoName": {"type": "string"},
                                        "signal": {"type": "string"},
                                        "evidence": {"type": "string"},
                                    },
                                    "required": [
                                        "repoName",
                                        "signal",
                                        "evidence",
                                    ],
                                },
                            },
                            "suggestedInterviewChecks": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "reviewRecommendation": {"type": "string"},
                            "detailedSummary": {"type": "string"},
                        },
                        "required": [
                            "username",
                            "githubPortfolioRating",
                            "portfolioVerdict",
                            "workStyleSignal",
                            "confidence",
                            "reason",
                            "strongPoints",
                            "weakPoints",
                            "scoreBreakdown",
                            "repoWiseEvidence",
                            "suggestedInterviewChecks",
                            "reviewRecommendation",
                            "detailedSummary",
                        ],
                    },
                }
            },
        )

        evaluation = parse_json_response(response.output_text)
        evaluation["evalStatus"] = "ok"

        # Keep score deterministic and controlled by Python evidence.
        evaluation["githubPortfolioRating"] = metrics["computedGithubPortfolioRating"]
        evaluation["portfolioVerdict"] = metrics["computedPortfolioVerdict"]
        evaluation["workStyleSignal"] = metrics["computedWorkStyleSignal"]
        evaluation["confidence"] = metrics["computedConfidence"]
        evaluation["scoreBreakdown"] = metrics["computedScoreBreakdown"]

        if not evaluation.get("repoWiseEvidence"):
            evaluation["repoWiseEvidence"] = build_repo_wise_fallback(metrics)

        if not evaluation.get("suggestedInterviewChecks"):
            evaluation["suggestedInterviewChecks"] = metrics["suggestedInterviewChecks"]

    except Exception as error:
        evaluation = insufficient_profile_result(
            username,
            f"GitHub profile evaluation failed: {error}",
            "failed",
        )

    return {
        "profile": profile,
        "metrics": metrics,
        "evaluation": evaluation,
    }


def print_github_profile_evaluation(result: dict):
    profile = result.get("profile", {})
    metrics = result.get("metrics", {})
    evaluation = result.get("evaluation", {})

    print("")
    print("GitHub Profile Evaluation")
    print("----------------------------")
    print("Username:", evaluation.get("username") or profile.get("username"))
    print("GitHub URL:", profile.get("githubUrl"))
    print("Repositories:", profile.get("repositoryCount"))
    print("Repos analyzed:", profile.get("reposAnalyzed"))
    if profile.get("excludedRepoName"):
        print("Excluded assignment repo:", profile.get("excludedRepoName"))
    print("Overall GitHub Rating:", f"{evaluation.get('githubPortfolioRating')} / 10")
    print("Portfolio Verdict:", evaluation.get("portfolioVerdict"))
    print("Work Style Signal:", evaluation.get("workStyleSignal"))
    print("Confidence:", evaluation.get("confidence"))
    print("Reason:", evaluation.get("reason"))

    print("")
    print("Computed GitHub Evidence Summary")
    print("----------------------------")
    if metrics:
        print("Single-commit repos:", f"{metrics.get('singleCommitReposCount')} / {metrics.get('reposAnalyzed')}")
        print("Less-than-1-day repos:", f"{metrics.get('shortDurationReposCount')} / {metrics.get('reposAnalyzed')}")
        print("Generic commit repos:", f"{metrics.get('genericCommitReposCount')} / {metrics.get('reposAnalyzed')}")
        print("Useful README repos:", f"{metrics.get('usefulReadmeReposCount')} / {metrics.get('reposAnalyzed')}")
        print("Backend/API repos:", f"{metrics.get('backendOrApiReposCount')} / {metrics.get('reposAnalyzed')}")
        print("Frontend repos:", f"{metrics.get('frontendReposCount')} / {metrics.get('reposAnalyzed')}")
        print("AI/ML/Data repos:", f"{metrics.get('aiMlDataReposCount')} / {metrics.get('reposAnalyzed')}")
        print("Recently pushed repos:", f"{metrics.get('recentlyPushedReposCount')} / {metrics.get('reposAnalyzed')}")
    else:
        print("No computed metrics available.")

    print("")
    print("Strong Points")
    print("----------------------------")
    strong_points = evaluation.get("strongPoints") or []
    if strong_points:
        for item in strong_points:
            print("-", item)
    else:
        print("None")

    print("")
    print("Weak Points")
    print("----------------------------")
    weak_points = evaluation.get("weakPoints") or []
    if weak_points:
        for item in weak_points:
            print("-", item)
    else:
        print("None")

    print("")
    print("Score Breakdown")
    print("----------------------------")
    score_breakdown = evaluation.get("scoreBreakdown") or []
    if score_breakdown:
        print("| Criterion | Score | Max | Evidence |")
        print("|---|---:|---:|---|")
        for item in score_breakdown:
            print(
                f"| {item.get('category')} | "
                f"{item.get('score')} | "
                f"{item.get('maxScore')} | "
                f"{item.get('evidence')} |"
            )
    else:
        print("No score breakdown.")

    print("")
    print("Repo-wise Evidence")
    print("----------------------------")
    repo_wise_evidence = evaluation.get("repoWiseEvidence") or []
    if repo_wise_evidence:
        print("| Repo | Signal | Evidence |")
        print("|---|---|---|")
        for item in repo_wise_evidence:
            print(
                f"| {item.get('repoName')} | "
                f"{item.get('signal')} | "
                f"{item.get('evidence')} |"
            )
    else:
        print("No repo-wise evidence.")

    print("")
    print("Suggested Interview Checks")
    print("----------------------------")
    checks = evaluation.get("suggestedInterviewChecks") or []
    if checks:
        for item in checks:
            print("-", item)
    else:
        print("None")

    print("")
    print("Review Recommendation")
    print("----------------------------")
    print(evaluation.get("reviewRecommendation") or "Use GitHub profile as a supporting signal only.")

    print("")
    print("Detailed Summary")
    print("----------------------------")
    print(evaluation.get("detailedSummary") or "")