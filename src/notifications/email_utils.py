"""
Formats AI-generated insights as a styled HTML email and delivers them via
the Azure Communication Services (ACS) Email SDK.

Required environment variables (injected from Key Vault by the Container App Job):
    ACS_CONNECTION_STRING  - ACS resource connection string
    EMAIL_FROM_ADDRESS     - verified sender address (DoNotReply@<acs-domain>)
    EMAIL_RECIPIENT        - destination address
"""

import os
from functools import lru_cache
from pathlib import Path
from string import Template
import base64
import mimetypes
from pathlib import Path
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
_EMAIL_TEMPLATE_PATH: str = os.getenv("EMAIL_TEMPLATE_PATH", "")

_TEMPLATE_PATH: Path = (
        Path(_EMAIL_TEMPLATE_PATH).expanduser()
        if _EMAIL_TEMPLATE_PATH
        else Path(__file__).resolve().parent / "templates" / "insights_email.html"
)


@lru_cache(maxsize=1)
def _load_email_template() -> Template:
    """Load and cache the HTML email template from disk."""
    if not _TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Email template not found: {_TEMPLATE_PATH}")
    return Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))


def _build_attachments(attachment_paths: list[str] | None) -> list[dict]:
    """
    Convert local file paths into ACS attachment payloads.
    """
    if not attachment_paths:
        return []

    attachments = []

    for file_path in attachment_paths:
        path = Path(file_path)
        if not path.exists():
            print(f"[WARN] Attachment not found: {file_path}")
            continue

        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"

        with open(path, "rb") as f:
            encoded_content = base64.b64encode(f.read()).decode("utf-8")

        attachments.append(
            {
                "name": path.name,
                "attachmentType": mime_type,
                "contentInBase64": encoded_content,
            }
        )

    return attachments


def build_html_email(insights_text: str, csv_name: str = "data.csv") -> str:
    """Render insights text (plain text / Markdown) into the full HTML template."""
    date_str = datetime.now().strftime("%B %d, %Y at %H:%M")
    insights_html = _md_to_html(insights_text)
    return _load_email_template().safe_substitute(
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
    attachment_paths: list[str] | None = None,
) -> None:
    """Send an HTML insights email via the ACS Email SDK."""
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
        f"{insights_text}\n\n"
        f"Interactive HTML charts are attached."
    )

    attachments = _build_attachments(attachment_paths)

    print(f"\n{'─' * 50}")
    print(f"  To          : {to_addr}")
    print(f"  Subject     : {subject}")
    print(
        f"  Attachments : "
        f"{[Path(p).name for p in attachment_paths] if attachment_paths else []}"
    )
    print(f"{'─' * 50}")

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
        print(f"[DRY-RUN] Email not sent. Preview at: file://{tmp.name}")
        if attachment_paths:
            print(f"[DRY-RUN] Attachments prepared: {attachment_paths}\n")
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

    if attachments:
        message["attachments"] = attachments

    poller = client.begin_send(message)
    result = poller.result()
    message_id = result.get("id") if isinstance(result, dict) else result.message_id
    print(f"Email delivered successfully. Message ID: {message_id}\n")