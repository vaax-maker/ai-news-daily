#!/usr/bin/env bash
# scripts/checkpoint.sh — Git 태그 기반 코드 체크포인트 관리
# 사용법:
#   ./scripts/checkpoint.sh create {label}   — 현재 커밋에 체크포인트 태그 생성
#   ./scripts/checkpoint.sh list             — backup/* 태그 목록 출력
#   ./scripts/checkpoint.sh restore {tag}    — 해당 태그로 hard reset (확인 프롬프트)
#   ./scripts/checkpoint.sh delete {tag}     — 로컬 태그 삭제

set -e

COMMAND=$1
LABEL=$2
TAG_PREFIX="backup"

usage() {
    echo "사용법: $0 {create|list|restore|delete} [label|tag]"
    echo ""
    echo "  create {label}   현재 커밋에 태그 생성 (예: pre-refactor)"
    echo "  list             backup/* 태그 목록 출력"
    echo "  restore {tag}    해당 태그로 코드 복원 (hard reset)"
    echo "  delete {tag}     로컬 태그 삭제"
    exit 1
}

case "$COMMAND" in
    create)
        if [ -z "$LABEL" ]; then
            echo "❌ label이 필요합니다. 예: $0 create pre-refactor"
            exit 1
        fi
        TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
        TAG_NAME="${TAG_PREFIX}/${TIMESTAMP}-${LABEL}"
        git tag "$TAG_NAME"
        echo "✅ 체크포인트 생성: $TAG_NAME"
        echo "   복원 명령: $0 restore ${TIMESTAMP}-${LABEL}"
        ;;

    list)
        echo "📋 체크포인트 목록 (backup/* 태그):"
        echo "────────────────────────────────────────"
        TAGS=$(git tag -l "${TAG_PREFIX}/*" --sort=-creatordate)
        if [ -z "$TAGS" ]; then
            echo "  (체크포인트 없음)"
        else
            while IFS= read -r tag; do
                DATE=$(git log -1 --format="%ci" "$tag" 2>/dev/null || echo "unknown")
                MSG=$(git log -1 --format="%s" "$tag" 2>/dev/null || echo "")
                echo "  $tag"
                echo "    커밋: $MSG"
                echo "    날짜: $DATE"
                echo ""
            done <<< "$TAGS"
        fi
        ;;

    restore)
        if [ -z "$LABEL" ]; then
            echo "❌ 태그명이 필요합니다. 예: $0 restore 20260222-143000-pre-refactor"
            exit 1
        fi
        # 전체 태그명 또는 suffix로 매칭
        if git rev-parse "${TAG_PREFIX}/${LABEL}" >/dev/null 2>&1; then
            TAG_NAME="${TAG_PREFIX}/${LABEL}"
        elif git rev-parse "$LABEL" >/dev/null 2>&1; then
            TAG_NAME="$LABEL"
        else
            echo "❌ 태그를 찾을 수 없습니다: $LABEL"
            echo "   사용 가능한 태그: $0 list"
            exit 1
        fi

        echo "⚠️  경고: '$TAG_NAME' 시점으로 코드를 복원합니다."
        echo "   현재 uncommitted 변경사항이 모두 사라집니다."
        echo "   docs/ 와 data/ 는 이 스크립트 범위 밖입니다."
        echo ""
        printf "계속하시겠습니까? (y/N): "
        read -r CONFIRM
        if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
            echo "취소되었습니다."
            exit 0
        fi
        git reset --hard "$TAG_NAME"
        echo "✅ 복원 완료: $TAG_NAME"
        ;;

    delete)
        if [ -z "$LABEL" ]; then
            echo "❌ 태그명이 필요합니다."
            exit 1
        fi
        if git rev-parse "${TAG_PREFIX}/${LABEL}" >/dev/null 2>&1; then
            TAG_NAME="${TAG_PREFIX}/${LABEL}"
        else
            TAG_NAME="$LABEL"
        fi
        git tag -d "$TAG_NAME"
        echo "✅ 태그 삭제: $TAG_NAME"
        ;;

    *)
        usage
        ;;
esac
