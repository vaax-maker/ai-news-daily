#!/usr/bin/env python3
"""
기업 프로필 상세정보 업데이트 스크립트
- 조사된 기업 정보를 company_profiles.yaml에 반영
"""

import yaml
from pathlib import Path

# 조사된 기업 상세 정보 (2024년 기준)
COMPANY_DETAILS = {
    # ===== 중소기업 =====
    "알체라": {
        "category": "중소기업",
        "category_code": "sme",
        "collect_news": True,
        "info": {
            "representative": "황영규",
            "industry": "AI 영상인식 소프트웨어",
            "employees": "181명",
            "description": "AI 기반 안면인식 및 영상인식 솔루션 전문 기업. 토스 얼굴결제, 인천공항 스마트패스 등에 기술 적용. NIST 얼굴인식 테스트 99.99% 정확도 달성.",
            "products": "안면인식 SDK/API, 산불감지 AI(파이어스카우트), eKYC 솔루션"
        },
        "financials": {
            "revenue": "172억원 (2024)",
            "operating_profit": "영업손실",
            "market_cap": "코스닥 상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "미국 의료AI 시장 진출, 금융권 eKYC 수요 증가"
        }
    },
    
    "버넥트": {
        "category": "중소기업",
        "category_code": "sme",
        "collect_news": True,
        "info": {
            "representative": "하태진",
            "industry": "XR(확장현실) 솔루션",
            "employees": "91명",
            "description": "산업용 XR 솔루션 전문 기업. 제조, 에너지, 건설, 국방 등 산업현장 디지털 전환 지원. 2023년 코스닥 상장.",
            "products": "VIRNECT Remote(원격협업), VIRNECT Make(XR저작도구), VIRNECT View, VisionX(AI스마트고글)"
        },
        "financials": {
            "revenue": "65억원 (2024)",
            "operating_profit": "영업손실",
            "market_cap": "코스닥 상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "산업용 XR 수요 증가, 글로벌 시장 확대"
        }
    },
    
    "비브스튜디오스": {
        "category": "중소기업",
        "category_code": "sme",
        "collect_news": True,
        "info": {
            "representative": "김세규",
            "industry": "XR/AR/AI 콘텐츠 제작",
            "employees": "50명",
            "description": "XR, AR, AI 융합 기술 기반 콘텐츠 제작사. MBC '너를 만났다' VR 다큐 제작. 2023년 예비유니콘 선정.",
            "products": "버추얼 프로덕션 VIT, 버추얼휴먼 VIPLE, AI 포토 SNAPAI"
        },
        "financials": {
            "revenue": "92억원 (2023)",
            "operating_profit": "-",
            "market_cap": "비상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "버추얼 프로덕션 수요 증가, AI 콘텐츠 시장 성장"
        }
    },
    
    "덱스터스튜디오": {
        "category": "중소기업",
        "category_code": "sme",
        "collect_news": True,
        "info": {
            "representative": "김용화",
            "industry": "VFX(시각특수효과)/콘텐츠 제작",
            "employees": "350명",
            "description": "대한민국 1세대 VFX 전문 기업. 신과함께, 기생충, 오징어게임 등 참여. 아시아 최고 수준 VFX 기술력 보유.",
            "products": "VFX 제작, DI(색보정), 사운드, 버추얼 프로덕션"
        },
        "financials": {
            "revenue": "537억원 (2024)",
            "operating_profit": "영업손실 89억원",
            "market_cap": "코스닥 상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "K-콘텐츠 글로벌 수요, VFX 아웃소싱 증가"
        }
    },
    
    "갤럭시코퍼레이션": {
        "category": "중소기업",
        "category_code": "sme",
        "collect_news": True,
        "info": {
            "representative": "박지현",
            "industry": "엔터테인먼트/매니지먼트",
            "employees": "-",
            "description": "미디어, IP, 커머스, 테크 융복합 엔터테인먼트 기업. 지드래곤 매니지먼트. 1박2일, 미스터트롯3 등 400편 이상 제작.",
            "products": "예능 제작, 아티스트 매니지먼트, IP 커머스(피스마이너스원 하이볼)"
        },
        "financials": {
            "revenue": "400억원 (2024)",
            "operating_profit": "흑자전환 (2025H1: 120억)",
            "market_cap": "코스닥 상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "지드래곤 월드투어, 신규 IP 확보로 성장 전망"
        }
    },
    
    "JTBC": {
        "category": "중소기업",
        "category_code": "sme",
        "collect_news": True,
        "info": {
            "representative": "-",
            "industry": "방송/미디어",
            "employees": "-",
            "description": "중앙일보 계열 종합편성채널. 뉴스룸, 드라마, 예능 콘텐츠 제작 및 방송.",
            "products": "뉴스, 드라마, 예능 콘텐츠"
        },
        "financials": {
            "revenue": "3,801억원 (2024)",
            "operating_profit": "영업손실 286억원",
            "market_cap": "비상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "광고시장 위축, 수익성 개선 과제"
        }
    },
    
    # ===== 소기업/스타트업 =====
    "콕스스페이스": {
        "category": "소기업",
        "category_code": "small",
        "collect_news": True,
        "info": {
            "representative": "김호연",
            "industry": "웨어러블/XR 디바이스",
            "employees": "12명",
            "description": "제스처 인식 반지형 마우스 VANZY 개발. XR 플랫폼 및 원격협업 솔루션 제공. CES 2025 참가.",
            "products": "VANZY(제스처 반지마우스), 콕스 메타스페이스(XR 원격 플랫폼)"
        },
        "financials": {
            "revenue": "12억원 (누적)",
            "operating_profit": "-",
            "market_cap": "비상장 (스타트업)",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "XR 하드웨어 시장 성장, 유럽 진출 모색"
        }
    },
    
    "펄스나인": {
        "category": "소기업",
        "category_code": "small",
        "collect_news": True,
        "info": {
            "representative": "양병석",
            "industry": "AI 버추얼휴먼",
            "employees": "-",
            "description": "딥리얼 AI 기술 기반 버추얼 휴먼 제작 전문 기업. 가상 아이돌 그룹 이터니티(ETERN!TY) 제작. 49개국 팬덤 보유.",
            "products": "딥리얼 AI, 버추얼 아이돌 이터니티, 아이아팹(AI 콘텐츠 제작소)"
        },
        "financials": {
            "revenue": "비공개 (스타트업)",
            "operating_profit": "-",
            "market_cap": "비상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "버추얼 휴먼 시장 성장, 글로벌 K-pop 수요"
        }
    },
    
    # ===== 중견기업 =====
    "SM엔터테인먼트": {
        "category": "중견기업",
        "category_code": "mid",
        "collect_news": False,
        "info": {
            "representative": "장철혁",
            "industry": "엔터테인먼트",
            "employees": "-",
            "description": "K-pop 4대 기획사. NCT, 에스파, EXO, 레드벨벳 등 소속. 엔터 부문 매출 91.3%.",
            "products": "음원/앨범, 콘서트/투어, 굿즈, IP 라이선스"
        },
        "financials": {
            "revenue": "9,897억원 (2024)",
            "operating_profit": "873억원",
            "market_cap": "코스닥 상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "글로벌 K-pop 수요, 신인 아티스트 라인업"
        }
    },
    
    "에스원": {
        "category": "중견기업",
        "category_code": "mid",
        "collect_news": False,
        "info": {
            "representative": "-",
            "industry": "보안/시큐리티",
            "employees": "-",
            "description": "삼성그룹 계열 종합 보안 서비스 기업. 시큐리티, 빌딩관리, 스마트솔루션 제공.",
            "products": "보안 경비, CCTV, 출입통제, 무인매장 솔루션"
        },
        "financials": {
            "revenue": "2조 8,047억원 (2024)",
            "operating_profit": "2,092억원",
            "market_cap": "코스피 상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "AI/IoT 기반 보안 서비스 확대"
        }
    },
    
    "MBC": {
        "category": "중견기업",
        "category_code": "mid",
        "collect_news": False,
        "info": {
            "representative": "박성제",
            "industry": "방송/미디어",
            "employees": "-",
            "description": "대한민국 지상파 방송사. 뉴스데스크, 드라마, 예능 콘텐츠 제작.",
            "products": "지상파 방송, 콘텐츠 제작, 광고"
        },
        "financials": {
            "revenue": "7,480억원 (2024)",
            "operating_profit": "66억원",
            "market_cap": "비상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "5년 연속 흑자, 콘텐츠 수익 다변화 필요"
        }
    },
    
    "하나금융TI": {
        "category": "중견기업",
        "category_code": "mid",
        "collect_news": False,
        "info": {
            "representative": "김병근",
            "industry": "금융 IT",
            "employees": "-",
            "description": "하나금융그룹 IT 서비스 자회사. 금융 시스템 개발 및 운영.",
            "products": "금융 IT 서비스, 시스템 개발/운영"
        },
        "financials": {
            "revenue": "3,439억원 (2024)",
            "operating_profit": "-",
            "market_cap": "비상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "디지털 금융 전환 수요 증가"
        }
    },
    
    # ===== 대기업 =====
    "대신증권": {
        "category": "대기업",
        "category_code": "large",
        "collect_news": False,
        "info": {
            "representative": "양홍석",
            "industry": "금융/증권",
            "employees": "-",
            "description": "대한민국 종합 증권사. 위탁매매, IB, 자산운용 등 금융 서비스 제공.",
            "products": "증권 위탁매매, 투자은행(IB), 자산관리"
        },
        "financials": {
            "revenue": "4조 875억원 (2024)",
            "operating_profit": "-",
            "market_cap": "코스피 상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "안정적 금융 서비스 수요"
        }
    },
    
    "한국항공우주산업": {
        "category": "대기업",
        "category_code": "large",
        "collect_news": False,
        "info": {
            "representative": "강구영",
            "industry": "방위산업/항공",
            "employees": "-",
            "description": "대한민국 유일 완제기 항공기 제작 기업. FA-50, KF-21, 수리온 등 제작. 방위산업 핵심 기업.",
            "products": "전투기(KF-21, FA-50), 헬기(수리온), 항공 정비"
        },
        "financials": {
            "revenue": "3조 6,337억원 (2024)",
            "operating_profit": "-",
            "market_cap": "코스피 상장",
            "stock_price": "-",
            "per": "-",
            "pbr": "-",
            "outlook": "KF-21 양산, 해외 수출 확대"
        }
    },
}


def update_profiles(profiles_path="config/company_profiles.yaml"):
    """기존 프로필에 상세정보 업데이트"""
    
    # 기존 프로필 로드
    with open(profiles_path, 'r', encoding='utf-8') as f:
        profiles = yaml.safe_load(f) or {}
    
    updated_count = 0
    
    # 상세정보 업데이트
    for company_name, details in COMPANY_DETAILS.items():
        if company_name in profiles:
            profiles[company_name].update(details)
            updated_count += 1
            print(f"  ✓ {company_name}")
        else:
            print(f"  ✗ {company_name} (프로필에 없음)")
    
    # 저장
    with open(profiles_path, 'w', encoding='utf-8') as f:
        yaml.dump(profiles, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    
    print(f"\n✅ {updated_count}개 기업 프로필 업데이트 완료!")
    return updated_count


if __name__ == "__main__":
    print("🚀 기업 프로필 상세정보 업데이트 시작...")
    update_profiles()
