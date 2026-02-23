#!/usr/bin/env python3
"""
scripts/rollback_docs.py — docs/ 디렉토리 git 기반 롤백 도구

사용법:
    python scripts/rollback_docs.py status              — 최근 docs/ 변경 커밋 목록
    python scripts/rollback_docs.py last                — 마지막 docs/ 변경 커밋 revert
    python scripts/rollback_docs.py --before 2026-02-22 — 날짜 이전 마지막 정상 커밋으로 복원
"""

import subprocess
import argparse
import sys


def run(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def get_docs_commits(limit: int = 10) -> list:
    """docs/ 를 변경한 최근 커밋 목록 반환."""
    result = run(["git", "log", "--oneline", f"-{limit}", "--", "docs/"])
    lines = result.stdout.strip().splitlines()
    commits = []
    for line in lines:
        if " " in line:
            hash_, msg = line.split(" ", 1)
            commits.append({"hash": hash_, "message": msg})
    return commits


def get_commit_before_date(date_str: str) -> str | None:
    """주어진 날짜 이전 마지막 docs/ 변경 커밋 해시 반환."""
    result = run([
        "git", "log", "--oneline", "--before", date_str, "-1", "--", "docs/"
    ])
    line = result.stdout.strip()
    if not line:
        return None
    return line.split(" ", 1)[0]


def status():
    """최근 docs/ 변경 커밋 목록 출력."""
    commits = get_docs_commits(limit=15)
    if not commits:
        print("docs/ 변경 커밋이 없습니다.")
        return
    print("📋 최근 docs/ 변경 커밋:")
    print("────────────────────────────────────────")
    for c in commits:
        print(f"  {c['hash']}  {c['message']}")


def revert_last():
    """마지막 docs/ 변경 커밋을 revert."""
    commits = get_docs_commits(limit=1)
    if not commits:
        print("❌ docs/ 변경 커밋이 없습니다.")
        sys.exit(1)

    commit = commits[0]
    print(f"⚠️  '{commit['hash']} {commit['message']}' 커밋을 revert합니다.")
    confirm = input("계속하시겠습니까? (y/N): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("취소되었습니다.")
        return

    # --no-commit 으로 revert (staging 상태 유지)
    result = run(["git", "revert", "--no-commit", commit["hash"]], check=False)
    if result.returncode != 0:
        print(f"❌ revert 실패:\n{result.stderr}")
        sys.exit(1)

    result = run(["git", "commit", "-m", f"revert: rollback docs/ ({commit['hash']})"])
    print(f"✅ revert 완료: {commit['hash']}")


def restore_before(date_str: str):
    """주어진 날짜 이전 마지막 정상 커밋으로 docs/ 복원."""
    commit_hash = get_commit_before_date(date_str)
    if not commit_hash:
        print(f"❌ {date_str} 이전 docs/ 변경 커밋이 없습니다.")
        sys.exit(1)

    print(f"⚠️  '{commit_hash}' 시점으로 docs/ 를 복원합니다.")
    print(f"   ({date_str} 이전 마지막 커밋)")
    confirm = input("계속하시겠습니까? (y/N): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("취소되었습니다.")
        return

    result = run(["git", "checkout", commit_hash, "--", "docs/"], check=False)
    if result.returncode != 0:
        print(f"❌ checkout 실패:\n{result.stderr}")
        sys.exit(1)

    result = run([
        "git", "commit", "-m",
        f"restore: docs/ to {commit_hash} (before {date_str})"
    ])
    print(f"✅ docs/ 복원 완료: {commit_hash}")


def main():
    parser = argparse.ArgumentParser(
        description="docs/ 디렉토리 git 기반 롤백 도구"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["status", "last"],
        help="status: 최근 커밋 목록 | last: 마지막 커밋 revert"
    )
    parser.add_argument(
        "--before",
        metavar="YYYY-MM-DD",
        help="해당 날짜 이전 마지막 정상 커밋으로 복원"
    )
    args = parser.parse_args()

    if args.before:
        restore_before(args.before)
    elif args.command == "status":
        status()
    elif args.command == "last":
        revert_last()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
