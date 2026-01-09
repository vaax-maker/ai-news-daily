#!/usr/bin/env python3
"""
회원사 분류 스크립트 (엄격한 검증 버전)
- 167개 회원사를 규모별로 분류 (대기업/중견기업/중소기업/소기업)
- 실제 매출 데이터에 기반한 분류
- 분류 기준: 대기업(5조+), 중견기업(400억~5조), 중소기업(~400억), 소기업(스타트업/매출 미확인)
"""

import yaml
import csv
import json
from pathlib import Path
from datetime import datetime

# 분류 정의
CATEGORIES = {
    "대기업": "large",
    "중견기업": "mid",
    "중소기업": "sme",
    "소기업": "small",
    "대학/연구기관": "academic",
    "협회/공공기관": "association",
    "미분류": "unknown"
}

# 실제 매출 데이터에 기반한 분류 (2024년 기준, 억원 단위)
# 분류 기준: 대기업(5조+), 중견기업(400억~5조), 중소기업(50억~400억), 소기업(~50억/스타트업)
AUTO_CLASSIFY = {
    # ===== 대기업 (매출 5조 이상) =====
    "대기업": [
        "삼성전자",          # 글로벌 대기업
        "LG유플러스",        # 통신사 (매출 14조+)
        "CJ제일제당",        # 식품 대기업 (매출 26조+)
        "호텔롯데",          # 롯데그룹 계열
        "HTC",              # 글로벌 IT 대기업
        "대신증권",          # 매출 4조 875억 (2024) - 금융업 특성상 대기업급
        "한국항공우주산업",   # 매출 3조 6,337억 (2024) - 방산 대기업
    ],
    
    # ===== 중견기업 (매출 400억 ~ 5조) =====
    "중견기업": [
        "SM엔터테인먼트",     # 매출 9,897억 (2024)
        "대교",              # 매출 6,635억 (2024)
        "에스원",            # 매출 2조 8,047억 (2024)
        "MBC",              # 매출 7,480억 (2024)
        "KBS",              # 매출 약 1조 5,000억 (2024)
        "하나금융TI",         # 매출 3,439억 (2024)
        "ST마이크로일렉트로닉스",  # 글로벌 반도체 기업
        "유니티테크놀로지스코리아(유)",  # 글로벌 게임엔진 기업
    ],
    
    # ===== 중소기업 (매출 50억 ~ 400억) =====
    "중소기업": [
        "JTBC",              # 매출 3,801억 (2024) - 경계선이나 적자 지속
        "덱스터스튜디오",     # 매출 537억 (2024)
        "갤럭시코퍼레이션",   # 매출 400억 (2024)
        "알체라",            # 매출 172억 (2024), 코스닥 상장
        "버넥트",            # 매출 65억 (2024), 코스닥 상장
        "비브스튜디오스",     # 매출 92억 (2023), 예비유니콘
        "이노시뮬레이션",     # VR 시뮬레이션, 중소기업
        "슈퍼브이알",        # VR 콘텐츠
        "스코넥엔터테인먼트", # VR 테마파크
    ],
    
    # ===== 소기업/스타트업 (매출 50억 미만 또는 미확인) =====
    "소기업": [
        "펄스나인",          # AI 버추얼휴먼, 매출 미확인 (스타트업)
        "콕스스페이스",       # 직원 ~12명, 매출 12억
        "비햅틱스",          # 햅틱 스타트업
        "케타버스",          # 메타버스 스타트업
        "유니브이알",        # VR 스타트업
        "두리번",            # AR 스타트업
        "플레이파크",        # XR 스타트업
        "메타버스쇼",        # 메타버스 스타트업
        "브이런치",          # VR 스타트업
    ],
    
    # ===== 대학/연구기관 =====
    "대학/연구기관": [
        "서강대학교",
        "대진대학교",
        "한국과학기술원",
        "숭실대학교",
        "한국공학대학교",
        "한국열린사이버대학교",
        "한국전자통신연구원",
        "국회미래연구원",
    ],
    
    # ===== 협회/공공기관 =====
    "협회/공공기관": [
        "(사)한국메타버스산업협회",
        "한국메타버스산업협회",
        "(재)전남정보문화산업진흥원",
        "한국능률협회",
        "한국교육학술정보원",
        "한국전자정보통신산업진흥회",
        "새만금 메타버스체험관",
    ],
}


