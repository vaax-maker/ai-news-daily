#!/usr/bin/env bash
# AI 이슈 모니터링 에이전트 자동 실행 스크립트 (macOS 크론탭용)

# 환경 변수 로그 폴더 설정
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$PROJECT_DIR"
cd "$PROJECT_DIR"

echo "==========================================="
echo "▶ 실행 시작: $(date)"

# 파이썬 가상환경 생성 (최초 1회)
if [ ! -d ".venv" ]; then
    echo "가상환경(.venv) 생성 중..."
    python3 -m venv .venv
fi

# 가상환경 활성화
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt > /dev/null 2>&1
playwright install chromium > /dev/null 2>&1

# NotebookLM 스킬 최신화 및 준비
SKILLS_DIR="$HOME/.agents/skills/notebooklm"
mkdir -p "$SKILLS_DIR"
if [ ! -d "/tmp/skills_repo" ]; then
    git clone https://github.com/sickn33/antigravity-awesome-skills.git /tmp/skills_repo > /dev/null 2>&1
else
    cd /tmp/skills_repo && git pull > /dev/null 2>&1
    cd "$PROJECT_DIR"
fi
cp -r /tmp/skills_repo/skills/notebooklm/* "$SKILLS_DIR/"

# 메인 에이전트 실행
python3 scripts/run_agent.py

echo "▶ 실행 종료: $(date)"
echo "==========================================="
