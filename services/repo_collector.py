import os
import re
import shutil
import subprocess
from pathlib import Path
from dotenv import load_dotenv


from services.github_client import verify_repo_access
from services.submission_status_checker import check_submission_status

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

TEMP_REPO_DIR = Path.cwd() / "temp-repos-py"

EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    "coverage",
    ".turbo",
    ".cache",
    "__pycache__",
    ".venv",
    "venv",
}

EXCLUDED_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
}

ALLOWED_EXTENSIONS = {
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".py",
    ".java",
    ".cs",
    ".go",
    ".php",
    ".rb",
    ".json",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".html",
    ".css",
    ".scss",
    ".sql",
}

IMPORTANT_FILES = {
    "README.md",
    "readme.md",
    "package.json",
    "package-lock.json",
    "requirements.txt",
    "pyproject.toml",
    "results.json",
    "run_tests.js",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Procfile",
}

MAX_FILE_SIZE_BYTES = 200 * 1024


def clone_repository(owner: str, repo: str) -> Path:
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN missing in .env")

    TEMP_REPO_DIR.mkdir(exist_ok=True)

    safe_folder_name = re.sub(r"[^a-zA-Z0-9-_]", "-", f"{owner}-{repo}")
    repo_dir = TEMP_REPO_DIR / safe_folder_name

    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    clone_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{owner}/{repo}.git"

    print("Cloning repository...")

    subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(repo_dir)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    print("Repo cloned successfully.")
    return repo_dir


def should_exclude(path: Path, root_dir: Path) -> bool:
    relative_parts = path.relative_to(root_dir).parts

    if any(part in EXCLUDED_DIRS for part in relative_parts):
        return True

    if path.name in EXCLUDED_FILES:
        return True

    return False


def is_allowed_file(path: Path) -> bool:
    if path.name in IMPORTANT_FILES:
        return True

    return path.suffix in ALLOWED_EXTENSIONS


def walk_files(root_dir: Path) -> list[dict]:
    files = []

    for path in root_dir.rglob("*"):
        if should_exclude(path, root_dir):
            continue

        if not path.is_file():
            continue

        if not is_allowed_file(path):
            continue

        size = path.stat().st_size

        if size > MAX_FILE_SIZE_BYTES:
            continue

        files.append(
            {
                "relative_path": str(path.relative_to(root_dir)),
                "full_path": path,
                "size_bytes": size,
            }
        )

    return files


def read_text_file(file_info: dict) -> dict | None:
    try:
        content = Path(file_info["full_path"]).read_text(encoding="utf-8")
        return {
            "path": file_info["relative_path"],
            "size_bytes": file_info["size_bytes"],
            "content": content,
        }
    except UnicodeDecodeError:
        return None


def clean_url(url: str) -> str:
    return re.sub(r'[.,;:)"\'`\]}]+$', "", url.strip())


def is_placeholder_url(url: str) -> bool:
    lower = url.lower()

    return any(
        token in lower
        for token in [
            "todo",
            "replace",
            "your_url",
            "your-url",
            "yourname",
            "example.com",
        ]
    )


