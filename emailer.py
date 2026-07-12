import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

from excel_export import generate_excel

logger = logging.getLogger(__name__)


def _get_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"환경변수 {key} 가 설정되지 않았습니다. "
            f"GitHub → Settings → Secrets and variables → Actions 에서 등록하세요."
        )
    return val


def _parse_recipients() -> list[str]:
    raw = _get_env("RECIPIENT_EMAILS")
    recipients = [addr.strip() for addr in raw.split(",") if addr.strip()]
    if not recipients:
        raise EnvironmentError("RECIPIENT_EMAILS 에 유효한 이메일 주소가 없습니다.")
    return recipients


def send_case_email(cases: list[dict], config: dict) -> None:
    sender     = _get_env("GMAIL_SENDER")
    password   = _get_env("GMAIL_APP_PASSWORD")
    recipients = _parse_recipients()

    now_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    subject = f"[판례 알림] {now_str} — {len(cases)}건 새 판례"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = ", ".join(recipients)

    # HTML + plain text
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(_build_plain(cases, config, recipients), "plain", "utf-8"))
    alt.attach(MIMEText(_build_html(cases, config, recipients), "html", "utf-8"))
    msg.attach(alt)

    # Excel 첨부
    try:
        excel_cases = []
        today = datetime.now().strftime("%Y-%m-%d")
        for c in cases:
            row = dict(c)
            row["sent_date"] = today
            excel_cases.append(row)
        excel_bytes = generate_excel(excel_cases, title="판례목록")
        fname = f"cases_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        part = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.set_payload(excel_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=fname)
        part.add_header("Content-Type",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        name=fname)
        msg.attach(part)
        logger.info(f"Excel 첨부 완료: {fname}")
    except Exception as exc:
        logger.warning(f"Excel 첨부 실패 (이메일은 발송): {exc}")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.send_message(msg)

    logger.info(f"이메일 발송 완료 → {', '.join(recipients)}")


def _build_plain(cases: list[dict], config: dict, recipients: list[str]) -> str:
    today_str = datetime.now().strftime("%Y.%m.%d")
    lines = [
        f"[판례 알림] {datetime.now().strftime('%Y-%m-%d %H:%M')} 기준 {len(cases)}건",
        "",
        "※ 판례는 선고일로부터 통상 1~4주 후 법제처에 공시됩니다.",
        "   이 알림은 오늘자 공시 기준이며, 실제 선고일과 차이가 있을 수 있습니다.",
        "   중요 판례는 대법원 종합법률정보(https://glaw.scourt.go.kr) 또는",
        "   법제처 국가법령정보(https://www.law.go.kr)를 수시로 직접 확인하시기 바랍니다.",
        "",
        "검색 조건",
        f"  키워드   : {', '.join(config.get('keywords', [])) or '없음'}",
        f"  법원     : {config.get('court_name') or '전체'}",
        f"  사건유형 : {config.get('case_type') or '전체'}",
        f"  수신자   : {', '.join(recipients)}",
        "",
        "-" * 60,
        "",
    ]
    prev_priority = None
    for i, c in enumerate(cases, 1):
        is_priority = c.get("priority", False)
        if is_priority != prev_priority:
            lines.append("★ 주요 관심 판례 (보험·설계사·인공지능·IT·전자금융·개인정보·신용정보·정보통신)" if is_priority else "○ 기타 판례")
            lines.append("-" * 40)
            prev_priority = is_priority
        link = c.get("link", "-") or "-"
        fresh_mark = " [최신]" if c.get("is_fresh") else ""
        lines += [
            f"{i}. {c.get('title', '-')}{fresh_mark}",
            f"   사건번호: {c.get('case_num', '-')}",
            f"   법원    : {c.get('court', '-')}",
            f"   선고일  : {c.get('date', '-') or '-'}",
            f"   게재확인: {today_str} (법제처 등재일 기준)",
            f"   참조URL : {link}",
        ]
        if c.get("content"):
            preview = c["content"][:150]
            suffix = "…" if len(c["content"]) > 150 else ""
            lines.append(f"   내용   : {preview}{suffix}")
        if c.get("summary"):
            lines.append(f"   AI요약  : {c['summary']}")
        lines.append("")
    lines += [
        "출처: https://glaw.scourt.go.kr (대법원 종합법률정보)",
        "     https://www.law.go.kr (법제처 국가법령정보)",
    ]
    return "\n".join(lines)


