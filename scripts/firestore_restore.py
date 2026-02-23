#!/usr/bin/env python3
"""
scripts/firestore_restore.py — Firestore 백업 JSON에서 복원

사용법:
    python scripts/firestore_restore.py --from backups/firestore/20260222_143000
    python scripts/firestore_restore.py --collection quickview_pages \\
                                        --from backups/firestore/20260222_143000/quickview_pages.json
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_firestore_client():
    try:
        from src.generators.quickview import get_firestore_client as _get
        return _get()
    except ImportError:
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
                raise RuntimeError("Firestore 인증 정보 없음")
        return fs.client()


def import_collection(db, collection_name: str, json_path: str) -> int:
    """JSON 파일에서 컬렉션 복원. 복원된 문서 수 반환."""
    with open(json_path, encoding="utf-8") as f:
        records = json.load(f)

    col_ref = db.collection(collection_name)
    count = 0
    for record in records:
        doc_id = record.get("id")
        data = record.get("data", {})
        if doc_id:
            col_ref.document(doc_id).set(data)
        else:
            col_ref.add(data)
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser(description="Firestore 백업 JSON 복원")
    parser.add_argument(
        "--from", dest="source",
        required=True,
        help="백업 디렉토리 또는 특정 JSON 파일 경로"
    )
    parser.add_argument(
        "--collection",
        help="특정 컬렉션만 복원 (--from 이 JSON 파일인 경우 필수)"
    )
    args = parser.parse_args()

    source = args.source

    # 단일 JSON 파일 복원
    if source.endswith(".json"):
        if not args.collection:
            print("❌ JSON 파일 복원 시 --collection 을 지정하세요.")
            sys.exit(1)
        files = [(args.collection, source)]
    else:
        # 디렉토리에서 모든 컬렉션 복원
        if not os.path.isdir(source):
            print(f"❌ 백업 경로를 찾을 수 없습니다: {source}")
            sys.exit(1)
        manifest_path = os.path.join(source, "_manifest.json")
        if os.path.isfile(manifest_path):
            with open(manifest_path) as f:
                manifest = json.load(f)
            collections = manifest.get("collections", [])
        else:
            collections = [
                f.replace(".json", "")
                for f in os.listdir(source)
                if f.endswith(".json") and not f.startswith("_")
            ]
        files = [(col, os.path.join(source, f"{col}.json")) for col in collections]

    print(f"⚠️  Firestore에 {len(files)}개 컬렉션을 복원합니다. 기존 데이터가 덮어씌워집니다.")
    confirm = input("계속하시겠습니까? (y/N): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("취소되었습니다.")
        return

    try:
        db = get_firestore_client()
    except Exception as e:
        print(f"❌ Firestore 연결 실패: {e}")
        sys.exit(1)

    for collection_name, json_path in files:
        if not os.path.isfile(json_path):
            print(f"  ⚠️  {collection_name}: 파일 없음 → 건너뜀")
            continue
        try:
            count = import_collection(db, collection_name, json_path)
            print(f"  ✅ {collection_name}: {count}개 문서 복원")
        except Exception as e:
            print(f"  ❌ {collection_name}: 복원 실패 — {e}")

    print("\n[Firestore Restore] 완료")


if __name__ == "__main__":
    main()
