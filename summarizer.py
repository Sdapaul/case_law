"""
Gemini 2.0 Flash (무료 tier) 로 판시사항을 쉬운 한국어로 요약.
GEMINI_API_KEY 환경변수가 없으면 AI 요약을 건너뜀.

무료 한도: 분당 15회 / 일 1,500회
"""

import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/gemini-2.0-flash:generateContent"
)
MAX_CASES  = 20    # 무료 tier 안전 상한 (일일 한도 여유 확보)
DELAY_SEC  = 5.0   # 15 RPM → 4s 간격 + 여유분
# 429 발생 시 대기 시간 (초): 첫 번째 60s, 두 번째 120s
_BACKOFF   = [60, 120]


def add_ai_summaries(cases: list[dict]) -> None:
    """판례 목록에 AI 요약을 in-place로 추가. GEMINI_API_KEY 없으면 no-op."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("GEMINI_API_KEY 없음 — AI 요약을 건너뜁니다.")
        return

    targets = cases[:MAX_CASES]
    total   = len(targets)
    if total == 0:
        return

    logger.info(f"Gemini AI 요약 시작 ({total}건, 최대 {MAX_CASES}건)...")
    consecutive_429 = 0

    for i, case in enumerate(targets):
        if i > 0:
            time.sleep(DELAY_SEC)

        success = False
        for backoff_idx, wait in enumerate([0] + _BACKOFF):
            if wait:
                logger.warning(f"  [{i+1}/{total}] 429 대기 {wait}s 후 재시도...")
                time.sleep(wait)
            try:
                case["summary"] = _call_gemini(case, api_key)
                logger.info(f"  [{i+1}/{total}] 요약 완료: {case.get('case_num', '')}")
                consecutive_429 = 0
                success = True
                break
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    consecutive_429 += 1
                    if backoff_idx < len(_BACKOFF):
                        continue  # 다음 백오프 단계
                    logger.warning(f"  [{i+1}/{total}] 429 최대 재시도 초과 — 원문 유지")
                else:
                    logger.warning(f"  [{i+1}/{total}] Gemini HTTP 오류 (원문 유지): {exc}")
                break
            except Exception as exc:
                logger.warning(f"  [{i+1}/{total}] Gemini 실패 (원문 유지): {exc}")
                break

        # 연속 3회 429 → 일일 한도 소진 가능성이 높으므로 중단
        if not success and consecutive_429 >= 3:
            logger.error(
                "Gemini 연속 3회 429 — 일일 할당량 소진으로 판단, AI 요약을 중단합니다."
            )
            break

    logger.info("AI 요약 완료.")


def _call_gemini(case: dict, api_key: str) -> str:
    existing  = case.get("summary") or ""
    title     = case.get("title") or ""
    case_type = case.get("case_type") or ""

    source = f"판시사항:\n{existing}" if existing else f"사건명: {title}\n사건종류: {case_type}"

    prompt = (
        "다음 법원 판례 정보를 법률 비전문가도 이해하기 쉽게 2~3문장으로 요약해 주세요. "
        "핵심 쟁점과 판단 결론을 포함하세요:\n\n" + source
    )
    resp = requests.post(
        GEMINI_URL,
        params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
