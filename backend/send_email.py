import html
import os
import smtplib
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate
from urllib.parse import urlparse
from dotenv import load_dotenv
from timezone_utils import get_timezone

# Load the environment variables from the .env file
load_dotenv()


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _plain_text(value):
    import re

    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value or "")
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    return " ".join(value.split())


def build_email_html(articles, newsletter_name="TECH / DAILY", timezone_name="UTC"):
    today = datetime.now(get_timezone(timezone_name)).strftime("%A, %d %B %Y")

    article_sections = []

    for article in articles:
        title = html.escape(str(article.get("title") or "Untitled"))
        link = str(article.get("link") or "").strip()
        summary = html.escape(_plain_text(article.get("summary", "")))
        source = html.escape(str(article.get("source") or "Unknown source"))

        published = article.get("published_parsed")
        if published:
            try:
                published_text = time.strftime("%d %b %Y, %I:%M %p", published)
            except (TypeError, ValueError, OverflowError):
                published_text = str(article.get("published") or "")
        else:
            published_text = str(article.get("published") or "")

        published_html = (
            f'<span style="color:#64748b;font-size:12px;">'
            f'{html.escape(published_text)}</span>'
            if published_text else ""
        )

        parsed_link = urlparse(link)
        if parsed_link.scheme in ("http", "https") and parsed_link.netloc:
            safe_link = html.escape(link, quote=True)
            title_html = (
                f'<a href="{safe_link}" style="color:#173f35;'
                f'text-decoration:none;">{title}</a>'
            )
            link_html = (
                f'<a href="{safe_link}" style="color:#26745b;'
                f'font-weight:bold;text-decoration:none;">Read full story &rarr;</a>'
            )
        else:
            title_html = title
            link_html = ""

        article_sections.append(f"""
        <tr>
          <td style="padding:22px 24px;border-bottom:1px solid #e5e7eb;">
            <div style="font-size:11px;letter-spacing:1px;text-transform:uppercase;
                        color:#64748b;margin-bottom:9px;">{source}</div>
            <h2 style="font-family:Arial,sans-serif;font-size:19px;line-height:1.4;
                       margin:0 0 10px 0;">{title_html}</h2>
            {f'<p style="font-family:Arial,sans-serif;font-size:14px;line-height:1.7;color:#475569;margin:0 0 12px 0;">{summary}</p>' if summary else ''}
            <div style="margin-bottom:12px;">{published_html}</div>
            {link_html}
          </td>
        </tr>
        """)

    if article_sections:
        content_html = "\n".join(article_sections)
    else:
        content_html = """
        <tr><td style="padding:28px 24px;font-family:Arial,sans-serif;
                       color:#475569;line-height:1.6;">
          No articles were available for this briefing. Please try again later.
        </td></tr>
        """

    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f3;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
         style="background:#f1f5f3;padding:24px 8px;">
    <tr><td align="center">
      <table role="presentation" width="600" cellspacing="0" cellpadding="0"
             style="width:100%;max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;">
        <tr>
          <td style="background:#173f35;padding:30px 24px;color:#ffffff;">
            <div style="font-family:Arial,sans-serif;font-size:12px;letter-spacing:2px;
                        font-weight:bold;color:#c7dfd3;">{html.escape(newsletter_name)}</div>
            <h1 style="font-family:Arial,sans-serif;font-size:27px;line-height:1.25;
                       margin:16px 0 8px 0;color:#ffffff;">Your world of tech, in focus.</h1>
            <p style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;
                      margin:0;color:#d8e7df;">A curated technology briefing for {html.escape(today)}.</p>
          </td>
        </tr>
        {content_html}
        <tr>
          <td style="padding:20px 24px;background:#f8faf9;font-family:Arial,sans-serif;
                     font-size:12px;line-height:1.6;color:#64748b;text-align:center;">
            You received this message because you configured your personal technology news reader.
            <br>Stories are linked to their original publishers.
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def build_email_text(articles, timezone_name="UTC"):
    """Build a plain-text alternative for email clients."""
    lines = [
        "TECH / DAILY — Your technology briefing",
        datetime.now(get_timezone(timezone_name)).strftime("%A, %d %B %Y"),
        "=" * 55,
    ]

    if not articles:
        lines.append("No articles were available for this briefing.")
    else:
        for index, article in enumerate(articles, start=1):
            title = _plain_text(article.get("title", "Untitled"))
            source = _plain_text(article.get("source", "Unknown source"))
            summary = _plain_text(article.get("summary", ""))
            link = str(article.get("link") or "")

            lines.extend([
                "",
                f"{index}. {title}",
                f"Source: {source}",
            ])
            if summary:
                lines.append(summary[:500])
            if link:
                lines.append(f"Read more: {link}")
            lines.append("-" * 55)

    return "\n".join(lines)


def send_email(articles, recipient, timezone_name="UTC"):
    sender = os.getenv("NEWS_EMAIL_ADDRESS")
    app_password = os.getenv("NEWS_EMAIL_APP_PASSWORD")

    if not sender or not app_password:
        raise RuntimeError(
            "Set NEWS_EMAIL_ADDRESS and NEWS_EMAIL_APP_PASSWORD "
            "as environment variables before sending."
        )

    if not recipient or "@" not in recipient:
        raise ValueError("Please provide a valid recipient email address.")

    message = EmailMessage()
    local_now = datetime.now(get_timezone(timezone_name))
    message["Subject"] = f"Your Tech Daily Briefing - {local_now.strftime('%d %b %Y')}"
    message["From"] = sender
    message["To"] = recipient
    message["Date"] = formatdate(localtime=True)

    message.set_content(build_email_text(articles, timezone_name))
    message.add_alternative(build_email_html(articles, timezone_name=timezone_name), subtype="html")

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.login(sender, app_password)
        server.send_message(message)

    print(f"Newsletter sent successfully to {recipient}.")


def send_confirmation_email(recipient, token):
    sender = os.getenv("NEWS_EMAIL_ADDRESS")
    app_password = os.getenv("NEWS_EMAIL_APP_PASSWORD")
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5500").rstrip("/")
    if not sender or not app_password:
        raise RuntimeError("Email delivery credentials are not configured.")

    message = EmailMessage()
    message["Subject"] = "Confirm your Tech / Daily subscription"
    message["From"] = sender
    message["To"] = recipient
    message["Date"] = formatdate(localtime=True)
    confirmation_url = f"{frontend_url}/confirm.html?token={token}"
    message.set_content(
        "Confirm your Tech / Daily subscription by opening this link:\n\n"
        f"{confirmation_url}\n\nThis link expires in 24 hours."
    )
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.login(sender, app_password)
        server.send_message(message)


if __name__ == "__main__":
    recipient = os.getenv("NEWS_EMAIL_RECIPIENT")
    if not recipient:
        raise RuntimeError(
            "Set NEWS_EMAIL_RECIPIENT to the address that should receive the newsletter."
        )

    sample_articles = [{
        "title": "Test newsletter — replace with fetched articles",
        "link": "https://example.com/",
        "summary": "This is a test email to check your HTML newsletter layout.",
        "source": "Your News Reader",
        "published": datetime.now().strftime("%a, %d %b %Y %H:%M:%S"),
    }]

    send_email(sample_articles, recipient)
