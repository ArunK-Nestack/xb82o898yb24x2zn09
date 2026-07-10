import os
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_BASE = "https://api.github.com"


def parse_github_repo_url(github_url: str) -> dict:
    parsed = urlparse(github_url)

    if "github.com" not in parsed.netloc:
        raise ValueError("Invalid GitHub URL")

    parts = [part for part in parsed.path.split("/") if part]

    if len(parts) < 2:
        raise ValueError("Could not extract owner/repo from GitHub URL")

    owner = parts[0]
    repo = parts[1].replace(".git", "")

    return {
        "owner": owner,
        "repo": repo,
        "repo_full_name": f"{owner}/{repo}",
        "is_invitation_url": "invitations" in parts,
    }


def github_headers() -> dict:
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN missing in .env")

    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_request(method: str, endpoint: str, **kwargs):
    url = f"{GITHUB_API_BASE}{endpoint}"
    response = requests.request(
        method=method,
        url=url,
        headers=github_headers(),
        timeout=30,
        **kwargs,
    )
    return response


def accept_github_invitation(github_url: str) -> dict:
    parsed_repo = parse_github_repo_url(github_url)

    owner = parsed_repo["owner"]
    repo = parsed_repo["repo"]
    repo_full_name = parsed_repo["repo_full_name"].lower()

    if parsed_repo["is_invitation_url"]:
        print("Invitation URL detected.")

    print("Checking invitation for:", repo_full_name)

    user_response = github_request("GET", "/user")

    if not user_response.ok:
        raise RuntimeError(
            f"GitHub token check failed: {user_response.status_code} {user_response.text}"
        )

    github_user = user_response.json()
    print("Authenticated GitHub user:", github_user.get("login"))

    invitations_response = github_request("GET", "/user/repository_invitations")

    if not invitations_response.ok:
        raise RuntimeError(
            f"Failed to fetch invitations: {invitations_response.status_code} {invitations_response.text}"
        )

    invitations = invitations_response.json()
    print("Pending invitations found:", len(invitations))

    matched_invitation = None

    for invitation in invitations:
        invitation_repo_name = (
            invitation.get("repository", {}).get("full_name", "").lower()
        )

        if invitation_repo_name == repo_full_name:
            matched_invitation = invitation
            break

    if not matched_invitation:
        return {
            "success": False,
            "invitation_found": False,
            "invitation_accepted": False,
            "message": "No pending invitation found for this repository. It may already be accepted.",
            "owner": owner,
            "repo": repo,
            "repo_full_name": parsed_repo["repo_full_name"],
            "authenticated_user": github_user.get("login"),
        }

    print("Invitation found:")
    print("Invitation ID:", matched_invitation.get("id"))
    print("Repository:", matched_invitation.get("repository", {}).get("full_name"))
    print("Permission:", matched_invitation.get("permissions"))
    print("Accepting invitation...")

    accept_response = github_request(
        "PATCH",
        f"/user/repository_invitations/{matched_invitation['id']}",
    )

    if accept_response.status_code == 204:
        return {
            "success": True,
            "invitation_found": True,
            "invitation_accepted": True,
            "message": f"Invitation accepted for {owner}/{repo}",
            "owner": owner,
            "repo": repo,
            "repo_full_name": parsed_repo["repo_full_name"],
            "authenticated_user": github_user.get("login"),
        }

    raise RuntimeError(
        f"Failed to accept invitation: {accept_response.status_code} {accept_response.text}"
    )


def verify_repo_access(owner: str, repo: str) -> dict:
    print("Verifying repo access...")

    response = github_request("GET", f"/repos/{owner}/{repo}")

    if not response.ok:
        raise RuntimeError(
            f"Repo access check failed: {response.status_code} {response.text}"
        )

    print("Repo access verified.")
    return response.json()