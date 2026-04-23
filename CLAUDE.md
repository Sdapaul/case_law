# CLAUDE.md — 판례 자동 알림 프로젝트

## 프로젝트 목적

법제처 API에서 최신 판례를 자동으로 수집·분류·요약하여 이메일로 발송하는 Python 자동화 시스템.
GitHub Actions로 매일 2회(오전 7시, 오후 3시 KST) 실행.

---

## 파일 구조

```
main.py          → 오케스트레이터 (진입점)
crawler.py       → 법제처 API 크롤링
summarizer.py    → Google Gemini AI 요약
emailer.py       → Gmail SMTP 이메일 발송
excel_export.py  → .xlsx 파일 생성 (openpyxl)
db.py            → SQLite 저장 (cases_db.sqlite)
config.json      → 런타임 설정 (keywords, days_back 등)
sent_cases.json  → 발송 완료 케이스 ID 목록 (중복 방지)
.github/workflows/schedule.yml     → 정기 발송 워크플로
.github/workflows/export_excel.yml → 엑셀 내보내기 워크플로
```

---

## 환경 변수 (GitHub Secrets)

| 변수명 | 용도 | 필수 |
|--------|------|------|
| `LAW_API_KEY` | 법제처 Open API 인증키 | 필수 |
| `GMAIL_SENDER` | 발신 Gmail 주소 | 필수 |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 (16자리) | 필수 |
| `RECIPIENT_EMAILS` | 수신자 이메일 (쉼표 구분) | 필수 |
| `GEMINI_API_KEY` | Google Gemini AI 키 | 선택 |

---

## DB 스키마 (`cases_db.sqlite`)

테이블: `sent_cases`
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
sent_date TEXT        -- 발송일 (YYYY-MM-DD)
seq TEXT              -- API 고유 ID
title TEXT            -- 판례명
case_num TEXT         -- 사건번호
court TEXT            -- 법원명
case_type TEXT        -- 사건유형
decision_date TEXT    -- 선고일 (YYYY.MM.DD)
ai_summary TEXT       -- AI 요약문
statutes TEXT         -- 참조 법령
link TEXT             -- 원문 링크
is_priority INTEGER   -- 우선순위 여부 (1/0)
is_fresh INTEGER      -- 최신 판례 여부 (1/0)
```

---

## 데이터 흐름

```
main.py
  ├─ crawler.py → 법제처 API (LAW_API_KEY)
  ├─ 중복 필터 (sent_cases.json)
  ├─ 우선순위 분류 (44개 법령 목록)
  ├─ summarizer.py → Gemini API (선택)
  ├─ emailer.py → Gmail SMTP
  └─ db.py → cases_db.sqlite 저장
```

---

## 토큰 최소화 지침

### 컨텍스트 전달 원칙
- 수정 작업 시 **해당 파일만** 읽어서 제공 (전체 코드베이스 불필요)
- 버그 수정 시 오류 메시지 + 관련 함수만 붙여넣기
- "전체 파일 다시 써줘" 대신 "X 함수의 Y 부분만 수정" 방식 선호

### 파일별 독립성
각 파일은 단일 책임. 수정 범위:
- 크롤링 변경 → `crawler.py`만
- 이메일 양식 변경 → `emailer.py`만
- AI 요약 변경 → `summarizer.py`만
- DB 쿼리 변경 → `db.py`만

### 자주 수정되는 설정값
코드 변경 없이 `config.json`으로 제어 가능:
- `days_back`: 판례 검색 기간 (일)
- `max_pages`: API 페이지 수 (1페이지=20건)
- `keywords`: 검색 키워드 배열
- `court_name`, `case_type`: 필터

### 금지 패턴
- 새 파일 생성 금지 (기존 파일 편집 우선)
- 사용되지 않는 코드 추가 금지
- 주석 남용 금지 (명백한 코드에 주석 불필요)
- `beautifulsoup4`, `lxml`은 현재 미사용 — 제거 검토 가능

---

## 외부 API 제한

| API | 제한 | 비고 |
|-----|------|------|
| 법제처 | 무료 (등록 필요) | 페이지당 20건 |
| Gemini 2.0 Flash | 15 req/min, 1,500/day | 429시 60초 대기 |
| Gmail SMTP | 하루 500건 | 앱 비밀번호 필요 |

---

## 실행 방법

```bash
# 실제 발송
python main.py

# 테스트 (이메일 발송 안 함)
python main.py --dry-run
```

---

## 주의사항

- `sent_cases.json`과 `cases_db.sqlite`는 GitHub Actions가 자동 커밋 (`[skip ci]` 태그 포함)
- Gemini API 없어도 동작 (요약 생략)
- 중복 방지는 `seq` 우선, 없으면 `case_num` 사용
- `is_priority`와 `is_fresh` 플래그는 이메일 시각적 구분에 사용됨
