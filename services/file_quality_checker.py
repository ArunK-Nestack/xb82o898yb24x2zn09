import json


def looks_like_markdown_or_readme(content: str) -> bool:
    lowered = content.lower()

    markdown_markers = [
        "# ",
        "## ",
        "installation",
        "how to run",
        "setup",
        "design decisions",
        "limitations",
        "deployment",
        "```",
        "pip install",
        "python ingest.py",
        "uvicorn",
        "curl",
    ]

    marker_count = sum(1 for marker in markdown_markers if marker in lowered)

    return marker_count >= 4


def looks_like_python_code(content: str) -> bool:
    python_markers = [
        "import ",
        "from ",
        "def ",
        "class ",
        "if __name__",
        "FastAPI(",
        "Flask(",
        "@app.",
        "argparse",
    ]

    return any(marker in content for marker in python_markers)


def looks_like_json_only(content: str) -> bool:
    stripped = content.strip()

    if not stripped:
        return False

    if not (stripped.startswith("{") or stripped.startswith("[")):
        return False

    try:
        json.loads(stripped)
        return True
    except Exception:
        return False


def check_python_source_files(source_files: dict) -> list[dict]:
    findings = []

    for file_path, content in (source_files or {}).items():
        lower_path = file_path.lower()

        if not lower_path.endswith(".py"):
            continue

        is_python = looks_like_python_code(content)
        is_markdown = looks_like_markdown_or_readme(content)
        is_json_only = looks_like_json_only(content)

        if is_markdown:
            findings.append({
                "severity": "critical",
                "file": file_path,
                "issue": "Python file appears to contain README/markdown-style content instead of runnable Python code.",
            })

        if is_json_only:
            findings.append({
                "severity": "critical",
                "file": file_path,
                "issue": "Python file appears to contain JSON only instead of runnable Python code.",
            })

        if not is_python:
            findings.append({
                "severity": "high",
                "file": file_path,
                "issue": "Python file does not contain clear Python code markers such as import, def, class, FastAPI, Flask, or route decorators.",
            })

    return findings


def check_requirements_file(config_files: dict) -> list[dict]:
    findings = []

    requirements_text = ""

    for file_path, content in (config_files or {}).items():
        if file_path.lower().endswith("requirements.txt"):
            requirements_text = content
            break

    if not requirements_text:
        return findings

    code_markers = [
        "def ",
        "class ",
        "from langchain",
        "import ",
        "@app.",
        "FastAPI(",
        "Flask(",
    ]

    if any(marker in requirements_text for marker in code_markers):
        findings.append({
            "severity": "critical",
            "file": "requirements.txt",
            "issue": "requirements.txt appears to contain application code instead of only dependency names.",
        })

    return findings


def check_results_json(results_json_text: str) -> list[dict]:
    findings = []

    if not results_json_text or not results_json_text.strip():
        findings.append({
            "severity": "critical",
            "file": "results.json",
            "issue": "results.json is missing or empty.",
        })
        return findings

    try:
        parsed = json.loads(results_json_text)
    except Exception:
        findings.append({
            "severity": "critical",
            "file": "results.json",
            "issue": "results.json is not valid JSON.",
        })
        return findings

    if parsed == [] or parsed == {}:
        findings.append({
            "severity": "critical",
            "file": "results.json",
            "issue": "results.json is empty and does not contain required query results.",
        })
        return findings

    parsed_text = json.dumps(parsed).lower()

    dependency_markers = [
        "langchain",
        "chromadb",
        "fastapi",
        "uvicorn",
        "sentence-transformers",
        "pypdf",
        "requirements",
    ]

    result_markers = [
        "query",
        "chunk_text",
        "page_number",
        "score",
    ]

    dependency_count = sum(1 for marker in dependency_markers if marker in parsed_text)
    result_count = sum(1 for marker in result_markers if marker in parsed_text)

    if dependency_count >= 3 and result_count < 2:
        findings.append({
            "severity": "critical",
            "file": "results.json",
            "issue": "results.json appears to contain dependency/package information instead of query output results.",
        })

    if result_count < 3:
        findings.append({
            "severity": "high",
            "file": "results.json",
            "issue": "results.json does not clearly contain required query result fields such as query, chunk_text, page_number, and score.",
        })

    return findings


def check_file_quality(repo_evidence: dict, assessment_type: str | None = None) -> dict:
    findings = []

    findings.extend(check_python_source_files(repo_evidence.get("sourceFiles", {})))
    findings.extend(check_requirements_file(repo_evidence.get("configFiles", {})))

    assessments_that_require_results_json = {
        "standard-vectorization",
        "langchain-vectorization",
        "data-extractor",
    }

    if assessment_type in assessments_that_require_results_json:
        findings.extend(check_results_json(repo_evidence.get("resultsJsonText", "")))

    critical_findings = [f for f in findings if f.get("severity") == "critical"]
    high_findings = [f for f in findings if f.get("severity") == "high"]

    return {
        "hasCriticalFileQualityIssue": len(critical_findings) > 0,
        "criticalCount": len(critical_findings),
        "highCount": len(high_findings),
        "findings": findings,
    }