import sys
import json
from pathlib import Path

from score_parse import parse_overall_score, redact_secrets
from services.github_client import (
    parse_github_repo_url,
    accept_github_invitation,
)
from services.repo_collector import collect_repo_evidence
from services.assessment_detector import (
    detect_assessment_type,
    detect_assessment_type_with_evidence,
)
from services.deployment_checker import check_deployment_urls
from services.cleanup import cleanup_temp_repos
from services.openai_pre_evaluator import run_openai_pre_evaluation
from services.final_assessment_evaluator import run_final_assessment_evaluation
from services.assignment_pdf_loader import load_assignment_pdf
from services.file_quality_checker import check_file_quality


def print_pipeline_summary(repo_evidence: dict, assessment_type: str):
    submission_status = repo_evidence.get("submissionStatus", {})

    print("")
    print("Pipeline Summary")
    print("----------------------------")
    print("Repo:", repo_evidence.get("repoFullName"))
    print("Private:", repo_evidence.get("repoPrivate"))
    print("Default Branch:", repo_evidence.get("repoDefaultBranch"))
    print("Submission Status:", submission_status.get("status"))
    print("Files scanned:", repo_evidence["fileStats"]["totalIncludedFiles"])
    print("Source files:", repo_evidence["fileStats"]["sourceFileCount"])
    print("Test files:", repo_evidence["fileStats"]["testFileCount"])
    print("Config files:", repo_evidence["fileStats"]["configFileCount"])
    print("README found:", repo_evidence["fileStats"]["hasReadme"])
    print("package.json found:", repo_evidence["fileStats"]["hasPackageJson"])
    print("results.json found:", repo_evidence["fileStats"]["hasResultsJson"])
    print("Deployment URLs:", repo_evidence.get("deploymentUrls"))
    print("Assessment Type:", assessment_type)

    if assessment_type == "unknown":
        print("Prompt Selected: none")
        print("Reason: Could not detect assessment type from scanned files.")
    else:
        print("Prompt Selected:", f"prompts/{assessment_type}.txt")

    print("")
    print("Included Files:")
    print(repo_evidence.get("fileList"))

    if submission_status.get("isRejected"):
        print("")
        print("Rejection Reasons")
        print("----------------------------")

        for reason in submission_status.get("rejectionReasons", []):
            print("-", reason)

        print("")
        print("Forbidden Items Found")
        print("----------------------------")

        for item in submission_status.get("forbiddenItems", []):
            print("-", item.get("path"), "|", item.get("reason"))

def print_assignment_pdf_summary(assignment_pdf: dict):
    print("")
    print("Assignment PDF Check")
    print("----------------------------")
    print("Assignment PDF found:", assignment_pdf.get("found"))
    print("PDF file:", assignment_pdf.get("fileName"))
    print("PDF pages:", assignment_pdf.get("pageCount"))
    print("Message:", assignment_pdf.get("message"))

def print_file_quality_summary(repo_evidence: dict):
    file_quality = repo_evidence.get("fileQuality", {})

    print("")
    print("File Quality Check")
    print("----------------------------")
    print("Critical issues:", file_quality.get("criticalCount", 0))
    print("High issues:", file_quality.get("highCount", 0))

    for finding in file_quality.get("findings", []):
        print(
            f"- {finding.get('severity').upper()} | "
            f"{finding.get('file')} | "
            f"{finding.get('issue')}"
        )

def print_deployment_results(repo_evidence: dict) -> list[dict]:
    deployment_urls = repo_evidence.get("deploymentUrls", [])

    print("")
    print("Checking deployment URLs...")
    print("----------------------------")

    if not deployment_urls:
        print("No deployment URLs found. Continuing evaluation without deployment.")

        return [
            {
                "url": None,
                "normalizedUrl": None,
                "ok": False,
                "reachable": False,
                "status": None,
                "statusText": "No deployment URL provided by candidate.",
                "testedUrl": None,
                "finalUrl": None,
                "missingDeploymentUrl": True,
                "attempts": [],
            }
        ]

    deployment_results = check_deployment_urls(deployment_urls)

    for result in deployment_results:
        if result.get("ok"):
            print(
                "OK",
                result.get("url"),
                result.get("status"),
                "tested:",
                result.get("testedUrl"),
            )
        elif result.get("reachable"):
            print(
                "REACHABLE BUT NOT OK",
                result.get("url"),
                result.get("status"),
                "tested:",
                result.get("testedUrl"),
            )
            print("Reason:", result.get("statusText"))
        else:
            print(
                "FAILED",
                result.get("url"),
                result.get("status") or "",
            )
            print("Reason:", result.get("statusText"))

    return deployment_results
