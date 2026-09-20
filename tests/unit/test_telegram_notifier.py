import pytest
from src.infrastructure.notifications.telegram import (
    markdown_to_telegram_html,
    split_telegram_message,
    TelegramNotifier
)

def test_markdown_to_telegram_html():
    raw_md = "### Headline\n**Bold text** and `code`\n---\n* Bullet 1\n* Bullet 2\n**Unclosed bold"
    html = markdown_to_telegram_html(raw_md)
    assert "📌 <b>Headline</b>" in html
    assert "<b>Bold text</b>" in html
    assert "<code>code</code>" in html
    assert "────────────────────────" in html
    assert "• Bullet 1" in html
    # Check that dangling ** was cleaned
    assert "**" not in html
    assert "<b>Unclosed bold</b>" in html

def test_split_telegram_message_short():
    short = "Hello world!"
    chunks = split_telegram_message(short, max_length=100)
    assert len(chunks) == 1
    assert chunks[0] == short

def test_split_telegram_message_long_with_tags():
    # Long text with an open <b> tag that spans across the split boundary
    inner = " كلمة " * 300
    long_msg = f"<b>{inner}</b>"
    chunks = split_telegram_message(long_msg, max_length=500)
    assert len(chunks) > 1

    # First chunk must properly close </b>
    assert chunks[0].endswith("</b>")
    # Subsequent chunk must reopen <b>
    assert chunks[1].startswith("<b>")
    # All chunks must have balanced tags
    for c in chunks:
        assert c.count("<b>") == c.count("</b>")
