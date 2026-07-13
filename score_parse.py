"""Pure, dependency-free pipeline helpers (score parsing + secret redaction).
Kept free of the heavy deps in services/ so they stay unit-testable without installs."""
import os
import re


def _clamp_score(raw: str) -> int | None:
    """Round a numeric score string and clamp to [0, 100]. None if invalid or out of range —
    an out-of-range number is a manipulated/garbage score, so it is withheld for human review."""
    try:
        value = round(float(raw))
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 100 else None


def parse_overall_score(report: str, nonce: str | None = None) -> int | None:
    """Pull the 0-100 hire score from the evaluator report.

    When `nonce` is given (a per-run, unguessable token), ONLY the anchored line
    'FINAL_SCORE[<nonce>]: <N>' is trusted. A candidate cannot forge the nonce, so any
    'Overall Score: 100' they plant in their own repo can no longer hijack the gate.
    Without a nonce, falls back to the legacy 'Overall Score: <N>' header (still clamped).
    Returns None if absent/invalid (report is still stored; a human reviews)."""
    report = report or ""
    if nonce:
        match = re.search(r"FINAL_SCORE\[" + re.escape(nonce) + r"\]:\s*([\d.]+)", report)
    else:
        match = re.search(r"Overall Score:\s*([\d.]+)", report)
    return _clamp_score(match.group(1)) if match else None


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
