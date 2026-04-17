"""
Gemini 1.5 Flash (무료 tier) 로 판시사항을 쉬운 한국어로 요약.
GEMINI_API_KEY 환경변수가 없으면 기존 판시사항을 그대로 사용.

무료 한도: 분당 15회 / 일 1,500회
"""

import os
import time
import logging
import requests

logger = logging.getLogger(__name__)

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/gemini-1.5-flash:generateContent"
)
MAX_CASES = 50   # 무료 tier 안전 상한
DELAY_SEC = 4.5  # 15 RPM → 4s 간격 (여유분 0.5s)


def add_ai_summaries(cases: list[dict]) -> None:
    """판례 목록에 AI 요약을 in-place로 추가. GEMINI_API_KEY 없으면 no-op."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("GEMINI_API_KEY 없음 — 기존 판시사항을 요약으로 사용합니다.")
        return

    targets = [c for c in cases if c.get("summary")][:MAX_CASES]
    total = len(targets)
    if total == 0:
        return

    logger.info(f"Gemini AI 요약 시작 ({total}건)...")
    for i, case in enumerate(targets):
        if i > 0:
            time.sleep(DELAY_SEC)
        try:
            case["summary"] = _call_gemini(case["summary"], api_key)
            logger.info(f"  [{i+1}/{total}] 요약 완료: {case.get('case_num', '')}")
        except Exception as exc:
            logger.warning(f"  [{i+1}/{total}] Gemini 실패 (원문 유지): {exc}")

    logger.info("AI 요약 완료.")


def _call_gemini(text: str, api_key: str) -> str:
    prompt = (
        "다음 법원 판시사항을 법률 비전문가도 이해하기 쉽게 2~3문장으로 요약해 주세요. "
        "핵심 쟁점과 판단 결론을 포함하세요:\n\n" + text
    )
    resp = requests.post(
        GEMINI_URL,
        params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
