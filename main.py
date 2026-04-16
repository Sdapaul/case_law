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

    # 이미 발송한 사건 제외
    new_cases = [
        c for c in all_cases
        if c.get("case_num", "-") not in sent
    ]

    # 선고일 최신순 정렬 (날짜 없는 항목은 뒤로)
    new_cases.sort(
        key=lambda c: c.get("date", "") or "0000.00.00",
        reverse=True,
    )
    logger.info(f"새 판례: {len(new_cases)}건")

    if not new_cases:
        logger.info("새 판례가 없습니다. 이메일을 발송하지 않습니다.")
        return

    if args.dry_run:
        logger.info("=== [DRY-RUN] 새 판례 목록 ===")
        for i, c in enumerate(new_cases, 1):
            print(
                f"{i}. [{c.get('date','-')}] {c.get('title','-')}"
                f" | {c.get('case_num','-')} | {c.get('court','-')}"
            )
        return

    send_case_email(new_cases, config)

    # 발송 완료 후 사건번호 기록
    sent.update(c["case_num"] for c in new_cases if c.get("case_num"))
    save_sent(sent)
    logger.info(f"sent_cases.json 업데이트 완료 (누적 {len(sent)}건)")


if __name__ == "__main__":
    main()
