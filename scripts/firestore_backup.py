#!/usr/bin/env python3
"""
scripts/firestore_backup.py — Firestore 컬렉션 JSON 백업

사용법:
    python scripts/firestore_backup.py
    python scripts/firestore_backup.py --collections all
    python scripts/firestore_backup.py --collections quickview_pages members
"""

import os
import sys
import json
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKUP_DIR = "backups/firestore"
DEFAULT_COLLECTIONS = ["quickview_pages", "members", "gov"]


def get_firestore_client():
    """generate_quickview.py의 get_firestore_client 패턴 재사용."""
    try:
        from src.generators.quickview import get_firestore_client as _get
        return _get()
    except ImportError:
        # Fallback: 직접 초기화
        import firebase_admin
        from firebase_admin import credentials, firestore as fs

        if firebase_admin._apps:
            return fs.client()

        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
        if service_account_json:
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(service_account_json)
                tmp_path = f.name
            cred = credentials.Certificate(tmp_path)
            firebase_admin.initialize_app(cred)
            os.unlink(tmp_path)
        else:
            cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
            if cred_path and os.path.isfile(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            else:
                raise RuntimeError(
                    "Firestore 인증 정보 없음. "
                    "FIREBASE_SERVICE_ACCOUNT 또는 GOOGLE_APPLICATION_CREDENTIALS 환경변수를 설정하세요."
                )
        return fs.client()


def export_collection(db, collection_name: str, output_path: str) -> int:
    """컬렉션 전체를 JSON으로 내보냄. 저장된 문서 수 반환."""
    docs = db.collection(collection_name).stream()
    records = []
    for doc in docs:
        records.append({"id": doc.id, "data": doc.to_dict()})

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, default=str)

    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Firestore 컬렉션 JSON 백업")
    parser.add_argument(
        "--collections",
        nargs="+",
        default=["all"],
        help="백업할 컬렉션 이름 (기본: all)"
    )
    args = parser.parse_args()

    collections = DEFAULT_COLLECTIONS if args.collections == ["all"] else args.collections

    now = datetime.datetime.now()
    backup_id = now.strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, backup_id)
    os.makedirs(backup_path, exist_ok=True)

    print(f"[Firestore Backup] 백업 시작: {backup_id}")
    print(f"  대상 컬렉션: {', '.join(collections)}")

    try:
        db = get_firestore_client()
    except Exception as e:
        print(f"❌ Firestore 연결 실패: {e}")
        sys.exit(1)

    doc_counts = {}
    for col in collections:
        output_file = os.path.join(backup_path, f"{col}.json")
        try:
            count = export_collection(db, col, output_file)
            doc_counts[col] = count
            print(f"  ✅ {col}: {count}개 문서 저장 → {output_file}")
        except Exception as e:
            print(f"  ❌ {col}: 백업 실패 — {e}")
            doc_counts[col] = -1

    manifest = {
        "created_at": now.isoformat(),
        "backup_id": backup_id,
        "collections": collections,
        "doc_counts": doc_counts,
    }
    manifest_path = os.path.join(backup_path, "_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    total = sum(v for v in doc_counts.values() if v >= 0)
    print(f"\n[Firestore Backup] ✅ 완료: {total}개 문서 백업 → {backup_path}")


if __name__ == "__main__":
    main()
