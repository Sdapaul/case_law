"""
판례 자동 알림 프로그램
  - 법제처 오픈 API로 최신 판례 조회
  - 이미 발송한 사건번호는 sent_cases.json 에 기록해 중복 발송 방지
  - 새 판례만 Gmail로 발송

사용법:
  python main.py              # 실제 실행 (이메일 발송)
  python main.py --dry-run    # 이메일 발송 없이 결과만 출력

환경변수 (GitHub Secrets):
  LAW_API_KEY         법제처 오픈 API 키
  GMAIL_SENDER        발신 Gmail 주소
  GMAIL_APP_PASSWORD  발신 계정의 Gmail 앱 비밀번호
  RECIPIENT_EMAILS    수신자 이메일 (쉼표로 여러 개 가능)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from crawler import search_cases
from emailer import send_case_email
from summarizer import add_ai_summaries

PRIORITY_LAWS = {
    "금융회사의 지배구조에 관한 법률",
    "상법",
    "형법",
    "개인금융채권의 관리 및 개인금융채무자의 보호에 관한 법률",
    "공중 등 협박목적 및 대량살상무기확산을 위한 자금조달행위의 금지에 관한 법률",
    "금융거래지표의 관리에 관한 법률",
    "금융산업의 구조개선에 관한 법률",
    "금융소비자 보호에 관한 법률",
    "금융위원회의 설치 등에 관한 법률",
    "금융혁신지원 특별법",
    "기업구조조정 촉진법",
    "기업구조조정투자회사법",
    "대부업 등의 등록 및 금융이용자 보호에 관한 법률",
    "보험사기방지 특별법",
    "보험업법",
    "감정평가 및 감정평가사에 관한 법률",
    "서민의 금융생활 지원에 관한 법률",
    "신용정보의 이용 및 보호에 관한 법률",
    "예금자보호법",
    "외국인투자 촉진법",
    "외국환거래법",
    "자본시장과 금융투자업에 관한 법률",
    "전자금융거래법",
    "주식ㆍ사채 등의 전자등록에 관한 법률",
    "주식회사 등의 외부감사에 관한 법률",
    "채권의 공정한 추심에 관한 법률",
    "특정 금융거래정보의 보고 및 이용 등에 관한 법률",
    "한국주택금융공사법",
    "개인정보 보호법",
    "공익신고자 보호법",
    "독점규제 및 공정거래에 관한 법률",
    "마약류 불법거래 방지에 관한 특례법",
    "범죄수익은닉의 규제 및 처벌 등에 관한 법률",
    "약관의 규제에 관한 법률",
    "전기통신금융사기 피해 방지 및 피해금 환급에 관한 특별법",
    "특정경제범죄 가중처벌 등에 관한 법률",
    "근로자퇴직급여 보장법",
    "금융지주회사법",
    "산업안전보건법",
    "유사수신행위의 규제에 관한 법률",
    "인공지능 발전과 신뢰 기반 조성 등에 관한 기본법",
    "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "중대재해 처벌 등에 관한 법률",
}


def _is_priority(case: dict) -> bool:
    """참조조문 또는 사건명에 우선순위 법률이 포함되어 있으면 True"""
    text = (case.get("statutes") or "") + " " + (case.get("title") or "")
    return any(law in text for law in PRIORITY_LAWS)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.json"
SENT_PATH = Path(__file__).parent / "sent_cases.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        logger.error(f"config.json 파일이 없습니다: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_sent() -> set[str]:
    """이미 발송된 사건번호 목록 로드"""
    if not SENT_PATH.exists():
        return set()
    with open(SENT_PATH, encoding="utf-8") as f:
        return set(json.load(f))


def save_sent(sent: set[str]) -> None:
    """발송된 사건번호 목록 저장"""
    with open(SENT_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(sent), f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="판례 자동 알림")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="이메일 발송 없이 결과만 출력",
    )
    args = parser.parse_args()

    config = load_config()
    sent = load_sent()

    logger.info("=== 판례 검색 시작 ===")
    logger.info(f"  키워드  : {config.get('keywords') or '없음'}")
    logger.info(f"  법원    : {config.get('court_name') or '전체'}")
    logger.info(f"  사건유형: {config.get('case_type') or '전체'}")
    logger.info(f"  기발송  : {len(sent)}건 (중복 제외 대상)")

    all_cases = search_cases(config)
    logger.info(f"API 조회 결과: {len(all_cases)}건")

    # 이미 발송한 사건 제외 (seq 우선, 없으면 case_num으로 확인)
    new_cases = [
        c for c in all_cases
        if (c.get("seq") or c.get("case_num", "-")) not in sent
    ]

    # 우선순위 법률 판례 먼저, 각 그룹 내 선고일 최신순
    priority_cases = [c for c in new_cases if _is_priority(c)]
    other_cases = [c for c in new_cases if not _is_priority(c)]
    priority_cases.sort(key=lambda c: c.get("date", "") or "0000.00.00", reverse=True)
    other_cases.sort(key=lambda c: c.get("date", "") or "0000.00.00", reverse=True)

    for c in priority_cases:
        c["priority"] = True
    for c in other_cases:
        c["priority"] = False

    new_cases = priority_cases + other_cases
    logger.info(f"새 판례: {len(new_cases)}건")

    if not new_cases:
        logger.info("새 판례가 없습니다. 이메일을 발송하지 않습니다.")
        return

    add_ai_summaries(new_cases)

    if args.dry_run:
        logger.info("=== [DRY-RUN] 새 판례 목록 ===")
        for i, c in enumerate(new_cases, 1):
            print(
                f"{i}. [{c.get('date','-')}] {c.get('title','-')}"
                f" | {c.get('case_num','-')} | {c.get('court','-')}"
            )
            if c.get("summary"):
                print(f"   요약: {c['summary'][:100]}...")
        return

    send_case_email(new_cases, config)

    # 발송 완료 후 고유 ID 기록 (seq 우선, 없으면 case_num)
    for c in new_cases:
        uid = c.get("seq") or c.get("case_num")
        if uid and uid != "-":
            sent.add(uid)
    save_sent(sent)
    logger.info(f"sent_cases.json 업데이트 완료 (누적 {len(sent)}건)")


if __name__ == "__main__":
    main()
