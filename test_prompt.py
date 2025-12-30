#!/usr/bin/env python3
"""Test the new LLM summarization prompt."""

import os
import sys

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.generators.llm import summarize_article

# Sample article text (엔비디아-그록 기사)
sample_text = """
글로벌 언어처리유닛(Language Processing Unit. 이하, LPU) 인공지능(AI) 칩 스타트업 '그록(Groq)'이 엔비디아(Nvidia)와 인공지능(AI) 인프라 경쟁력 강화를 위해 약 200억 달러(약 29조원) 규모의 기술 라이선스 및 핵심 인재 영입 계약을 체결했다고 밝혔다. 이 거래는 엔비디아의 역대 최대 규모 전략적 움직임으로 평가되며, AI 추론(inference) 칩 기술 확보에 중점을 둔 것이 특징이다. 

24일(현지시간) 그록에 따르면 엔비디아는 이번 계약을 통해 그록의 핵심 지적재산권(IP)과 기술을 비독점(non-exclusive) 라이선스 방식으로 확보했다. 그록 측은 거래 조건을 공개하며 "그록클라우드(GroqCloud) 사업을 제외한 대부분의 자산을 대상으로 계약이 이뤄졌다"고 설명했다. 그록(Groq)은 독립 기업으로 남되, 엔비디아는 핵심 기술과 엔지니어링 인력을 조직 내로 흡수하게 된다. 

이번 계약의 일환으로 그록의 창립자인 조나단 로스(Jonathan Ross)와 사장 써니 마드라(Sunny Madra)를 포함한 주요 팀원들이 엔비디아에 합류한다. 이들은 엔비디아 내에서 그록으로부터 라이선스를 받은 기술을 고도화하고 확장하는 역할을 맡게 된다.

그록은 LPU 추론 특화 칩은 기존 GPU 대비 높은 실시간 응답 속도와 에너지 효율성을 강점으로 내세워 왔다. LPUs는 특히 대형언어모델(LLM)의 추론 작업에서 저지연(low latency)과 고성능을 발휘해 GPU 중심의 AI 컴퓨팅 지형에 도전하는 기술로 평가된다.

엔비디아는 이러한 기술을 "AI 팩토리(AI Factory)" 아키텍처에 통합함으로써, 실시간 AI 서비스·추론 워크로드에 대한 경쟁력을 한층 강화할 계획이라고 밝혔다.
"""

sample_title = "엔비디아, AI 하드웨어 지형 확장한다! 그록과 29조원 규모 계약"

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 LLM 프롬프트 테스트")
    print("=" * 60)
    print(f"\n📰 기사 제목: {sample_title}\n")
    
    # Check API keys
    gemini_key = os.getenv("GEMINI_API_KEY")
    grok_key = os.getenv("GROK_API_KEY")
    
    print(f"🔑 GEMINI_API_KEY: {'설정됨' if gemini_key else '❌ 미설정'}")
    print(f"🔑 GROK_API_KEY: {'설정됨' if grok_key else '❌ 미설정'}")
    print()
    
    if not gemini_key and not grok_key:
        print("❌ API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
        sys.exit(1)
    
    print("⏳ LLM 요약 중...\n")
    
    try:
        result = summarize_article(sample_text, sample_title, "AI")
        print("=" * 60)
        print("✅ 요약 결과:")
        print("=" * 60)
        print(result)
        print("=" * 60)
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
