# CLAUDE.md — 판례 자동 알림 시스템 개발 지침

## 프로젝트 한 줄 요약

법제처 Open API로 한국 법원 판례를 수집·AI 요약·Gmail 발송하는 Python 자동화 시스템.
GitHub Actions에서 매일 07:00 / 15:00 KST 자동 실행.

---

## 모듈 지도 (수정 전 반드시 확인)

| 파일 | 단일 책임 | 수정 시 연관 파일 |
|------|-----------|-----------------|
| `main.py` | 파이프라인 조율 + 우선순위 분류 | 없음 (진입점) |
| `crawler.py` | 법제처 API 호출 + 결과 정규화 | `main.py` (데이터 구조 의존) |
| `summarizer.py` | Gemini AI 요약 + 속도 제한 처리 | `main.py` (case dict 수정) |
| `emailer.py` | HTML/텍스트 이메일 + 첨부파일 발송 | `excel_export.py` (첨부용 바이트) |
| `excel_export.py` | openpyxl .xlsx 생성 | `db.py` (컬럼 구조 공유) |
| `db.py` | SQLite CRUD | `excel_export.py`, `main.py` |
| `config.json` | 런타임 파라미터 | `crawler.py` (설정 소비) |
| `sent_cases.json` | 발송 완료 ID 목록 (중복 방지) | `main.py` (읽기/쓰기) |

---

## 핵심 데이터 흐름

```
config.json
    │
    ▼
crawler.py ──────────────────→ 법제처 API (HTTPS)
    │ List[dict]
    ▼
main.py: 중복 제거 (sent_cases.json 비교)
    │ new_cases
    ▼
main.py: 우선순위 정렬 (PRIORITY_LAWS 집합 × statutes 매칭)
    │ sorted_cases
    ▼
summarizer.py ───────────────→ Gemini API (선택, 5초 간격)
    │ enriched_cases
    ▼
emailer.py ──────────────────→ Gmail SMTP :465 (SSL)
    │       └── excel_export.py → .xlsx 첨부
    ▼
db.py → cases_db.sqlite (영구 이력)
main.py → sent_cases.json 업데이트
GitHub Actions → 자동 커밋 [skip ci]
```

---

## 환경 변수 (GitHub Secrets → 로컬은 export)

```
LAW_API_KEY          # 법제처 Open API (필수)
GMAIL_SENDER         # 발신 Gmail 주소 (필수)
GMAIL_APP_PASSWORD   # 16자리 앱 비밀번호, 공백 포함 가능 (필수)
RECIPIENT_EMAILS     # 쉼표 구분 수신자 목록 (필수)
GEMINI_API_KEY       # Google Gemini 2.0 Flash (선택 — 없으면 AI 요약 생략)
```

---

## DB 스키마 (`cases_db.sqlite` > `sent_cases`)

```sql
id            INTEGER PRIMARY KEY AUTOINCREMENT
sent_date     TEXT     -- YYYY-MM-DD (발송 기준, query_cases 범위 키)
seq           TEXT     -- 판례일련번호 (중복 제거 1순위)
title         TEXT     -- 사건명
case_num      TEXT     -- 사건번호 (중복 제거 2순위: seq 없을 때)
court         TEXT     -- 법원명
case_type     TEXT     -- 사건종류명
decision_date TEXT     -- 선고일 YYYY.MM.DD
ai_summary    TEXT     -- Gemini 요약 (없으면 NULL)
statutes      TEXT     -- 참조조문 (우선순위 매칭에 사용됨)
link          TEXT     -- law.go.kr 원문 URL
is_priority   INTEGER  -- 1=우선순위 법령 매칭, 0=일반
is_fresh      INTEGER  -- 1=선고일 ≤ 30일, 0=그 이전
```

**주의**: `query_cases()`는 `sent_date` 기준 조회 (선고일 기준 아님).
`save_cases()`는 중복 방지 없이 누적 삽입 — 동일 케이스 재발송 시 레코드 중복 가능.

---

## 자주 수정되는 영역별 가이드

### 우선순위 법령 추가/제거
→ `main.py` 상단 `PRIORITY_LAWS` frozenset에 법령명 문자열 추가
→ `statutes` 필드에 부분 문자열 매칭(`any(law in statutes for law in PRIORITY_LAWS)`)

### 검색 조건 변경
→ `config.json`만 수정 (코드 변경 불필요)

### 이메일 HTML 레이아웃 변경
→ `emailer.py` `_build_html_body()` 함수만 읽기

### 엑셀 컬럼/스타일 변경
→ `excel_export.py` 전체 (108줄, 빠르게 읽기 가능)

### AI 요약 프롬프트 변경
→ `summarizer.py` 내 `PROMPT` 상수만 수정

### 발송 스케줄 변경
→ `.github/workflows/schedule.yml` cron 표현식 (UTC 기준)
   - 현재: `0 22 * * *` (07:00 KST), `0 6 * * *` (15:00 KST)

---

## 토큰 절감 원칙

### 읽기 최소화
- 수정 범위를 먼저 좁힌 뒤 해당 함수/섹션만 읽기
- `sent_cases.json` → 내용은 ID 배열, 스키마 이해 후 재읽기 불필요
- `cases_db.sqlite` → 바이너리, DB 스키마(위 참조)로 충분
- `.github/workflows/` → CI 흐름 파악 후 재읽기 불필요

### 검색 도구 우선순위
1. 특정 심볼 → **Grep** (빠름)
2. 파일명 패턴 → **Glob**
3. 광범위 탐색 → **Agent(Explore)** (느리지만 종합적)

### 수정 시 금지 패턴
- 새 파일 생성 금지 (기존 파일 편집 우선)
- 사용되지 않는 코드/주석 추가 금지
- `beautifulsoup4`, `lxml`은 현재 미사용 — 제거 검토 대상

---

## API 외부 한도

| API | 한도 | 초과 시 동작 |
|-----|------|------------|
| 법제처 Open API | 무료 (등록 필요), 페이지당 20건 | HTTP 오류 → 재시도 3회 |
| Gemini 2.0 Flash | 15 req/min / 1,500 req/day | 429 → 60s/120s 대기 후 중단 |
| Gmail SMTP | 일 500건 (무료 계정) | SMTP 오류 → 예외 발생 |

---

## 실행 진입점

```bash
python main.py             # 실제 발송 + DB 저장 + sent_cases.json 갱신
python main.py --dry-run   # 미리보기만 (발송·저장 없음, 안전)
```

---

## GitHub Actions 동작 요약

**`schedule.yml`**:
- 트리거: cron 2회/일 + 수동(dry_run 옵션)
- 실행 후: `sent_cases.json`, `cases_db.sqlite` 변경 시 자동 커밋
- 커밋 태그: `[skip ci]` (재귀 방지)
- 타임아웃: 20분

**`export_excel.yml`**:
- 트리거: 수동 (start_date / end_date 입력)
- 결과: .xlsx 아티팩트 (30일 보관)
- 권한: `contents: read` (쓰기 없음)

---

## 주의사항 요약

- `sent_cases.json`과 `cases_db.sqlite`는 함께 갱신 — 둘 중 하나만 수정하면 불일치
- Gemini 없어도 이메일 발송 정상 동작 (AI 요약 칸만 비움)
- Excel 첨부 실패해도 이메일은 발송됨 (graceful degradation)
- 중복 제거: `seq` 우선, 없으면 `case_num` 사용
