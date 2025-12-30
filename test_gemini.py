#!/usr/bin/env python3
"""Test the LLM summarization prompt with Gemini only."""

import os
import sys

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.generators.llm import _summarize_with_gemini

# Sample article text
sample_text = """
글로벌 언어처리유닛(Language Processing Unit. 이하, LPU) 인공지능(AI) 칩 스타트업 '그록(Groq)'이 엔비디아(Nvidia)와 인공지능(AI) 인프라 경쟁력 강화를 위해 약 200억 달러(약 29조원) 규모의 기술 라이선스 및 핵심 인재 영입 계약을 체결했다고 밝혔다. 이 거래는 엔비디아의 역대 최대 규모 전략적 움직임으로 평가되며, AI 추론(inference) 칩 기술 확보에 중점을 둔 것이 특징이다. 

24일(현지시간) 그록에 따르면 엔비디아는 이번 계약을 통해 그록의 핵심 지적재산권(IP)과 기술을 비독점(non-exclusive) 라이선스 방식으로 확보했다. 그록 측은 거래 조건을 공개하며 "그록클라우드(GroqCloud) 사업을 제외한 대부분의 자산을 대상으로 계약이 이뤄졌다"고 설명했다.

이번 계약의 일환으로 그록의 창립자인 조나단 로스(Jonathan Ross)와 사장 써니 마드라(Sunny Madra)를 포함한 주요 팀원들이 엔비디아에 합류한다.

그록은 LPU 추론 특화 칩은 기존 GPU 대비 높은 실시간 응답 속도와 에너지 효율성을 강점으로 내세워 왔다. LPUs는 특히 대형언어모델(LLM)의 추론 작업에서 저지연(low latency)과 고성능을 발휘해 GPU 중심의 AI 컴퓨팅 지형에 도전하는 기술로 평가된다.
"""

sample_title = "엔비디아, AI 하드웨어 지형 확장한다! 그록과 29조원 규모 계약"

# Build prompt (same as in llm.py)
prompt = f"""<task>
뉴스 기사를 섹션별로 구조화된 상세 요약으로 작성
</task>

<output_format>
## 1. 핵심 내용
**주제**: 한 문장으로 핵심 요약

- 세부 내용 1 (구체적 수치/금액/일정 포함)
- 세부 내용 2
- 세부 내용 3

## 2. 배경 및 맥락
- 왜 이런 결정/사건이 발생했는지
- 관련 기술/시장 상황 설명

## 3. 주요 관계자/기업
- 관련 기업/인물과 역할

## 4. 전략적 의미
- 산업/시장에 미치는 영향
- 경쟁 구도 변화

## 5. 향후 전망
- 예상되는 후속 영향
- 리스크 요인

**한 줄 요약**: (기사의 핵심을 한 문장으로)
</output_format>

<constraint>
- 각 섹션에 2-4개의 bullet point 포함
- 수치(금액, 날짜, 비율)는 반드시 명시
- 문장 끝은 ~함, ~임, ~됨 형식
- 전체 분량 400-600자
- 불필요한 섹션은 생략 가능
</constraint>

<article>
제목: {sample_title}

{sample_text[:2500]}
</article>

위 기사를 구조화된 형식으로 요약하세요.
"""

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Gemini 프롬프트 테스트")
    print("=" * 60)
    print(f"\n📰 기사 제목: {sample_title}\n")
    
    gemini_key = os.getenv("GEMINI_API_KEY")
    print(f"🔑 GEMINI_API_KEY: {'설정됨 (' + gemini_key[:10] + '...)' if gemini_key else '❌ 미설정'}")
    print()
    
    if not gemini_key:
        print("❌ GEMINI_API_KEY가 설정되지 않았습니다.")
        sys.exit(1)
    
    print("⏳ Gemini로 요약 중...\n")
    
    try:
        result = _summarize_with_gemini(prompt)
        print("=" * 60)
        print("✅ Gemini 요약 결과:")
        print("=" * 60)
        print(result)
        print("=" * 60)
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
