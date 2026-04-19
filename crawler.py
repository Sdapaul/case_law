"""
법제처 국가법령정보 오픈 API - 판례 검색
API 키 발급: https://open.law.go.kr/lspo/main.do (무료)
"""

import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

API_URL = "https://www.law.go.kr/DRF/lawSearch.do"


def search_cases(config: dict) -> list[dict]:
    """최신 판례를 가져옴 (날짜 필터 없음 — 중복은 main.py에서 seen_cases로 처리)"""
    api_key = os.environ.get("LAW_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            "환경변수 LAW_API_KEY 가 없습니다. "
            "https://open.law.go.kr 에서 무료 발급 후 GitHub Secrets 에 등록하세요."
        )

    keywords: list = config.get("keywords", [])
    court_name: str = config.get("court_name", "")
    case_type: str = config.get("case_type", "")
    max_pages: int = config.get("max_pages", 3)

    query = " ".join(keywords) if keywords else ""
    all_cases: list[dict] = []

    for page in range(1, max_pages + 1):
        logger.info(f"API 조회 중 (페이지 {page})...")

        params = {
            "OC": api_key,
            "target": "prec",
            "type": "JSON",
            "query": query,
            "display": 20,
            "page": page,
            "sort": "date",  # 최신 선고일 순
        }

        data = None
        for attempt in range(1, 4):  # 최대 3회 재시도
            try:
                resp = requests.get(
                    API_URL,
                    params=params,
                    timeout=30,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36"
                        ),
                        "Accept": "application/json, text/javascript, */*",
                        "Accept-Language": "ko-KR,ko;q=0.9",
                        "Referer": "https://www.law.go.kr/",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as exc:
                logger.warning(f"API 오류 (페이지 {page}, 시도 {attempt}/3): {exc}")
                if attempt < 3:
                    time.sleep(3 * attempt)
        if data is None:
            logger.error(f"페이지 {page} 3회 모두 실패 — 중단")
            break

        raw_list = data.get("PrecSearch", {}).get("prec", [])
        if isinstance(raw_list, dict):
            raw_list = [raw_list]
        if not raw_list:
            logger.info("더 이상 결과가 없습니다.")
            break

        for raw in raw_list:
            if court_name and court_name not in raw.get("법원명", ""):
                continue
            if case_type and case_type not in raw.get("사건종류명", ""):
                continue
            all_cases.append(_normalize(raw))

        if len(raw_list) < 20:
            break

    return all_cases


def _normalize(raw: dict) -> dict:
    date_str = raw.get("선고일자", "") or ""
    if len(date_str) == 8:
        formatted = f"{date_str[:4]}.{date_str[4:6]}.{date_str[6:]}"
        # 0001.01.01 등 무효 날짜 제외
        date_str = formatted if date_str > "19000101" else ""

    seq = raw.get("판례일련번호", "") or ""
    link = (
        f"https://www.law.go.kr/precInfoP.do?mode=0&precSeq={seq}" if seq else ""
    )

    case_num = raw.get("사건번호") or ""
    court = raw.get("법원명") or ""
    summary = raw.get("판시사항", "") or raw.get("판결요지", "") or ""

    return {
        "seq": seq,                        # 판례 고유번호 (중복 방지 키)
        "title": raw.get("사건명") or "-",
        "case_num": case_num or "-",
        "court": court or "-",
        "case_type": raw.get("사건종류명") or "",
        "date": date_str,
        "summary": summary[:500],
        "statutes": raw.get("참조조문") or "",  # 참조 법령 (우선순위 정렬용)
        "link": link,
    }
