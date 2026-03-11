"""
Formats AI-generated insights as a styled HTML email and delivers them via
the Azure Communication Services (ACS) Email SDK.

Required environment variables (injected from Key Vault by the Container App Job):
    ACS_CONNECTION_STRING  - ACS resource connection string
    EMAIL_FROM_ADDRESS     - verified sender address (DoNotReply@<acs-domain>)
    EMAIL_RECIPIENT        - destination address
"""

import os
from datetime import datetime
from typing import Optional

from azure.communication.email import EmailClient

# Markdown to HTML conversion
try:
    import markdown as _md

    def _md_to_html(text: str) -> str:
        return _md.markdown(text, extensions=["extra", "nl2br"])

except ImportError:  # pragma: no cover
    _md = None  # type: ignore

    def _md_to_html(text: str) -> str:  # type: ignore[misc]
        """Minimal fallback: wrap lines / paragraphs in HTML tags."""
        blocks = text.strip().split("\n\n")
        parts: list[str] = []
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            lines = [l.rstrip() for l in block.splitlines() if l.strip()]
            # Detect numbered / bullet lists
            is_list = all(
                l.startswith(tuple("0123456789")) or l.startswith(("-", "*", "•"))
                for l in lines
            )
            if is_list:
                items = "".join(
                    f"  <li>{l.lstrip('-*•0123456789. ').strip()}</li>\n"
                    for l in lines
                )
                parts.append(f"<ol>\n{items}</ol>")
            else:
                parts.append(f"<p>{'<br>'.join(lines)}</p>")
        return "\n".join(parts)


_ACS_CONNECTION_STRING: str = os.getenv("ACS_CONNECTION_STRING", "")
_EMAIL_SENDER: str = os.getenv("EMAIL_FROM_ADDRESS", "DoNotReply@hitachi.local")
_EMAIL_RECIPIENT: str = os.getenv("EMAIL_RECIPIENT", "hitachiseniordesign@outlook.com")


