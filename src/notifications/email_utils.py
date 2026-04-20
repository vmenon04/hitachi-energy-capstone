"""
Formats AI-generated insights as a styled HTML email and delivers them via
the Azure Communication Services (ACS) Email SDK.

Required environment variables (injected from Key Vault by the Container App Job):
    ACS_CONNECTION_STRING  - ACS resource connection string
    EMAIL_FROM_ADDRESS     - verified sender address (DoNotReply@<acs-domain>)
    EMAIL_RECIPIENT        - destination address
"""

import os
import re
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
_EMAIL_RECIPIENT: str = os.getenv("EMAIL_RECIPIENT", "hitachienergy2@outlook.com")
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
                "contentType": mime_type,
                "contentInBase64": encoded_content,
            }
        )

    return attachments


def build_html_email(
    insights_text: str,
    csv_name: str = "data.csv",
    chart_images: dict[str, list[dict]] | None = None,
) -> str:
    """Render insights text (plain text / Markdown) into the full HTML template."""
    date_str = datetime.now().strftime("%B %d, %Y at %H:%M")
    chart_images = chart_images or {}

    def _norm(s: str) -> str:
        return s.lower().strip()

    def _chart_block(chart: dict) -> str:
        title = chart.get("title", "")
        b64 = chart.get("image_b64", "")
        sas_url = chart.get("sas_url", "")
        link_tag = (
            f'<a href="{sas_url}" class="chart-link" target="_blank">'
            f'View interactive chart \u2192</a>'
            if sas_url else ""
        )
        return (
            f'<div class="chart-block">'
            f'<p class="chart-title">{title}</p>'
            f'<img src="data:image/png;base64,{b64}" alt="{title}"'
            f' style="width:100%;max-width:700px;display:block;margin:0 auto;"/>'
            f'{link_tag}'
            f'</div>'
        )

    # Build a normalised lookup so minor LLM title drift still matches
    normalized_map = {_norm(k): v for k, v in chart_images.items()}
    matched_titles: set[str] = set()

    # Split insights on ### headings so each section is followed by its charts
    sections = re.split(r'(?m)^(?=### )', insights_text.strip())
    html_parts: list[str] = []

    for section in sections:
        if not section.strip():
            continue
        html_parts.append(_md_to_html(section.strip()))

        title_match = re.match(r'^### (.+)', section)
        if title_match and normalized_map:
            norm_title = _norm(title_match.group(1))
            charts = normalized_map.get(norm_title, [])
            if not charts:
                # Substring fallback for minor LLM title drift
                for key, val in normalized_map.items():
                    if norm_title in key or key in norm_title:
                        charts = val
                        norm_title = key
                        break
            for chart in charts:
                html_parts.append(_chart_block(chart))
            if charts:
                matched_titles.add(norm_title)

    insights_html = "\n".join(html_parts)

    # Charts not matched to any insight fall through to the bottom
    fallback_blocks = [
        _chart_block(chart)
        for key, charts_list in normalized_map.items()
        if key not in matched_titles
        for chart in charts_list
    ]
    charts_html = "\n".join(fallback_blocks)

    return _load_email_template().safe_substitute(
        date_str=date_str,
        csv_name=csv_name,
        insights_html=insights_html,
        charts_html=charts_html,
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
    chart_images: dict[str, list[dict]] | None = None,
    persona: Optional[str] = None,
) -> None:
    """Send an HTML insights email via the ACS Email SDK.
    
    Args:
        insights_text: The insights text to include in the email.
        csv_name: The name of the data source.
        subject: Optional custom subject line. If not provided, a default based on persona is used.
        recipient: Optional email recipient. Defaults to EMAIL_RECIPIENT env var.
        sender: Optional sender email. Defaults to EMAIL_FROM_ADDRESS env var.
        connection_string: Optional ACS connection string. Defaults to ACS_CONNECTION_STRING env var.
        attachment_paths: Optional list of file paths to attach.
        chart_images: Optional dict of insight titles to chart image data.
        persona: Optional persona name (e.g., 'r_and_d', 'project_manager', 'engineer') to customize subject and messaging.
    """
    conn_str = connection_string or _ACS_CONNECTION_STRING
    from_addr = sender or _EMAIL_SENDER
    to_addr = recipient or _EMAIL_RECIPIENT
    
    # If subject not provided, generate a persona-specific one
    if subject is None:
        persona_label = ""
        if persona == "r_and_d":
            persona_label = "R&D Report"
        elif persona == "project_manager":
            persona_label = "Project Manager Report"
        elif persona == "engineer":
            persona_label = "Engineering Report"
        else:
            persona_label = "Analysis"
        
        subject = f"{persona_label} – {datetime.now().strftime('%B %d, %Y')}"

    html_body = build_html_email(insights_text, csv_name=csv_name, chart_images=chart_images)
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
    total_charts = sum(len(v) for v in chart_images.values()) if chart_images else 0
    print(f"  Charts      : {total_charts} inline image(s)")
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