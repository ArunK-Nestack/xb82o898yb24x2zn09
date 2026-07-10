import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def trim_large_text(text: str = "", max_chars: int = 18000) -> str:
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n\n[TRUNCATED]"


def trim_file_map(file_map: dict | None, max_chars_per_file: int = 10000) -> dict:
    trimmed = {}

    for file_path, content in (file_map or {}).items():
        trimmed[file_path] = trim_large_text(content, max_chars_per_file)

    return trimmed


def extract_json_from_text(text: str) -> dict:
    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.replace("```json", "", 1).strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```", "", 1).strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")

    if first_brace != -1 and last_brace != -1:
        cleaned = cleaned[first_brace:last_brace + 1]

    return json.loads(cleaned)


def build_weak_signal_payload(
    repo_evidence: dict,
    assessment_type: str,
    deployment_results: list[dict],
    assignment_pdf: dict | None = None,
) -> dict:
    return {
        "assessmentType": assessment_type,

        "assignmentPdfEvidence": {
            "found": assignment_pdf.get("found") if assignment_pdf else False,
            "fileName": assignment_pdf.get("fileName") if assignment_pdf else None,
            "pageCount": assignment_pdf.get("pageCount") if assignment_pdf else 0,
            "message": assignment_pdf.get("message") if assignment_pdf else "No assignment PDF provided.",
            "combinedText": trim_large_text(
                assignment_pdf.get("combinedText", "") if assignment_pdf else "",
                20000,
            ),
        },

        "repo": {
            "repoFullName": repo_evidence.get("repoFullName"),
            "repoPrivate": repo_evidence.get("repoPrivate"),
            "repoDefaultBranch": repo_evidence.get("repoDefaultBranch"),
            "repoUrl": repo_evidence.get("repoUrl"),
        },

        "submissionStatus": repo_evidence.get("submissionStatus"),
        "fileQuality": repo_evidence.get("fileQuality"),

        "files": {
            "includedFiles": repo_evidence.get("fileList"),
            "fileStats": repo_evidence.get("fileStats"),
        },

        "urls": {
            "deploymentUrls": repo_evidence.get("deploymentUrls"),
            "readmeUrls": repo_evidence.get("readmeUrls"),
            "deploymentResults": deployment_results,
        },

        "readmeText": trim_large_text(repo_evidence.get("readmeText")),
        "packageJsonText": trim_large_text(repo_evidence.get("packageJsonText")),
        "resultsJsonText": trim_large_text(repo_evidence.get("resultsJsonText")),
        "sourceFiles": trim_file_map(repo_evidence.get("sourceFiles")),
        "testFiles": trim_file_map(repo_evidence.get("testFiles")),
        "configFiles": trim_file_map(repo_evidence.get("configFiles")),
    }


def run_openai_pre_evaluation(
    repo_evidence: dict,
    assessment_type: str,
    deployment_results: list[dict],
    assignment_pdf: dict | None = None,
) -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY missing in .env")

    payload = build_weak_signal_payload(
        repo_evidence,
        assessment_type,
        deployment_results,
        assignment_pdf,
    )

    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.5"),
        input=[
            {
                "role": "system",
                "content": """
You are a strict repository weak-signal detector.

Your job is NOT to score the candidate.
Your job is NOT to award points.
Your job is NOT to find positive signals.

Your only job is to detect weak signals, risk signals, mismatch signals, missing evidence, and suspicious inconsistencies that the final evaluator must consider.

Use the original assignment PDF, cloned repository evidence, deployment result, README, file list, source files, config files, test files, and results.json evidence.

Important rules:
- Do not provide any score.
- Do not provide any grade.
- Do not provide category scores.
- Do not provide positive signals.
- Do not praise implementation.
- Do not say something is good unless it is necessary to explain a mismatch.
- Only report weaknesses, risks, missing evidence, inconsistencies, and suspicious issues.
- Do not invent issues. Use only provided evidence.
- If a problem is already directly visible in fileQuality, include it as a weak signal.
- If deployment URL is missing, report it as a weak signal, not a rejection.
- If deployment URL failed, report it as a weak signal.
- Report results.json missing, empty, malformed, copied, irrelevant, or inconsistent only if the selected assignment type or assignment PDF requires results.json.- If README contains placeholders, TODOs, fake URLs, missing-file references, or unsupported claims, report it.
- If code appears in the wrong file, report it.
- If source files are README-style, JSON-only, empty, or not runnable, report it.
- If repository appears to solve a different assignment than the assignment PDF, report it.
- If candidate claims LangGraph, tests, Docker, deployment, or features that are not present in files, report it.
- If tests are missing, report it.
- If dependencies are unpinned, irrelevant, missing, or inconsistent with assignment, report it.
- If security/professionalism concerns exist, report them.
                """.strip(),
            },
            {
                "role": "user",
                "content": f"""
WEAK-SIGNAL DETECTION EVIDENCE:
{json.dumps(payload, indent=2)}

Return JSON only. No markdown. No text outside JSON.

Use this exact schema:

{{
  "assignmentAlignment": {{
    "matchesAssignmentPdf": true,
    "detectedIssue": "",
    "evidence": ""
  }},
  "weakSignals": [
    {{
      "severity": "critical | high | medium | low",
      "area": "assignment_alignment | deployment | readme | source_code | results_json | tests | dependencies | security | professionalism | file_quality",
      "signal": "",
      "evidence": "",
      "finalEvaluatorInstruction": ""
    }}
  ],
  "mustConsiderInFinalEvaluation": [
    ""
  ],
  "manualReviewNeeded": true
}}

Rules:
- weakSignals must contain only negative signals.
- mustConsiderInFinalEvaluation must be a concise list of issues the final evaluator should not miss.
- Do not include score.
- Do not include grade.
- Do not include positiveSignals.
- Do not include categoryScores.
                """.strip(),
            },
        ],
    )

    try:
        parsed_result = extract_json_from_text(response.output_text)

        if "weakSignals" not in parsed_result:
            parsed_result["weakSignals"] = []

        if "mustConsiderInFinalEvaluation" not in parsed_result:
            parsed_result["mustConsiderInFinalEvaluation"] = []

        if "manualReviewNeeded" not in parsed_result:
            parsed_result["manualReviewNeeded"] = True

        return parsed_result

    except Exception:
        return {
            "assignmentAlignment": {
                "matchesAssignmentPdf": False,
                "detectedIssue": "OpenAI returned non-JSON output.",
                "evidence": response.output_text,
            },
            "weakSignals": [
                {
                    "severity": "critical",
                    "area": "system",
                    "signal": "Weak signal scan failed because OpenAI returned non-JSON output.",
                    "evidence": response.output_text,
                    "finalEvaluatorInstruction": "Do not rely on weak signal scan. Evaluate strictly from repository evidence.",
                }
            ],
            "mustConsiderInFinalEvaluation": [
                "Weak signal scan failed and requires manual review."
            ],
            "manualReviewNeeded": True,
        }