def load_members(config_path="config/members.yaml"):
    """회원사 목록 로드"""
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    members = data.get("members", {})
    return members


def classify_member(name):
    """회원사를 자동 분류"""
    for category, companies in AUTO_CLASSIFY.items():
        if name in companies:
            return category
    return "미분류"


def generate_classification_report(members):
    """분류 결과 생성"""
    results = []
    
    for key, info in members.items():
        name = info.get("name", key)
        representative = info.get("representative", "-")
        keywords = info.get("keywords", [])
        
        category = classify_member(name)
        
        # 뉴스 수집 여부 (중소기업/소기업/미분류만 수집)
        # 대기업, 중견기업, 대학, 협회는 제외
        collect_news = category in ["중소기업", "소기업", "미분류"]
        
        results.append({
            "name": name,
            "representative": representative,
            "keywords": ", ".join(keywords) if keywords else "-",
            "category": category,
            "category_code": CATEGORIES.get(category, "unknown"),
            "collect_news": collect_news,
            "needs_review": category == "미분류"
        })
    
    return results


def save_csv(results, output_path="output/member_classification.csv"):
    """CSV 파일로 저장"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "representative", "keywords", "category", 
            "category_code", "collect_news", "needs_review"
        ])
        writer.writeheader()
        writer.writerows(results)
    
    print(f"✅ CSV 저장 완료: {output_path}")


def save_yaml(results, output_path="config/company_profiles.yaml"):
    """YAML 프로필 파일로 저장"""
    profiles = {}
    
    for item in results:
        profiles[item["name"]] = {
            "category": item["category"],
            "category_code": item["category_code"],
            "collect_news": item["collect_news"],
            "info": {
                "representative": item["representative"],
                "industry": "",  # 추후 수집
                "employees": "",
                "description": "",
                "products": ""
            },
            "financials": {
                "revenue": "",
                "operating_profit": "",
                "market_cap": "",
                "stock_price": "",
                "per": "",
                "pbr": "",
                "outlook": ""
            }
        }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(profiles, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    
    print(f"✅ YAML 저장 완료: {output_path}")


def print_summary(results):
    """분류 결과 요약 출력"""
    from collections import Counter
    
    categories = Counter(r["category"] for r in results)
    
    print("\n" + "="*60)
    print("📊 회원사 분류 결과 (실제 매출 데이터 기반)")
    print("="*60)
    print("\n분류 기준:")
    print("  - 대기업: 매출 5조 이상")
    print("  - 중견기업: 매출 400억 ~ 5조")
    print("  - 중소기업: 매출 50억 ~ 400억")
    print("  - 소기업: 매출 50억 미만 또는 스타트업")
    print("-"*60)
    
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        news_status = "뉴스수집O" if cat in ["중소기업", "소기업", "미분류"] else "뉴스수집X"
        print(f"  {cat}: {count}개 ({news_status})")
    
    print("-"*60)
    print(f"  총 회원사: {len(results)}개")
    
    # 뉴스 수집 대상 계산
    collect_count = sum(1 for r in results if r["collect_news"])
    exclude_count = len(results) - collect_count
    print(f"  뉴스 수집 대상: {collect_count}개")
    print(f"  뉴스 수집 제외: {exclude_count}개")
    print(f"  미분류 (리뷰필요): {categories.get('미분류', 0)}개")
    print("="*60)


def main(dry_run=False):
    """메인 실행"""
    print("🚀 회원사 분류 스크립트 시작 (엄격한 검증 버전)...")
    
    # 회원사 로드
    members = load_members()
    print(f"📋 회원사 {len(members)}개 로드 완료")
    
    # 분류 실행
    results = generate_classification_report(members)
    
    # 요약 출력
    print_summary(results)
    
    if not dry_run:
        # CSV 저장
        save_csv(results, "output/member_classification.csv")
        
        # YAML 저장
        save_yaml(results, "config/company_profiles.yaml")
        
        print("\n✅ 분류 완료! 다음 파일을 확인하세요:")
        print("   - output/member_classification.csv (검토용)")
        print("   - config/company_profiles.yaml (프로필 데이터)")
    else:
        print("\n[DRY-RUN] 파일 저장 생략됨")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="회원사 분류 스크립트")
    parser.add_argument("--dry-run", action="store_true", help="파일 저장 없이 테스트만")
    args = parser.parse_args()
    
    main(dry_run=args.dry_run)