def print_pre_evaluation_result(weak_signal_scan: dict):
    print("")
    print("OpenAI Weak Signal Scan")
    print("----------------------------")

    alignment = weak_signal_scan.get("assignmentAlignment", {})
    print("Matches assignment PDF:", alignment.get("matchesAssignmentPdf"))
    print("Assignment issue:", alignment.get("detectedIssue"))
    print("Evidence:", alignment.get("evidence"))
    print("Manual review needed:", "yes" if weak_signal_scan.get("manualReviewNeeded") else "no")

    print("")
    print("Weak Signals")
    print("----------------------------")

    weak_signals = weak_signal_scan.get("weakSignals", [])

    if not weak_signals:
        print("No weak signals detected.")
    else:
        for signal in weak_signals:
            print(
                f"- {signal.get('severity', '').upper()} | "
                f"{signal.get('area')} | "
                f"{signal.get('signal')}"
            )
            print(f"  Evidence: {signal.get('evidence')}")
            print(f"  Final evaluator instruction: {signal.get('finalEvaluatorInstruction')}")

    print("")
    print("Must Consider In Final Evaluation")
    print("----------------------------")

    for item in weak_signal_scan.get("mustConsiderInFinalEvaluation", []):
        print(f"- {item}")


        
def print_final_assessment_report(final_report: str):
    print("")
    print("Final Assessment Evaluation")
    print("----------------------------")
    print(final_report)

def print_assessment_detection_debug(repo_evidence: dict):
    result = detect_assessment_type_with_evidence(repo_evidence)

    print("")
    print("Assessment Detection Debug")
    print("----------------------------")
    print("Detected:", result.get("assessmentType"))
    print("Confidence:", result.get("confidence"))
    print("Score:", result.get("score"))
    print("Second best:", result.get("secondBest"))
    print("Second score:", result.get("secondScore"))
    print("Reason:", result.get("reason"))

    print("")
    print("Assessment Scores")
    print("----------------------------")

    scores = result.get("scores", {})

    for assessment_type, data in sorted(
        scores.items(),
        key=lambda item: item[1].get("score", 0),
        reverse=True,
    ):
        print(f"{assessment_type}: {data.get('score')}")

        for evidence in data.get("evidence", [])[:3]:
            print(f"  - {evidence}")

def _write_result(result: dict) -> None:
    """Write the machine-readable result the CI workflow POSTs back to the app."""
    safe = {
        **result,
        "error": redact_secrets(result.get("error")),
        "report": redact_secrets(result.get("report")),
    }
    try:
        Path("result.json").write_text(json.dumps(safe), encoding="utf-8")
    except Exception as error:
        print("Failed to write result.json:", str(error))


def main():
    repo_evidence = None
    # Default to error; each terminal branch overwrites this. Written in `finally`.
    result = {"status": "error", "score": None, "rejected": False, "report": None, "error": None}

    if len(sys.argv) < 2:
        print("Please provide GitHub repo URL.")
        print("Example:")
        print("python main.py https://github.com/org/repo/invitations")
        result["error"] = "No GitHub repo URL provided."
        _write_result(result)
        sys.exit(1)

    github_url = sys.argv[1]

    try:
        print("Starting GitHub evaluation pipeline...")

        parsed_repo = parse_github_repo_url(github_url)

        print("Repo detected:", parsed_repo["repo_full_name"])

        invitation_result = accept_github_invitation(github_url)

        print("")
        print("Invitation step result:")
        print(invitation_result["message"])

        print("")
        print("Continuing to repo access check...")

        repo_evidence = collect_repo_evidence(
            parsed_repo["owner"],
            parsed_repo["repo"],
        )

        print_assessment_detection_debug(repo_evidence)
        assessment_type = detect_assessment_type(repo_evidence)
        file_quality = check_file_quality(repo_evidence, assessment_type)
        repo_evidence["fileQuality"] = file_quality
        assignment_pdf = load_assignment_pdf(assessment_type)

        print_pipeline_summary(repo_evidence, assessment_type)
        print_assignment_pdf_summary(assignment_pdf)
        submission_status = repo_evidence.get("submissionStatus", {})

        if submission_status.get("isRejected"):
            print("")
            print("Pipeline stopped because submission is rejected.")
            reasons = submission_status.get("rejectionReasons", [])
            result.update(
                status="ok",
                rejected=True,
                score=0,
                report="Submission rejected before evaluation.\n"
                + "\n".join(f"- {reason}" for reason in reasons),
            )
            return

        # A missing deployment URL is not a stop condition: print_deployment_results
        # returns a placeholder result and the rubric scores deployment as 0, so we
        # continue evaluating the repo. (See deployment calibration rules.)
        deployment_results = print_deployment_results(repo_evidence)

        print("")
        print("Running OpenAI Pre-Evaluation...")
        print("----------------------------")

        weak_signal_scan = run_openai_pre_evaluation(
            repo_evidence,
            assessment_type,
            deployment_results,
            assignment_pdf,
        )

        print_pre_evaluation_result(weak_signal_scan)

        final_report = run_final_assessment_evaluation(
            repo_evidence,
            assessment_type,
            deployment_results,
            weak_signal_scan,
            assignment_pdf,
        )
        print_final_assessment_report(final_report)

        # The final report header is "Overall Score: <N> / 100" (see final_assessment_evaluator).
        result.update(
            status="ok",
            rejected=False,
            score=parse_overall_score(final_report),
            report=final_report,
        )
    except Exception as error:
        print("")
        print("Pipeline failed:")
        print(str(error))
        result["status"] = "error"
        result["error"] = str(error)

    finally:
        local_repo_dir = None

        if repo_evidence:
            local_repo_dir = repo_evidence.get("localRepoDir")

        cleanup_temp_repos(local_repo_dir)
        _write_result(result)

    if result["status"] != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()