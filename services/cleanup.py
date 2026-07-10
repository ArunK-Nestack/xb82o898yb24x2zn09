import os
import stat
import time
import shutil
from pathlib import Path


def force_writable_and_retry(function, path, exc_info):
    try:
        os.chmod(path, stat.S_IWRITE)
        function(path)
    except Exception:
        pass


def safe_delete_folder(path: Path) -> bool:
    if not path.exists():
        return False

    try:
        shutil.rmtree(path, onerror=force_writable_and_retry)
        return True
    except PermissionError:
        time.sleep(1)
        shutil.rmtree(path, onerror=force_writable_and_retry)
        return True


def cleanup_temp_repos(local_repo_dir: str | None = None):
    paths_to_try = []

    if local_repo_dir:
        repo_path = Path(local_repo_dir)

        if repo_path.exists():
            paths_to_try.append(repo_path.parent)

    paths_to_try.append(Path.cwd() / "temp-repos-py")
    paths_to_try.append(Path.cwd() / "temp-repos")

    deleted_anything = False

    for path in paths_to_try:
        if path.exists() and path.is_dir():
            safe_delete_folder(path)
            print("")
            print(f"Cleanup completed: deleted {path}")
            deleted_anything = True
            break

    if not deleted_anything:
        print("")
        print("Cleanup completed: no temp repo folder found.")