def _build_html(cases: list[dict], config: dict, recipients: list[str]) -> str:
    now_str       = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    today_dot     = datetime.now().strftime("%Y.%m.%d")
    keywords_str  = ", ".join(config.get("keywords", [])) or "없음"
    court_str     = config.get("court_name") or "전체"
    case_type_str = config.get("case_type") or "전체"

    rows = ""
    prev_priority = None
    row_idx = 0
    for c in cases:
        is_priority = c.get("priority", False)
        is_fresh    = c.get("is_fresh", False)

        if is_priority != prev_priority:
            if is_priority:
                header_label = "&#9733; 주요 관심 판례 (보험&#183;설계사&#183;인공지능&#183;IT&#183;전자금융&#183;개인정보&#183;신용정보&#183;정보통신)"
                header_bg    = "#1a3a6b"
            else:
                header_label = "&#9675; 기타 판례"
                header_bg    = "#4a5568"
            rows += f"""
        <tr>
          <td colspan="4" style="padding:10px 15px;background:{header_bg};
              color:#ffffff;font-size:13px;font-weight:bold;letter-spacing:0.3px;">
            {header_label}
          </td>
        </tr>"""
            prev_priority = is_priority

        row_idx += 1
        bg       = "#f2f6ff" if row_idx % 2 == 0 else "#ffffff"
        title    = c.get("title", "-")
        link     = c.get("link", "#") or "#"
        case_num = c.get("case_num", "-")
        court    = c.get("court", "-")
        date     = c.get("date", "-") or "-"
        content  = c.get("content", "")
        summary  = c.get("summary", "")
        fresh_badge = (
            '<span style="display:inline-block;background:#28a745;color:#fff;'
            'font-size:10px;padding:1px 5px;border-radius:3px;margin-left:5px;">최신</span>'
            if is_fresh else ""
        )

        content_html = ""
        if content:
            preview = (content[:180] + "…") if len(content) > 180 else content
            content_html = (
                f'<div style="margin-top:6px;font-size:12px;color:#444444;'
                f'line-height:1.6;border-left:2px solid #cccccc;padding-left:8px;">'
                f'{preview}'
                f'</div>'
            )

        summary_html = ""
        if summary:
            summary_html = (
                f'<div style="margin-top:7px;font-size:12px;color:#1a3366;'
                f'background:#e8f0fe;padding:6px 10px;'
                f'border-left:3px solid #1a56c4;">'
                f'<strong style="color:#444444;">AI요약:</strong> {summary}'
                f'</div>'
            )

        url_html = (
            f'<div style="margin-top:5px;font-size:11px;color:#666666;">'
            f'&#128279; <a href="{link}" style="color:#1a56c4;">{link}</a>'
            f'</div>'
        ) if link and link != "#" else ""

        rows += f"""
        <tr style="background:{bg};">
          <td style="padding:12px 15px;border-bottom:1px solid #d0d8ee;">
            <a href="{link}" style="color:#1a56c4;text-decoration:none;font-weight:bold;font-size:14px;">{title}</a>{fresh_badge}
            {content_html}
            {summary_html}
            {url_html}
          </td>
          <td style="padding:12px 15px;border-bottom:1px solid #d0d8ee;white-space:nowrap;color:#111111;font-size:14px;">{case_num}</td>
          <td style="padding:12px 15px;border-bottom:1px solid #d0d8ee;white-space:nowrap;color:#111111;font-size:14px;">{court}</td>
          <td style="padding:12px 15px;border-bottom:1px solid #d0d8ee;white-space:nowrap;font-size:14px;">
            <span style="color:#111111;">{date}</span>
            <div style="margin-top:3px;font-size:11px;color:#888888;">&#128197; 게재확인 {today_dot}</div>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="font-family:'Malgun Gothic',Arial,sans-serif;background:#f0f2f5;margin:0;padding:20px;">
  <div style="max-width:900px;margin:0 auto;background:#ffffff;border:1px solid #cccccc;">

    <div style="background:#1a56c4;padding:24px 28px;">
      <h1 style="margin:0;font-size:22px;color:#ffffff;letter-spacing:-0.5px;">&#9878; 판례 알림</h1>
      <p style="margin:6px 0 0;font-size:14px;color:#c8dfff;">{now_str} 기준 &nbsp;|&nbsp; 총 <strong style="color:#ffffff;">{len(cases)}건</strong></p>
    </div>

    <div style="background:#fff8e1;padding:12px 28px;border-left:4px solid #f59e0b;font-size:13px;color:#555555;">
      &#9432; 판례는 선고일로부터 통상 <strong>1~4주 후</strong> 법제처에 공시됩니다.
      이 알림은 오늘자 공시 기준이며, 실제 선고일과 차이가 있을 수 있습니다.<br>
      중요 판례는 <a href="https://glaw.scourt.go.kr" style="color:#b45309;">대법원 종합법률정보</a> 또는
      <a href="https://www.law.go.kr" style="color:#b45309;">법제처 국가법령정보</a>를 <strong>수시로 직접 확인</strong>하시기 바랍니다.
    </div>

    <div style="background:#ddeaff;padding:14px 28px;border-left:4px solid #1a56c4;font-size:14px;color:#111111;">
      <strong>검색 조건</strong> &nbsp;
      키워드: <strong>{keywords_str}</strong> &nbsp;|&nbsp;
      법원: <strong>{court_str}</strong> &nbsp;|&nbsp;
      사건유형: <strong>{case_type_str}</strong>
      <br>
      수신자: <strong>{', '.join(recipients)}</strong>
    </div>

    <div style="overflow-x:auto;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#2c3e6b;">
            <th style="padding:12px 15px;text-align:left;font-weight:600;color:#ffffff;">판례명</th>
            <th style="padding:12px 15px;text-align:left;font-weight:600;white-space:nowrap;color:#ffffff;">사건번호</th>
            <th style="padding:12px 15px;text-align:left;font-weight:600;white-space:nowrap;color:#ffffff;">법원</th>
            <th style="padding:12px 15px;text-align:left;font-weight:600;white-space:nowrap;color:#ffffff;">선고일 / 게재확인</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>

    <div style="padding:16px 28px;background:#f0f2f5;font-size:12px;color:#555555;border-top:1px solid #cccccc;">
      이 메일은 자동 발송되었습니다.<br>
      출처: <a href="https://glaw.scourt.go.kr" style="color:#1a56c4;">대법원 종합법률정보</a>
      &nbsp;|&nbsp;
      <a href="https://www.law.go.kr" style="color:#1a56c4;">법제처 국가법령정보</a>
    </div>
  </div>
</body>
</html>"""
