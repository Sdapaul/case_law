import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

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
    """환경변수 RECIPIENT_EMAILS (쉼표 구분) → 리스트"""
    raw = _get_env("RECIPIENT_EMAILS")
    recipients = [addr.strip() for addr in raw.split(",") if addr.strip()]
    if not recipients:
        raise EnvironmentError("RECIPIENT_EMAILS 에 유효한 이메일 주소가 없습니다.")
    return recipients


def send_case_email(cases: list[dict], config: dict) -> None:
    sender = _get_env("GMAIL_SENDER")
    password = _get_env("GMAIL_APP_PASSWORD")
    recipients = _parse_recipients()

    now_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    subject = f"[판례 알림] {now_str} — {len(cases)}건 새 판례"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    msg.attach(MIMEText(_build_plain(cases, config, recipients), "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(cases, config, recipients), "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())

    logger.info(f"이메일 발송 완료 → {', '.join(recipients)}")


def _build_plain(cases: list[dict], config: dict, recipients: list[str]) -> str:
    lines = [
        f"[판례 알림] {datetime.now().strftime('%Y-%m-%d %H:%M')} 기준 {len(cases)}건",
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
    for i, c in enumerate(cases, 1):
        lines += [
            f"{i}. {c.get('title', '-')}",
            f"   사건번호: {c.get('case_num', '-')}",
            f"   법원    : {c.get('court', '-')}",
            f"   선고일  : {c.get('date', '-')}",
            f"   링크    : {c.get('link', '-')}",
        ]
        if c.get("summary"):
            lines.append(f"   요약    : {c['summary']}")
        lines.append("")
    lines.append("출처: https://glaw.scourt.go.kr")
    return "\n".join(lines)


def _build_html(cases: list[dict], config: dict, recipients: list[str]) -> str:
    now_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")
    keywords_str = ", ".join(config.get("keywords", [])) or "없음"
    court_str = config.get("court_name") or "전체"
    case_type_str = config.get("case_type") or "전체"

    rows = ""
    for i, c in enumerate(cases, 1):
        bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        title = c.get("title", "-")
        link = c.get("link", "#")
        case_num = c.get("case_num", "-")
        court = c.get("court", "-")
        date = c.get("date", "-")
        summary = c.get("summary", "")

        summary_html = (
            f'<br><small style="color:#666;font-size:12px;">{summary}</small>'
            if summary else ""
        )

        rows += f"""
        <tr style="background:{bg};">
          <td style="padding:12px 15px;border-bottom:1px solid #eee;">
            <a href="{link}" style="color:#1a73e8;text-decoration:none;font-weight:bold;">{title}</a>
            {summary_html}
          </td>
          <td style="padding:12px 15px;border-bottom:1px solid #eee;white-space:nowrap;color:#333;">{case_num}</td>
          <td style="padding:12px 15px;border-bottom:1px solid #eee;white-space:nowrap;color:#333;">{court}</td>
          <td style="padding:12px 15px;border-bottom:1px solid #eee;white-space:nowrap;color:#333;">{date}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="font-family:'Malgun Gothic',Arial,sans-serif;background:#f4f6f8;margin:0;padding:20px;">
  <div style="max-width:900px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">

    <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);padding:24px 28px;color:white;">
      <h1 style="margin:0;font-size:22px;letter-spacing:-0.5px;">⚖️ 판례 알림</h1>
      <p style="margin:6px 0 0;opacity:0.88;font-size:14px;">{now_str} 기준 &nbsp;|&nbsp; 총 <strong>{len(cases)}건</strong></p>
    </div>

    <div style="background:#e8f0fe;padding:14px 28px;border-left:4px solid #1a73e8;font-size:14px;color:#333;">
      <strong>검색 조건</strong> &nbsp;
      키워드: <strong>{keywords_str}</strong> &nbsp;|&nbsp;
      법원: <strong>{court_str}</strong> &nbsp;|&nbsp;
      사건유형: <strong>{case_type_str}</strong>
      <br style="margin-top:4px;">
      수신자: <strong>{', '.join(recipients)}</strong>
    </div>

    <div style="overflow-x:auto;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#34495e;color:white;">
            <th style="padding:12px 15px;text-align:left;font-weight:600;">판례명</th>
            <th style="padding:12px 15px;text-align:left;font-weight:600;white-space:nowrap;">사건번호</th>
            <th style="padding:12px 15px;text-align:left;font-weight:600;white-space:nowrap;">법원</th>
            <th style="padding:12px 15px;text-align:left;font-weight:600;white-space:nowrap;">선고일</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>

    <div style="padding:16px 28px;background:#f4f6f8;font-size:12px;color:#888;text-align:center;">
      이 메일은 자동 발송되었습니다. &nbsp;
      출처: <a href="https://glaw.scourt.go.kr" style="color:#1a73e8;">대법원 종합법률정보</a>
    </div>
  </div>
</body>
</html>"""
