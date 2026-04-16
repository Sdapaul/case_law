"""
법제처 국가법령정보 오픈 API - 판례 검색
API 키 발급: https://open.law.go.kr/lspo/main.do (무료)
"""

import os
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

API_URL = "https://www.law.go.kr/DRF/lawSearch.do"


def search_new_cases(config: dict) -> list[dict]:
    api_key = os.environ.get("LAW_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError(
            "환경변수 LAW_API_KEY 가 없습니다. "
            "https://open.law.go.kr 에서 무료 발급 후 GitHub Secrets 에 등록하세요."
        )

    keywords: list = config.get("keywords", [])
    court_name: str = config.get("court_name", "")
    case_type: str = config.get("case_type", "")
    days_back: int = config.get("days_back", 1)
    max_pages: int = config.get("max_pages", 3)

    cutoff = datetime.now() - timedelta(days=days_back)
    query = " ".join(keywords) if keywords else ""

    all_cases: list[dict] = []
    stop = False

    for page in range(1, max_pages + 1):
        if stop:
            break

        logger.info(f"API 조회 중 (페이지 {page})...")

        params = {
            "OC": api_key,
            "target": "prec",
            "type": "JSON",
            "query": query,
            "display": 20,
            "page": page,
            "sort": "date",
        }

        try:
            resp = requests.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error(f"API 오류 (페이지 {page}): {exc}")
            break

        prec_search = data.get("PrecSearch", {})
        raw_list = prec_search.get("prec", [])

        # 단건일 때 dict로 내려오는 경우 처리
        if isinstance(raw_list, dict):
            raw_list = [raw_list]
        if not raw_list:
            logger.info("더 이상 결과가 없습니다.")
            break

        for raw in raw_list:
            case_date = _parse_date(raw.get("선고일자", ""))
            if case_date and case_date < cutoff:
                stop = True  # 날짜순 정렬이므로 이후 결과도 기간 밖
                break

            # 법원 필터
            if court_name and court_name not in raw.get("법원명", ""):
                continue
            # 사건유형 필터
            if case_type and case_type not in raw.get("사건종류명", ""):
                continue

            all_cases.append(_normalize(raw))

        # 페이지당 20건 미만이면 마지막 페이지
        if len(raw_list) < 20:
            break

    logger.info(f"총 {len(all_cases)}건 수집 완료")
    return all_cases


def _parse_date(date_str: str) -> datetime | None:
    """'20240115' → datetime"""
    try:
        return datetime.strptime(date_str.strip(), "%Y%m%d")
    except (ValueError, AttributeError):
        return None


def _normalize(raw: dict) -> dict:
    date_str = raw.get("선고일자", "")
    if len(date_str) == 8:
        date_str = f"{date_str[:4]}.{date_str[4:6]}.{date_str[6:]}"

    seq = raw.get("판례일련번호", "")
    link = (
        f"https://www.law.go.kr/precInfoP.do?mode=0&precSeq={seq}"
        if seq else ""
    )

    summary = raw.get("판시사항", "") or raw.get("판결요지", "") or ""

    return {
        "title": raw.get("사건명", "-"),
        "case_num": raw.get("사건번호", "-"),
        "court": raw.get("법원명", "-"),
        "case_type": raw.get("사건종류명", ""),
        "date": date_str,
        "summary": summary[:200],
        "link": link,
    }
