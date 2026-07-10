"""Pure, dependency-free pipeline helpers (score parsing + secret redaction).
Kept free of the heavy deps in services/ so they stay unit-testable without installs."""
import os
import re


def parse_overall_score(report: str) -> int | None:
    """Pull the 0-100 score from the report header 'Overall Score: <N> / 100'.
    Returns None if absent (report is still stored; a human reviews)."""
    match = re.search(r"Overall Score:\s*([\d.]+)", report or "")
    return round(float(match.group(1))) if match else None


def redact_secrets(text):
    """Strip the GitHub token before any string leaves the runner. The clone URL
    embeds the PAT, so a git failure would otherwise carry it into result.json ->
    the callback -> EvaluationJob.error in the app database."""
    if not isinstance(text, str):
        return text
    token = os.getenv("GITHUB_TOKEN")
    if token:
        text = text.replace(token, "***")
    return re.sub(r"x-access-token:[^@\s]+@", "x-access-token:***@", text)
