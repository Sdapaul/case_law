"""
판례 자동 알림 프로그램
  - 대법원 종합법률정보(glaw.scourt.go.kr) 크롤링
  - 조건에 맞는 새 판례를 Gmail로 발송

사용법:
  python main.py              # 실제 실행 (이메일 발송)
  python main.py --dry-run    # 이메일 발송 없이 결과 출력만

환경변수 (GitHub Secrets 에 등록):
  GMAIL_SENDER        발신 Gmail 주소
  GMAIL_APP_PASSWORD  발신 계정의 Gmail 앱 비밀번호
  RECIPIENT_EMAILS    수신자 이메일 (쉼표로 여러 개 가능)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from crawler import search_new_cases
from emailer import send_case_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        logger.error(f"config.json 파일이 없습니다: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="판례 자동 알림")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="이메일 발송 없이 결과만 출력",
    )
    args = parser.parse_args()

    config = load_config()

    logger.info("=== 판례 검색 시작 ===")
    logger.info(f"  키워드  : {config.get('keywords') or '없음'}")
    logger.info(f"  법원    : {config.get('court_name') or '전체'}")
    logger.info(f"  사건유형: {config.get('case_type') or '전체'}")
    logger.info(f"  검색기간: 최근 {config.get('days_back', 1)}일")

    cases = search_new_cases(config)

    if not cases:
        logger.info("조건에 맞는 새 판례가 없습니다. 이메일을 발송하지 않습니다.")
        return

    logger.info(f"총 {len(cases)}건의 판례를 발견했습니다.")

    if args.dry_run:
        logger.info("=== [DRY-RUN] 발견된 판례 ===")
        for i, c in enumerate(cases, 1):
            print(
                f"{i}. {c.get('title', '-')}"
                f" | {c.get('case_num', '-')}"
                f" | {c.get('court', '-')}"
                f" | {c.get('date', '-')}"
            )
    else:
        send_case_email(cases, config)


if __name__ == "__main__":
    main()
