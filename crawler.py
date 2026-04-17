"""
법제처 국가법령정보 오픈 API - 판례 검색
API 키 발급: https://open.law.go.kr/lspo/main.do (무료)
"""

import os
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

        try:
            resp = requests.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error(f"API 오류 (페이지 {page}): {exc}")
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
    date_str = raw.get("선고일자", "")
    if len(date_str) == 8:
        date_str = f"{date_str[:4]}.{date_str[4:6]}.{date_str[6:]}"

    seq = raw.get("판례일련번호", "")
    link = (
        f"https://www.law.go.kr/precInfoP.do?mode=0&precSeq={seq}" if seq else ""
    )

    summary = raw.get("판시사항", "") or raw.get("판결요지", "") or ""

    return {
        "title": raw.get("사건명", "-"),
        "case_num": raw.get("사건번호", "-"),
        "court": raw.get("법원명", "-"),
        "case_type": raw.get("사건종류명", ""),
        "date": date_str,
        "summary": summary[:500],
        "link": link,
    }
