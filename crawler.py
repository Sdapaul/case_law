import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

SEARCH_URL = "https://glaw.scourt.go.kr/wsjo/panre/sjo150.do"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Referer": "https://glaw.scourt.go.kr/",
}

COURT_NAMES = [
    "대법원", "헌법재판소", "고등법원", "지방법원",
    "가정법원", "행정법원", "특허법원", "회생법원",
]

CASE_NUM_PATTERN = re.compile(r"\d{4}[가나다라마바사아자차카타파하도보고누두모코루수]+\d+")
DATE_PATTERN = re.compile(r"\d{4}[.\-]\d{2}[.\-]\d{2}")


def search_new_cases(config: dict) -> list[dict]:
    keywords: list = config.get("keywords", [])
    court_name: str = config.get("court_name", "")
    case_type: str = config.get("case_type", "")
    days_back: int = config.get("days_back", 1)
    max_pages: int = config.get("max_pages", 3)

    today = datetime.now()
    end_dt = today.strftime("%Y.%m.%d")
    start_dt = (today - timedelta(days=days_back)).strftime("%Y.%m.%d")

    query = " ".join(keywords) if keywords else ""

    all_cases: list[dict] = []

    for page in range(1, max_pages + 1):
        logger.info(f"페이지 {page} 크롤링 중...")

        params: dict = {
            "q": query,
            "nPage": str(page),
            "startDt": start_dt,
            "endDt": end_dt,
            "pId": "0",
        }
        if court_name:
            params["courtNm"] = court_name

        try:
            resp = requests.get(
                SEARCH_URL, params=params, headers=HEADERS, timeout=30
            )
            resp.raise_for_status()
            resp.encoding = "utf-8"

            cases = _parse_results(resp.text)

            if not cases:
                logger.info("더 이상 결과가 없습니다.")
                break

            all_cases.extend(cases)
            logger.info(f"페이지 {page}: {len(cases)}건 발견")

            if not _has_next_page(resp.text):
                break

            time.sleep(1.0)

        except requests.RequestException as exc:
            logger.error(f"크롤링 오류 (페이지 {page}): {exc}")
            break

    # case_type 필터: 사건번호나 제목에 포함 여부로 판단
    if case_type:
        all_cases = [
            c for c in all_cases
            if case_type in c.get("case_num", "")
            or case_type in c.get("title", "")
            or case_type in c.get("court", "")
        ]

    # 중복 제거 (사건번호 기준)
    seen: set = set()
    unique_cases: list[dict] = []
    for c in all_cases:
        key = c.get("case_num") or c.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique_cases.append(c)

    return unique_cases


def _parse_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cases: list[dict] = []

    # 대법원 종합법률정보 결과 컨테이너 후보
    container = (
        soup.find("div", id="panre_list")
        or soup.find("div", class_="result_list")
        or soup.find("ul", class_="panre_list")
        or soup.find("div", class_="list_wrap")
        or soup.find("div", class_="search_list")
    )

    if container:
        items = container.find_all(["li", "dl"])
    else:
        # fallback: a 태그를 가진 li 전체
        items = soup.find_all(
            "li",
            class_=lambda x: bool(x) and any(
                kw in x for kw in ("result", "case", "panre", "item")
            ),
        )

    for item in items:
        case = _extract_case(item)
        if case and case.get("title"):
            cases.append(case)

    return cases


def _extract_case(item) -> dict | None:
    case: dict = {}

    # 제목 및 링크
    link_tag = item.find("a")
    if not link_tag:
        return None

    case["title"] = link_tag.get_text(strip=True)
    href = link_tag.get("href", "")
    if href:
        case["link"] = (
            href if href.startswith("http")
            else "https://glaw.scourt.go.kr" + href
        )
    else:
        case["link"] = ""

    # 모든 텍스트 블록에서 메타데이터 추출
    all_text = item.get_text(" ", strip=True)

    # 사건번호
    m = CASE_NUM_PATTERN.search(all_text)
    if m:
        case["case_num"] = m.group()

    # 선고일
    m = DATE_PATTERN.search(all_text)
    if m:
        case["date"] = m.group()

    # 법원명
    for court in COURT_NAMES:
        if court in all_text:
            m = re.search(r"[가-힣]*" + court, all_text)
            case["court"] = m.group() if m else court
            break

    # 요약 / 키워드
    summary_tag = item.find(
        class_=lambda x: bool(x) and any(
            kw in str(x) for kw in ("summary", "keyword", "요약", "주제어")
        )
    )
    if summary_tag:
        case["summary"] = summary_tag.get_text(strip=True)[:200]
    else:
        case["summary"] = ""

    return case


def _has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return bool(
        soup.find("a", class_="next")
        or soup.find("a", string=re.compile("다음"))
        or soup.find("button", string=re.compile("다음"))
    )