def extract_readme_urls(readme_text: str = "") -> dict:
    raw_urls = re.findall(r"https?://[^\s\)\]\"'`,]+", readme_text)
    urls = list(dict.fromkeys(clean_url(url) for url in raw_urls))

    deployment_hosts = [
        "vercel.app",
        "netlify.app",
        "render.com",
        "railway.app",
        "fly.dev",
        "github.io",
        "firebaseapp.com",
        "web.app",
        "herokuapp.com",
    ]

    example_hosts = [
        "webhook.site",
        "httpstat.us",
        "your-endpoint.com",
        "example.com",
    ]

    external_hosts = [
        "github.com",
        "docs.github.com",
        "nodejs.org",
        "npmjs.com",
        "deb.nodesource.com",
    ]

    deployment_urls = []
    localhost_urls = []
    example_urls = []
    external_reference_urls = []
    placeholder_urls = []

    for url in urls:
        lower = url.lower()

        if is_placeholder_url(url):
            placeholder_urls.append(url)
            continue

        if "localhost" in lower or "127.0.0.1" in lower or "0.0.0.0" in lower:
            localhost_urls.append(url)
            continue

        if any(host in lower for host in example_hosts):
            example_urls.append(url)
            continue

        if any(host in lower for host in external_hosts):
            external_reference_urls.append(url)
            continue

        if any(host in lower for host in deployment_hosts):
            deployment_urls.append(url)
            continue

        deployment_urls.append(url)

    return {
        "deploymentUrls": deployment_urls,
        "localhostUrls": localhost_urls,
        "exampleUrls": example_urls,
        "externalReferenceUrls": external_reference_urls,
        "placeholderUrls": placeholder_urls,
        "allUrls": urls,
    }


def categorize_files(read_files: list[dict]) -> dict:
    readme_text = ""
    package_json_text = ""
    results_json_text = ""

    source_files = {}
    test_files = {}
    config_files = {}

    for file in read_files:
        file_path = file["path"]
        file_name = Path(file_path).name.lower()
        content = file["content"]

        if file_name == "readme.md":
            readme_text = content
            continue

        if file_name == "package.json":
            package_json_text = content
            continue

        if file_name == "results.json":
            results_json_text = content
            continue

        is_test = (
            "test" in file_name
            or "spec" in file_name
            or file_name == "run_tests.js"
        )

        if is_test:
            test_files[file_path] = content
            continue

        is_config = (
            file_name in {".env.example", ".gitignore"}
            or "config" in file_name
            or file_name.endswith(".yml")
            or file_name.endswith(".yaml")
            or file_name in {"requirements.txt", "pyproject.toml"}
        )

        if is_config:
            config_files[file_path] = content
            continue

        source_files[file_path] = content

    return {
        "readmeText": readme_text,
        "packageJsonText": package_json_text,
        "resultsJsonText": results_json_text,
        "sourceFiles": source_files,
        "testFiles": test_files,
        "configFiles": config_files,
    }


def collect_repo_evidence(owner: str, repo: str) -> dict:
    repo_meta = verify_repo_access(owner, repo)
    repo_dir = clone_repository(owner, repo)

    submission_status = check_submission_status(repo_dir)

    print("Scanning files...")

    files = walk_files(repo_dir)
    read_files = []

    for file in files:
        result = read_text_file(file)

        if result:
            read_files.append(result)

    categorized = categorize_files(read_files)
    readme_urls = extract_readme_urls(categorized["readmeText"])

    return {
        "repoFullName": f"{owner}/{repo}",
        "repoDefaultBranch": repo_meta.get("default_branch"),
        "repoPrivate": repo_meta.get("private"),
        "repoUrl": repo_meta.get("html_url"),
        "localRepoDir": str(repo_dir),

        "submissionStatus": submission_status,

        "fileList": [file["path"] for file in read_files],
        "readmeText": categorized["readmeText"],
        "packageJsonText": categorized["packageJsonText"],
        "resultsJsonText": categorized["resultsJsonText"],
        "sourceFiles": categorized["sourceFiles"],
        "testFiles": categorized["testFiles"],
        "configFiles": categorized["configFiles"],
        "readmeUrls": readme_urls,
        "deploymentUrls": readme_urls["deploymentUrls"],
        "fileStats": {
            "totalIncludedFiles": len(read_files),
            "sourceFileCount": len(categorized["sourceFiles"]),
            "testFileCount": len(categorized["testFiles"]),
            "configFileCount": len(categorized["configFiles"]),
            "hasReadme": bool(categorized["readmeText"]),
            "hasPackageJson": bool(categorized["packageJsonText"]),
            "hasResultsJson": bool(categorized["resultsJsonText"]),
        },
    }