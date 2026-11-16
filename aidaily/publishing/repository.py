"""Git repository operations used by publishing workflows."""

from __future__ import annotations

import subprocess
import shutil
import tempfile
from pathlib import Path


def publish_generated(repository: str | Path, paths: list[str], message: str,
                      remote: str = "origin", branch: str = "main",
                      dry_run: bool = False) -> bool:
    """Publish selected outputs in a disposable clone; never mutate the runtime tree.

    Returns whether a publication commit was necessary. Dry runs also use an
    isolated commit and Git's push dry-run, without changing either repository.
    Missing paths and symlinks are rejected rather than publishing partial data.
    """
    source = Path(repository).resolve()
    if not paths:
        return False
    if remote.startswith("-") or branch.startswith("-"):
        raise ValueError("Invalid publication remote or branch")
    selected: list[Path] = []
    for value in paths:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts or ".git" in relative.parts or not relative.parts:
            raise ValueError("Publication paths must be relative generated paths")
        candidate = source / relative
        if not candidate.exists():
            raise ValueError(f"Missing publication output: {relative}")
        entries = [candidate, *candidate.rglob("*")] if candidate.is_dir() else [candidate]
        if any(entry.is_symlink() or not entry.resolve().is_relative_to(source) for entry in entries):
            raise ValueError("Publication outputs cannot contain symlinks")
        if any(".git" in entry.relative_to(source).parts for entry in entries):
            raise ValueError("Publication outputs cannot include Git metadata")
        selected.append(relative)

    def checked(command: list[str], cwd: Path, operation: str) -> subprocess.CompletedProcess:
        try:
            result = run(command, cwd, check=False)
        except (subprocess.SubprocessError, OSError):
            raise RuntimeError(f"Isolated publication failed during {operation}") from None
        if result.returncode:
            # Remote URLs and Git stderr can contain embedded credentials.
            raise RuntimeError(f"Isolated publication failed during {operation}")
        return result

    checked(["git", "check-ref-format", "--branch", branch], source, "branch validation")
    url = checked(["git", "remote", "get-url", "--push", remote], source, "remote lookup").stdout.strip()
    # Relative filesystem remotes are resolved relative to the runtime repository.
    if not Path(url).is_absolute() and ":" not in url:
        url = str((source / url).resolve())
    with tempfile.TemporaryDirectory(prefix="aidaily-publish-") as temporary:
        clone = Path(temporary) / "repository"
        checked(["git", "clone", "--quiet", "--single-branch", "--branch", branch,
                 "--", url, str(clone)], source, "clone")
        for relative in selected:
            origin, destination = source / relative, clone / relative
            # Refuse remote symlink ancestors before writing into the clone.
            ancestors = [destination]
            parent = destination.parent
            while parent != clone:
                ancestors.append(parent)
                parent = parent.parent
            if any(part.is_symlink() for part in ancestors):
                raise ValueError("Remote publication destination contains a symlink")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if origin.is_dir():
                shutil.copytree(origin, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(origin, destination)
            if origin.is_file() and origin.suffix.lower() == '.html':
                from aidaily.publishing.engagement import instrument_html
                destination.write_text(instrument_html(destination.read_text(encoding='utf-8')), encoding='utf-8')
        checked(["git", "add", "--", *map(str, selected)], clone, "staging")
        status = run(["git", "diff", "--cached", "--quiet"], clone, check=False)
        if status.returncode == 0:
            return False
        if status.returncode != 1:
            raise RuntimeError("Isolated publication failed during diff")
        checked(["git", "-c", "user.name=AI Daily", "-c",
                 "user.email=aifoundry01@gmail.com", "commit", "--quiet", "-m", message], clone, "commit")
        command = ["git", "push", *(["--dry-run"] if dry_run else []), "origin", f"HEAD:{branch}"]
        pushed = run(command, clone, check=False)
        if pushed.returncode and not dry_run:
            checked(["git", "fetch", "origin", branch], clone, "race fetch")
            checked(["git", "-c", "user.name=AI Daily", "-c", "user.email=aifoundry01@gmail.com",
                     "rebase", "FETCH_HEAD"], clone, "race rebase")
            pushed = run(command, clone, check=False)
        if pushed.returncode:
            raise RuntimeError("Isolated publication push failed; inspect remote before retrying")
        return True


def run(command: list[str], repository: str | Path, *, check: bool = True,
        timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(repository),
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def sync(repository: str | Path, remote: str = "origin", branch: str = "main") -> None:
    run(["git", "pull", "--rebase", "--autostash", remote, branch], repository)


def commit_and_push(repository: str | Path, paths: list[str], message: str,
                    remote: str = "origin", branch: str = "main",
                    dry_run: bool = False) -> bool:
    run(["git", "add", "--", *paths], repository)
    status = run(["git", "diff", "--cached", "--quiet"], repository, check=False)
    if status.returncode == 0:
        return False
    run([
        "git", "-c", "user.name=AI Daily",
        "-c", "user.email=aifoundry01@gmail.com",
        "commit", "-m", message,
    ], repository)
    command = ["git", "push"] + (["--dry-run"] if dry_run else [])
    pushed = run(command + [remote, f"HEAD:{branch}"], repository, check=False)
    if pushed.returncode != 0 and not dry_run:
        run(["git", "fetch", remote], repository)
        run(["git", "rebase", "--autostash", f"{remote}/{branch}"], repository)
        pushed = run(command + [remote, f"HEAD:{branch}"], repository, check=False)
    if pushed.returncode != 0:
        raise RuntimeError(f"git push failed: {(pushed.stderr or pushed.stdout)[-500:]}")
    return True
