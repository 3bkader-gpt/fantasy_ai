import logging
import re
from typing import List, Optional, Dict, Any
import requests

from ...domain.interfaces.notifier import INotifier
from ...domain.models.transfer import Transfer
from ...domain.models.squad import LineupSelection
from ...config import config

logger = logging.getLogger("TelegramNotifier")


def markdown_to_telegram_html(text: str) -> str:
    """Converts AI markdown output into clean, reliable Telegram HTML."""
    if not text:
        return ""
    text = text.replace('\r\n', '\n')
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Convert headers (### Title)
    def header_repl(match):
        h_text = match.group(2).strip()
        h_text = re.sub(r'^\*+|\*+$', '', h_text).strip()
        return f"\n\n📌 <b>{h_text}</b>"
    text = re.sub(r'^(#{1,6})\s+(.+)$', header_repl, text, flags=re.MULTILINE)

    # Convert bold **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # Convert horizontal rules
    text = re.sub(r'^[ \t]*[-*_]{3,}[ \t]*$', '────────────────────────', text, flags=re.MULTILINE)

    # Convert bullet points
    text = re.sub(r'^[ \t]*[\*\-]\s+', '• ', text, flags=re.MULTILINE)

    # Convert code blocks and inline code
    text = re.sub(r'```(?:[a-zA-Z0-9_-]+)?\n?(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Normalize spacing
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class TelegramNotifier(INotifier):
    """Sends tactical briefings and transfer alerts directly to Telegram with rich HTML & buttons."""

    def __init__(self, token: str = config.telegram_bot_token, chat_id: str = config.telegram_chat_id):
        self.token = token.strip() if token else ""
        self.chat_id = chat_id.strip() if chat_id else ""
        self.is_configured = bool(self.token and self.chat_id)

    def send_message(self, text: str, reply_markup: Optional[Dict[str, Any]] = None, parse_mode: str = "HTML") -> bool:
        if not self.is_configured:
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        # Auto-convert if markdown detected and HTML requested
        if parse_mode == "HTML" and any(k in text for k in ("###", "**", "---", "`")):
            text = markdown_to_telegram_html(text)

        if reply_markup is None:
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🌐 فتح الداشبورد", "url": "https://fantasy-ai-dashboard.pages.dev/"},
                        {"text": "🔙 🏠 القائمة الرئيسية", "callback_data": "main_menu"}
                    ]
                ]
            }

        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        success = True

        for i, chunk in enumerate(chunks):
            markup = reply_markup if i == len(chunks) - 1 else None
            payload = {
                "chat_id": self.chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            if markup:
                payload["reply_markup"] = markup

            try:
                resp = requests.post(url, json=payload, timeout=12)
                if resp.status_code != 200:
                    payload.pop("parse_mode", None)
                    resp2 = requests.post(url, json=payload, timeout=12)
                    success = (resp2.status_code == 200)
            except Exception as e:
                logger.warning(f"Error sending Telegram notification: {e}")
                success = False

        return success

    def send_markdown_message(self, text: str) -> bool:
        return self.send_message(markdown_to_telegram_html(text), parse_mode="HTML")

    def send_gameweek_summary(
        self,
        gw: int,
        transfers: List[Transfer],
        lineup: LineupSelection,
        briefing_text: str,
        dry_run: bool
    ) -> bool:
        mode_str = "🛡️ [وضع المحاكاة]" if dry_run else "🚀 [تنفيذ رسمي مباشر]"
        trans_str = ""
        if transfers:
            for t in transfers:
                trans_str += f"🔴 خروج: <b>{t.player_out.name}</b> ({t.player_out.team_short})\n"
                trans_str += f"🟢 دخول: <b>{t.player_in.name}</b> ({t.player_in.team_short}) [xP: {t.player_in.xp:.1f}]\n"
        else:
            trans_str = "🔄 ترحيل التبديل المجاني (Roll Transfer)\n"

        clean_briefing = markdown_to_telegram_html(briefing_text)

        card = f"""⚽ <b>تقرير مدير الفانتازي – الجولة {gw}</b> 🤖
━━━━━━━━━━━━━━━━━━━━
📋 <b>الحالة:</b> {mode_str}
📐 <b>التشكيل:</b> <code>{lineup.formation}</code>
👑 <b>الكابتن:</b> <b>{lineup.captain.name}</b> | 🥈 <b>النائب:</b> <b>{lineup.vice_captain.name}</b>

🔄 <b>التنقلات المعتمدة:</b>
{trans_str}
━━━━━━━━━━━━━━━━━━━━
🧠 <b>الرؤية التكتيكية للمدير الفني:</b>
{clean_briefing}"""

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🌐 فتح الداشبورد المباشر", "url": "https://fantasy-ai-dashboard.pages.dev/"}
                ],
                [
                    {"text": "📊 حالة الفريق", "callback_data": "status"},
                    {"text": "🛡️ نبض الأمان T-20m", "callback_data": "safety"}
                ],
                [
                    {"text": "ℹ️ دليل استخدام البوت", "callback_data": "help"},
                    {"text": "🔙 🏠 القائمة الرئيسية", "callback_data": "main_menu"}
                ]
            ]
        }

        return self.send_message(card, reply_markup=reply_markup, parse_mode="HTML")
