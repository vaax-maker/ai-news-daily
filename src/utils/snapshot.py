"""
src/utils/snapshot.py — data/ 디렉토리 스냅샷 관리
사용법:
    from src.utils.snapshot import DataSnapshot
    snap = DataSnapshot()
    snap_id = snap.create("pre-work")
    snap.restore(snap_id)
    snap.list()
    snap.cleanup(keep=7)
"""

import os
import json
import shutil
import datetime
from pathlib import Path


class DataSnapshot:
    BASE_DIR = "data/_snapshots"
    MAX_KEEP = 7  # 기본 보관 개수
    EXCLUDE = {"_snapshots", "usage.db"}  # 스냅샷에 포함하지 않을 항목

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.snapshot_dir = os.path.join(data_dir, "_snapshots")

    def create(self, label: str = "auto") -> str:
        """data/ 디렉토리 스냅샷 생성. 스냅샷 ID 반환."""
        now = datetime.datetime.now()
        snapshot_id = now.strftime("%Y%m%d_%H%M%S") + f"_{label}"
        dest = os.path.join(self.snapshot_dir, snapshot_id)
        os.makedirs(dest, exist_ok=True)

        if not os.path.isdir(self.data_dir):
            print(f"[Snapshot] data/ 디렉토리가 없습니다: {self.data_dir}")
            return snapshot_id

        files_count = 0
        size_bytes = 0

        for item in os.listdir(self.data_dir):
            if item in self.EXCLUDE:
                continue
            src_path = os.path.join(self.data_dir, item)
            dst_path = os.path.join(dest, item)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path)
                for root, _, files in os.walk(dst_path):
                    for f in files:
                        fp = os.path.join(root, f)
                        size_bytes += os.path.getsize(fp)
                        files_count += 1
            elif os.path.isfile(src_path):
                shutil.copy2(src_path, dst_path)
                size_bytes += os.path.getsize(dst_path)
                files_count += 1

        meta = {
            "id": snapshot_id,
            "label": label,
            "created_at": now.isoformat(),
            "files_count": files_count,
            "size_bytes": size_bytes,
        }
        with open(os.path.join(dest, "_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"[Snapshot] ✅ 생성 완료: {snapshot_id} ({files_count}개 파일, {size_bytes // 1024}KB)")
        return snapshot_id

    def restore(self, snapshot_id: str) -> None:
        """스냅샷 ID로 data/ 복원. 현재 data/ 덮어쓰기 전 확인."""
        snap_path = os.path.join(self.snapshot_dir, snapshot_id)
        if not os.path.isdir(snap_path):
            raise FileNotFoundError(f"스냅샷을 찾을 수 없습니다: {snapshot_id}")

        print(f"⚠️  경고: '{snapshot_id}' 스냅샷으로 data/ 를 복원합니다.")
        print("   현재 data/ 의 내용이 덮어씌워집니다.")
        confirm = input("계속하시겠습니까? (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("취소되었습니다.")
            return

        # 복원: 스냅샷의 파일을 data/ 에 덮어쓰기
        for item in os.listdir(snap_path):
            if item == "_meta.json":
                continue
            src = os.path.join(snap_path, item)
            dst = os.path.join(self.data_dir, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            elif os.path.isfile(src):
                shutil.copy2(src, dst)

        print(f"[Snapshot] ✅ 복원 완료: {snapshot_id}")

    def list(self) -> list:
        """스냅샷 목록 반환: [{id, label, created_at, size_mb}]"""
        if not os.path.isdir(self.snapshot_dir):
            return []

        result = []
        for entry in sorted(os.listdir(self.snapshot_dir), reverse=True):
            meta_path = os.path.join(self.snapshot_dir, entry, "_meta.json")
            if not os.path.isfile(meta_path):
                continue
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            result.append({
                "id": meta.get("id", entry),
                "label": meta.get("label", ""),
                "created_at": meta.get("created_at", ""),
                "size_mb": round(meta.get("size_bytes", 0) / 1024 / 1024, 2),
                "files_count": meta.get("files_count", 0),
            })
        return result

    def cleanup(self, keep: int = MAX_KEEP) -> int:
        """오래된 스냅샷 삭제. 삭제된 개수 반환."""
        snapshots = self.list()
        if len(snapshots) <= keep:
            return 0

        to_delete = snapshots[keep:]
        deleted = 0
        for snap in to_delete:
            snap_path = os.path.join(self.snapshot_dir, snap["id"])
            if os.path.isdir(snap_path):
                shutil.rmtree(snap_path)
                deleted += 1
                print(f"[Snapshot] 삭제: {snap['id']}")

        print(f"[Snapshot] 정리 완료: {deleted}개 삭제, {keep}개 보관")
        return deleted


if __name__ == "__main__":
    import sys
    snap = DataSnapshot()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "create":
        label = sys.argv[2] if len(sys.argv) > 2 else "manual"
        snap.create(label)
    elif cmd == "restore":
        if len(sys.argv) < 3:
            print("사용법: python -m src.utils.snapshot restore {snapshot_id}")
            sys.exit(1)
        snap.restore(sys.argv[2])
    elif cmd == "list":
        items = snap.list()
        if not items:
            print("(스냅샷 없음)")
        for item in items:
            print(f"  {item['id']}  {item['size_mb']}MB  {item['files_count']}files  {item['created_at']}")
    elif cmd == "cleanup":
        keep = int(sys.argv[2]) if len(sys.argv) > 2 else DataSnapshot.MAX_KEEP
        snap.cleanup(keep=keep)
