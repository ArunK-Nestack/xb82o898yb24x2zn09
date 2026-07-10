import time
from urllib.parse import urlparse, urlunparse

import requests


REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,*/*",
}


def normalize_url(url: str) -> str:
    cleaned_url = url.strip()

    if not cleaned_url:
        return ""

    if not cleaned_url.startswith(("http://", "https://")):
        cleaned_url = "https://" + cleaned_url

    parsed_url = urlparse(cleaned_url)

    # Domain is case-insensitive, so normalize it.
    netloc = parsed_url.netloc.lower()

    return urlunparse((
        parsed_url.scheme,
        netloc,
        parsed_url.path.rstrip("/"),
        "",
        parsed_url.query,
        "",
    ))


def build_candidate_urls(base_url: str) -> list[str]:
    parsed_url = urlparse(base_url)

    root_url = urlunparse((
        parsed_url.scheme,
        parsed_url.netloc,
        "",
        "",
        "",
        "",
    )).rstrip("/")

    candidates = [
        base_url,
        root_url,
        f"{root_url}/health",
        f"{root_url}/docs",
        f"{root_url}/openapi.json",
    ]

    unique_candidates = []

    for candidate in candidates:
        if candidate and candidate not in unique_candidates:
            unique_candidates.append(candidate)

    return unique_candidates


def is_success_status(status_code: int | None) -> bool:
    if status_code is None:
        return False

    # 2xx and 3xx mean the deployment is clearly usable/reachable.
    return 200 <= status_code < 400


def is_reachable_status(status_code: int | None) -> bool:
    if status_code is None:
        return False

    # 401/403/404 still prove the server is online.
    # 5xx means app/server failure.
    return 200 <= status_code < 500


def check_single_url(url: str, timeout_seconds: int = 45) -> dict:
    try:
        response = requests.get(
            url,
            timeout=timeout_seconds,
            allow_redirects=True,
            headers=REQUEST_HEADERS,
        )

        return {
            "url": url,
            "ok": is_success_status(response.status_code),
            "reachable": is_reachable_status(response.status_code),
            "status": response.status_code,
            "statusText": response.reason,
            "finalUrl": response.url,
            "error": None,
        }

    except requests.RequestException as error:
        return {
            "url": url,
            "ok": False,
            "reachable": False,
            "status": None,
            "statusText": str(error),
            "finalUrl": None,
            "error": str(error),
        }


def check_deployment_url(url: str) -> dict:
    normalized_url = normalize_url(url)

    if not normalized_url:
        return {
            "url": url,
            "normalizedUrl": normalized_url,
            "ok": False,
            "reachable": False,
            "status": None,
            "statusText": "Empty deployment URL",
            "testedUrl": None,
            "finalUrl": None,
            "attempts": [],
        }

    candidate_urls = build_candidate_urls(normalized_url)
    attempts = []

    # Retry because Render/Railway/Fly free deployments may need warm-up time.
    for retry_number in range(1, 4):
        for candidate_url in candidate_urls:
            result = check_single_url(candidate_url)
            result["retryNumber"] = retry_number
            attempts.append(result)

            # Best case: 2xx/3xx.
            if result["ok"]:
                return {
                    "url": url,
                    "normalizedUrl": normalized_url,
                    "ok": True,
                    "reachable": True,
                    "status": result["status"],
                    "statusText": result["statusText"],
                    "testedUrl": candidate_url,
                    "finalUrl": result["finalUrl"],
                    "attempts": attempts,
                }

        # Wait before next retry for cold-start deployments.
        if retry_number < 3:
            time.sleep(8)

    # Fallback: if any response is 401/403/404, server is online but not usable from root.
    reachable_attempts = [
        attempt for attempt in attempts
        if attempt.get("reachable")
    ]

    if reachable_attempts:
        best_attempt = reachable_attempts[0]

        return {
            "url": url,
            "normalizedUrl": normalized_url,
            "ok": False,
            "reachable": True,
            "status": best_attempt.get("status"),
            "statusText": (
                "Deployment is reachable, but no checked endpoint returned 2xx/3xx"
            ),
            "testedUrl": best_attempt.get("url"),
            "finalUrl": best_attempt.get("finalUrl"),
            "attempts": attempts,
        }

    last_attempt = attempts[-1] if attempts else {}

    return {
        "url": url,
        "normalizedUrl": normalized_url,
        "ok": False,
        "reachable": False,
        "status": last_attempt.get("status"),
        "statusText": last_attempt.get("statusText", "Deployment check failed"),
        "testedUrl": last_attempt.get("url"),
        "finalUrl": last_attempt.get("finalUrl"),
        "attempts": attempts,
    }


def check_deployment_urls(urls: list[str]) -> list[dict]:
    results = []

    for url in urls:
        results.append(check_deployment_url(url))

    return results