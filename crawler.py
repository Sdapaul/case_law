"""
법제처 국가법령정보 오픈 API - 판례 검색
API 키 발급: https://open.law.go.kr/lspo/main.do (무료)
"""

import os
import time
import logging
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)

FRESH_DAYS = 30  # 선고일 기준 이 일수 이내면 최신 판례로 표시

API_URL = "https://www.law.go.kr/DRF/lawSearch.do"


def search_cases(config: dict) -> list[dict]:
    """최신 판례를 가져옴 (선고일 기준 days_back 이내만 포함)"""
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
    days_back: int = config.get("days_back", 30)
    cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y.%m.%d")

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
            case = _normalize(raw)
            if case["date"] and case["date"] < cutoff:
                continue  # 오래된 항목은 건너뜀 (조기 종료 없이 계속 스캔)
            all_cases.append(case)

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

    is_fresh = _check_freshness(date_str)

    return {
        "seq": seq,                        # 판례 고유번호 (중복 방지 키)
        "title": raw.get("사건명") or "-",
        "case_num": case_num or "-",
        "court": court or "-",
        "case_type": raw.get("사건종류명") or "",
        "date": date_str,
        "content": summary[:300],          # 원문 판시사항/판결요지 미리보기 (이메일 표시용)
        "summary": summary[:500],          # summarizer.py가 AI 요약으로 덮어씀
        "statutes": raw.get("참조조문") or "",  # 참조 법령 (우선순위 정렬용)
        "link": link,
        "is_fresh": is_fresh,
    }


def _check_freshness(date_str: str) -> bool:
    """선고일이 FRESH_DAYS 이내면 True (최신 판례)"""
    if not date_str:
        return False
    try:
        decision_date = datetime.strptime(date_str, "%Y.%m.%d")
        return (datetime.now() - decision_date).days <= FRESH_DAYS
    except ValueError:
        return False


_DETAIL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.law.go.kr/",
}


def enrich_with_detail(cases: list[dict]) -> None:
    """목록 API에서 판시사항/판결요지가 비어있는 판례를 상세 API로 보완."""
    api_key = os.environ.get("LAW_API_KEY", "").strip()
    if not api_key:
        return
    targets = [c for c in cases if not c.get("content") and c.get("seq")]
    if not targets:
        return
    logger.info(f"판시사항 상세 조회 중 ({len(targets)}건)...")
    for case in targets:
        seq = case["seq"]
        try:
            resp = requests.get(
                "https://www.law.go.kr/DRF/lawService.do",
                params={"OC": api_key, "target": "prec", "ID": seq, "type": "JSON"},
                timeout=15,
                headers=_DETAIL_HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
            content = ""
            for top_key in ("PrecService", "법령", "prec"):
                node = data.get(top_key, {})
                if not isinstance(node, dict):
                    continue
                for field in ("판시사항", "판결요지", "판례내용"):
                    val = (node.get(field) or "").strip()
                    if val:
                        content = val
                        break
                if content:
                    break
            if content:
                case["content"] = content[:300]
                if not case.get("summary"):
                    case["summary"] = content[:500]
        except Exception as exc:
            logger.debug(f"상세 API 실패 (seq={seq}): {exc}")
        time.sleep(0.5)
