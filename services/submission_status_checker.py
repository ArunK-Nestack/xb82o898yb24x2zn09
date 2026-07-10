import os
from pathlib import Path


ALLOWED_ENV_FILES = {
    ".env.example",
}


FORBIDDEN_ENV_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
}


def is_forbidden_env_file(file_name: str) -> bool:
    lower_name = file_name.lower()

    if lower_name in ALLOWED_ENV_FILES:
        return False

    if lower_name in FORBIDDEN_ENV_FILES:
        return True

    if lower_name.startswith(".env."):
        return True

    return False


def check_submission_status(repo_dir: Path) -> dict:
    forbidden_items = []

    for current_root, dir_names, file_names in os.walk(repo_dir):
        current_path = Path(current_root)

        for dir_name in list(dir_names):
            if dir_name.lower() == "node_modules":
                node_modules_path = current_path / dir_name

                forbidden_items.append({
                    "type": "forbidden_folder",
                    "path": str(node_modules_path.relative_to(repo_dir)),
                    "reason": "node_modules folder is committed in repository",
                })

                dir_names.remove(dir_name)

        for file_name in file_names:
            if is_forbidden_env_file(file_name):
                file_path = current_path / file_name

                forbidden_items.append({
                    "type": "forbidden_env_file",
                    "path": str(file_path.relative_to(repo_dir)),
                    "reason": "Environment file is committed. Only .env.example is allowed",
                })

    if forbidden_items:
        return {
            "status": "REJECTED",
            "isRejected": True,
            "rejectionReasons": [
                "Repository contains forbidden files/folders such as node_modules or environment files."
            ],
            "forbiddenItems": forbidden_items,
        }

    return {
        "status": "ACCEPTED_FOR_REVIEW",
        "isRejected": False,
        "rejectionReasons": [],
        "forbiddenItems": [],
    }