import logging
from typing import List
import requests

from ...domain.interfaces.notifier import INotifier
from ...domain.models.transfer import Transfer
from ...domain.models.squad import LineupSelection
from ...config import config

logger = logging.getLogger("TelegramNotifier")


class TelegramNotifier(INotifier):
    """Sends tactical briefings and transfer alerts directly to Telegram."""

    def __init__(self, token: str = config.telegram_bot_token, chat_id: str = config.telegram_chat_id):
        self.token = token.strip() if token else ""
        self.chat_id = chat_id.strip() if chat_id else ""
        self.is_configured = bool(self.token and self.chat_id)

    def send_message(self, text: str) -> bool:
        if not self.is_configured:
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        success = True

        for chunk in chunks:
            payload = {"chat_id": self.chat_id, "text": chunk, "parse_mode": "Markdown", "disable_web_page_preview": True}
            try:
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code != 200:
                    payload.pop("parse_mode", None)
                    requests.post(url, json=payload, timeout=10)
            except Exception as e:
                logger.warning(f"Error sending Telegram notification: {e}")
                success = False

        return success

    def send_gameweek_summary(
        self,
        gw: int,
        transfers: List[Transfer],
        lineup: LineupSelection,
        briefing_text: str,
        dry_run: bool
    ) -> bool:
        mode_str = "🛡️ [وضع المحاكاة]" if dry_run else "🚀 [تنفيذ رسمي]"
        trans_str = ""
        if transfers:
            for t in transfers:
                trans_str += f"🔴 خروج: {t.player_out.name} ({t.player_out.team_short})\n"
                trans_str += f"🟢 دخول: {t.player_in.name} ({t.player_in.team_short}) [xP: {t.player_in.xp:.1f}]\n"
        else:
            trans_str = "🔄 ترحيل التبديل المجاني\n"

        card = (
            f"⚽ *تقرير مدير الفانتازي للجولة {gw}* 🤖\n"
            f"الحالة: {mode_str}\n"
            f"التشكيل: {lineup.formation}\n"
            f"👑 الكابتن: {lineup.captain.name} | 🥈 النائب: {lineup.vice_captain.name}\n\n"
            f"*التنقلات:*\n{trans_str}\n"
            f"------------------------------------\n"
            f"*التقرير التكتيكي:*\n{briefing_text}"
        )
        return self.send_message(card)