# HTML email template
_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>AI Business Insights Report</title>
  <style>
    /* ── Reset & base ───────────────────────────────────────────────────── */
    body {{
      margin: 0; padding: 0;
      background-color: #f4f4f4;
      font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
      color: #333333;
    }}
    /* ── Outer wrapper ──────────────────────────────────────────────────── */
    .wrapper {{
      max-width: 680px;
      margin: 32px auto;
      background: #ffffff;
      border-radius: 8px;
      overflow: hidden;
      box-shadow: 0 2px 10px rgba(0,0,0,0.10);
    }}
    /* ── Header ─────────────────────────────────────────────────────────── */
    .header {{
      background-color: #cc0000;   /* Hitachi red */
      padding: 36px 44px 28px;
      color: #ffffff;
    }}
    .header h1 {{
      margin: 0 0 6px 0;
      font-size: 26px;
      font-weight: 700;
      letter-spacing: 0.4px;
    }}
    .header .sub {{
      margin: 0;
      font-size: 14px;
      opacity: 0.88;
    }}
    .badge {{
      display: inline-block;
      margin-top: 12px;
      background: rgba(255,255,255,0.18);
      border: 1px solid rgba(255,255,255,0.35);
      border-radius: 14px;
      padding: 3px 14px;
      font-size: 11px;
      letter-spacing: 0.6px;
      text-transform: uppercase;
    }}
    /* ── Content area ───────────────────────────────────────────────────── */
    .content {{
      padding: 32px 44px 36px;
    }}
    .meta-box {{
      background: #fafafa;
      border-left: 4px solid #cc0000;
      border-radius: 4px;
      padding: 10px 16px;
      margin-bottom: 28px;
      font-size: 13px;
      color: #666;
    }}
    .section-title {{
      color: #cc0000;
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 1.2px;
      margin: 0 0 16px 0;
      padding-bottom: 10px;
      border-bottom: 2px solid #f0f0f0;
    }}
    /* ── Insight body (markdown output lands here) ──────────────────────── */
    .insights p,
    .insights li {{
      font-size: 15px;
      line-height: 1.75;
      color: #444444;
    }}
    .insights h1, .insights h2, .insights h3 {{
      color: #222222;
      margin-top: 18px;
    }}
    .insights ol, .insights ul {{
      padding-left: 22px;
    }}
    .insights li {{
      margin-bottom: 10px;
    }}
    .insights strong {{ color: #111111; }}
    .insights code {{
      background: #f3f3f3;
      border-radius: 3px;
      padding: 1px 5px;
      font-size: 13px;
    }}
    /* ── Footer ─────────────────────────────────────────────────────────── */
    .footer {{
      background-color: #f0f0f0;
      padding: 18px 44px;
      text-align: center;
      font-size: 12px;
      color: #999999;
      border-top: 1px solid #e0e0e0;
    }}
    .footer a {{ color: #cc0000; text-decoration: none; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <!-- Header -->
    <div class="header">
      <h1>AI Business Insights Report</h1>
      <p class="sub">Generated on {date_str}</p>
      <span class="badge">Azure OpenAI &amp; LangChain</span>
    </div>

    <!-- Body -->
    <div class="content">
      <div class="meta-box">
        Dataset:&nbsp;<strong>{csv_name}</strong>
        &nbsp;&nbsp;|&nbsp;&nbsp;
        Report date:&nbsp;<strong>{date_str}</strong>
      </div>

      <p class="section-title">Key Insights</p>

      <div class="insights">
        {insights_html}
      </div>
    </div>

    <!-- Footer -->
    <div class="footer">
      This report was automatically generated by the
      <a href="#">Hitachi AI Analytics Platform</a>.<br>
      Do&nbsp;not reply &mdash; this message was sent from an unmonitored address.
    </div>
  </div>
</body>
</html>
"""


def build_html_email(insights_text: str, csv_name: str = "data.csv") -> str:
    """Render insights text (plain text / Markdown) into the full HTML template.

    Args:
        insights_text: The raw insight string returned by the AI model.
        csv_name:      Dataset label shown in the email meta-box.

    Returns:
        A complete HTML document as a string.
    """
    date_str = datetime.now().strftime("%B %d, %Y at %H:%M")
    insights_html = _md_to_html(insights_text)
    return _HTML_TEMPLATE.format(
        date_str=date_str,
        csv_name=csv_name,
        insights_html=insights_html,
    )


def send_insights_email(
    insights_text: str,
    csv_name: str = "data.csv",
    *,
    subject: Optional[str] = None,
    recipient: Optional[str] = None,
    sender: Optional[str] = None,
    connection_string: Optional[str] = None,
) -> None:
    """Send an HTML insights email via the ACS Email SDK.

    Args:
        insights_text:     Plain-text / Markdown insights from the AI model.
        csv_name:          Dataset label used in the email body.
        subject:           Email subject line.
        recipient:         Destination address  (env: EMAIL_RECIPIENT).
        sender:            From address          (env: EMAIL_FROM_ADDRESS).
        connection_string: ACS connection string (env: ACS_CONNECTION_STRING).
    """
    conn_str = connection_string or _ACS_CONNECTION_STRING
    from_addr = sender or _EMAIL_SENDER
    to_addr = recipient or _EMAIL_RECIPIENT
    subject = subject or (
        f"AI Business Insights Report \u2013 {datetime.now().strftime('%B %d, %Y')}"
    )

    html_body = build_html_email(insights_text, csv_name=csv_name)
    plain_body = (
        f"AI Business Insights Report\n"
        f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}\n"
        f"Dataset:   {csv_name}\n"
        f"{'=' * 60}\n\n"
        f"{insights_text}"
    )

    print(f"\n{'─' * 50}")
    print(f"  To      : {to_addr}")
    print(f"  Subject : {subject}")
    print(f"{'─' * 50}")

    # Local dry-run mode: ACS_CONNECTION_STRING unset or set to "local".
    # Writes the rendered HTML to a temp file instead of calling ACS so
    # we can preview the email in a browser without needing Azure credentials.
    if not conn_str or conn_str.strip().lower() == "local":
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            prefix="hitachi_email_",
            suffix=".html",
            delete=False,
            mode="w",
            encoding="utf-8",
        )
        tmp.write(html_body)
        tmp.close()
        print(f"[DRY-RUN] Email not sent. Preview at: file://{tmp.name}\n")
        return

    client = EmailClient.from_connection_string(conn_str)
    message = {
        "senderAddress": from_addr,
        "recipients": {"to": [{"address": to_addr}]},
        "content": {
            "subject": subject,
            "plainText": plain_body,
            "html": html_body,
        },
    }
    poller = client.begin_send(message)
    result = poller.result()
    message_id = result.get("id") if isinstance(result, dict) else result.message_id
    print(f"Email delivered successfully. Message ID: {message_id}\n")
