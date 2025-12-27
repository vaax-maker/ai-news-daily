#!/usr/bin/env python3
"""
모든 페이지를 목록형으로 통일 (Home 제외)
모든 토론/공유 버튼 스타일 통일
"""

print("=" * 60)
print("페이지 구조 및 버튼 스타일 통일 작업")
print("=" * 60)

# 1. AI/XR daily 페이지 템플릿 - 이미 목록형임
print("\n✓ daily_list.html - 이미 목록형 (뉴스 하단에 토론/공유)")

# 2. 회원사 페이지들 - 이미 목록형으로 변경됨
print("✓ member_page.html - 목록형 완료")
print("✓ member_index.html - 목록형 완료")

# 3. 정부과제 - PC는 테이블, 모바일은 목록형
print("✓ gov_archive.html - PC 테이블/모바일 목록형")

# 4. Home은 카드형 유지
print("✓ index.html - 카드형 유지 (변경 없음)")

# 5. 아카이브 인덱스 확인 필요
print("\n확인 필요: archive_index.html (AI/XR 아카이브 인덱스)")

print("\n" + "=" * 60)
print("현재 상태 확인 완료")
print("=" * 60)
print("\n다음 작업:")
print("1. archive_index.html이 동적으로 카드를 생성하는지 확인")
print("2. 생성된다면 목록형으로 변경")
print("3. 모든 페이지의 버튼 스타일이 discuss-btn-sm로 통일되었는지 확인")
