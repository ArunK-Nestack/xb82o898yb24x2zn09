# Runnable checks for the dep-free pipeline helpers: `python test_parse_score.py`
# Guards (1) the "Overall Score: <N> / 100" contract the app callback depends on, and
# (2) that the GitHub token never survives into result.json (it would land in the DB).
import os
from score_parse import parse_overall_score, redact_secrets

assert parse_overall_score("Overall Score: 87 / 100\nBase Rubric Score: 85 / 100") == 87
assert parse_overall_score("Overall Score:0 / 100") == 0
assert parse_overall_score("Overall Score: 72.6 / 100") == 73   # rounded
assert parse_overall_score("no score here") is None
assert parse_overall_score("") is None

os.environ["GITHUB_TOKEN"] = "ghp_SECRET123"
leak = "fatal: clone https://x-access-token:ghp_SECRET123@github.com/o/r.git failed"
red = redact_secrets(leak)
assert "ghp_SECRET123" not in red, red          # token value scrubbed
assert "x-access-token:***@" in red, red        # url-form scrubbed even if token var differs
assert redact_secrets(None) is None             # non-str passthrough

print("score_parse helpers: all checks passed")
