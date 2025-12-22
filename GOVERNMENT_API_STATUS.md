# 정부과제 및 나라장터 연동 상태 보고서

**테스트 일시**: 2025-12-19 10:45:33  
**테스트 결과**: 부분 정상

---

## 📊 전체 상태 요약

| 항목 | 상태 | 세부사항 |
|------|------|----------|
| **과기정통부 API** | ✅ **정상** | 10건의 공고 수집 성공 |
| **나 라장터 API** | ⚠️ **장애** | HTTP 500 오류 발생 |
| **통합 수집** | ✅ **정상** | 과기정통부 데이터로 동작 중 |

---

## 1. 과기정통부(MSIT) 사업공고 API

### ✅ 상태: 정상 동작

- **API 엔드포인트**: 
  - `http://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList`
- **수집 결과**: 10건
- **최신 공고 예시**:
  1. 2026년도『공공기술기반 시장연계 창업탐색 지원사업』시행 공고 (2025-12-18)
  2. 「 K-문샷 프로젝트 대국민 공모전 」 공고 (2025-12-16)
  3. 정보보호제품 성능평가기관 신규 및 재지정에 관한 공고 (2025-12-15)
  4. 2026년「ICT 학점연계 프로젝트 인턴십」사업 공고 (2025-12-11)
  5. 2026년도 양자정보과학 인적기반조성사업 양자정보연구지원센터 공모 (2025-12-08)

### 📌 코드 위치
- 파일: `src/fetchers/gov.py`
- 함수: `fetch_msit_announcements()`

---

## 2. 나라장터(KONEPS) 입찰공고 API

### ⚠️ 상태: 서비스 오류

- **API 엔드포인트** (시도한 버전들):
  - v04: `http://apis.data.go.kr/1230000/BidPublicInfoService04/getBidPblancListInfoServcPPSSrch`
  - v03: `http://apis.data.go.kr/1230000/BidPublicInfoService03/getBidPblancListInfoServcPPSSrch`
  - v02: `http://apis.data.go.kr/1230000/BidPublicInfoService02/getBidPblancListInfoServcPPSSrch`

- **오류 내용**: 모든 API 버전에서 **HTTP 500 (Internal Server Error)** 반환
- **검색 조건**:
  - 키워드: 인공지능, AI, 메타버스, XR, 가상현실, 증강현실, 디지털트윈
  - 검색 기간: 최근 2일 (기본) / 7일 (확장 테스트)

### 🔍 오류 원인 분석

1. **API 서비스 장애** (가장 유력)
   - 조달청 API 서버의 일시적 장애
   - 서비스 점검 중일 가능성

2. **API 키 승인 문제**
   - data.go.kr에서 'BidPublicInfoService' 서비스 미승인
   - API 키 유효기간 만료

3. **API 버전 변경**
   - 조달청에서 새로운 API 버전으로 전환
   - 기존 API 엔드포인트 폐기

### 📌 코드 위치
- 파일: `src/fetchers/gov.py`
- 함수: `fetch_koneps_announcements()`

---

## 3. 통합 정부과제 수집

### ✅ 상태: 정상 동작 (과기정통부 데이터 기반)

- **함수**: `fetch_gov_announcements()`
- **수집 결과**: 10건 (모두 과기정통부)
- **출처별 통계**:
  - 과기정통부: 10건
  - 나라장터: 0건 (API 오류로 수집 불가)

---

## 🔧 권장 조치사항

### 즉시 조치

1. **data.go.kr 계정 확인**
   - 로그인: https://www.data.go.kr/
   - 마이페이지 → 활용신청 현황 확인
   - 'BidPublicInfoService' 서비스 승인 상태 확인

2. **API 키 갱신 확인**
   - 현재 사용 중인 API 키: `b333fbc99c...`
   - 유효기간 및 사용량 제한 확인

### 중기 조치

3. **나라장터 API 대안 탐색**
   - 조달청 공식 API 문서 재확인
   - 새로운 API 버전 또는 엔드포인트 탐색
   - KONEPS 웹사이트 크롤링 고려 (최후수단)

4. **오류 처리 개선**
   - API 호출 실패 시 재시도 로직 강화
   - 오류 로그 상세화
   - 모니터링 알림 설정

### 장기 조치

5. **다양한 정부과제 소스 추가**
   - NTIS (국가과학기술정보서비스)
   - IRIS (범부처통합연구지원시스템)
   - 각 부처별 공고 API

---

## 📝 테스트 파일

생성된 테스트 스크립트:

1. **`test_gov_status.py`** - 통합 상태 확인 스크립트
   - 과기정통부, 나라장터, 통합 수집 모두 테스트
   - 실행: `python3 test_gov_status.py`

2. **`test_koneps_extended.py`** - 나라장터 상세 테스트
   - 검색 기간 확장 가능
   - API 버전별 상세 오류 확인
   - 실행: `python3 test_koneps_extended.py`

3. **기존 파일**:
   - `test_koneps_check.py`
   - `test_koneps_debug.py`
   - `test_koneps_debug_v2.py`

---

## 💡 결론

**현재 정부과제 연동 시스템은 부분적으로 정상 동작 중입니다.**

- ✅ 과기정통부 API가 정상 작동하여 정부 R&D 과제 공고를 수집하고 있습니다.
- ⚠️ 나라장터 API는 서비스 오류(HTTP 500)로 인해 현재 작동하지 않습니다.
- ✅ 통합 수집 기능은 정상 동작하며, 최소 1개 이상의 소스에서 데이터를 수집하고 있습니다.

**서비스는 정상적으로 운영 가능하나, 나라장터 API 복구를 위한 조치가 필요합니다.**

---

## 📞 문의

- data.go.kr 고객센터: https://www.data.go.kr/tcs/css/selCssInfo.do
- 조달청 나라장터: https://www.g2b.go.kr/
