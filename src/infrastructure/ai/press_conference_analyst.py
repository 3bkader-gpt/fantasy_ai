import logging
import json
import re
from typing import List, Dict, Any, Optional
import requests

from ...config import config
from .rate_limiter import GeminiRateLimiter

logger = logging.getLogger("PressConferenceAnalyst")


class PressConferenceAnalyst:
    """
    Analyzes Premier League press conferences, manager quotes, and official injury updates
    using Google Gemini to produce actionable expected minutes modifiers for the FPL solver.
    """

    def __init__(self, api_key: str = config.gemini_api_key, primary_model: str = config.gemini_model):
        self.api_key = api_key
        models = [
            primary_model,
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite"
        ]
        self.models = [m for m in dict.fromkeys(models) if m]
        self.rate_limiter = GeminiRateLimiter()

    def _call_gemini(self, prompt: str, system_instruction: str) -> Optional[str]:
        if not self.api_key:
            logger.warning("No GEMINI_API_KEY found. Skipping NLP press conference analysis.")
            return None

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,  # Low temperature for precise structured extraction
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json"
            }
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        for model in self.models:
            if not self.rate_limiter.can_call(model):
                continue

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            try:
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        usage = data.get("usageMetadata", {})
                        tokens = usage.get("totalTokenCount", 0)
                        self.rate_limiter.record_call(model, total_tokens=tokens)
                        return candidates[0]["content"]["parts"][0]["text"]
                logger.warning(f"Model {model} returned status {res.status_code}: {res.text[:120]}")
            except Exception as e:
                logger.warning(f"Gemini call to {model} failed: {e}")

        return None

    def analyze_news(
        self,
        news_articles: List[Dict[str, Any]],
        fpl_flags: List[Dict[str, Any]],
        tracked_players: List[Dict[str, Any]]
    ) -> Dict[int, Dict[str, Any]]:
        """
        Processes news articles and FPL injury flags against tracked players.
        Returns a mapping of player_id -> NLP insight dictionary.
        """
        if not self.api_key:
            logger.info("Skipping press conference analysis: API key not configured.")
            return {}

        if not tracked_players:
            return {}

        # Limit to the most relevant items to save tokens
        articles_snippet = [
            {
                "title": a.get("title"),
                "summary": a.get("summary"),
                "date": a.get("date"),
                "matched_players": a.get("matched_players", [])
            }
            for a in news_articles[:15]
        ]

        players_context = [
            {
                "id": p.get("id"),
                "name": p.get("web_name"),
                "team": p.get("team_name") or p.get("team"),
                "status": p.get("status"),
                "fpl_chance": p.get("chance_of_playing_next_round")
            }
            for p in tracked_players
        ]

        system_instruction = (
            "You are Pep Guardiola's Chief Sports Science & Tactical Intelligence Officer for FPL.\n"
            "Your job is to read real Premier League press conference quotes, injury updates, and team news, "
            "and determine the exact impact on each tracked player's expected minutes and availability for the upcoming Gameweek.\n"
            "Output MUST be strict JSON adhering to the specified schema without any markdown wrapping."
        )

        prompt = (
            f"Here are the tracked players in our FPL squad and watchlist:\n"
            f"{json.dumps(players_context, ensure_ascii=False, indent=2)}\n\n"
            f"Here are the latest official Premier League news and press conference articles:\n"
            f"{json.dumps(articles_snippet, ensure_ascii=False, indent=2)}\n\n"
            f"Here are the official FPL status flags:\n"
            f"{json.dumps(fpl_flags[:20], ensure_ascii=False, indent=2)}\n\n"
            "INSTRUCTIONS:\n"
            "1. For each tracked player mentioned or affected by the news or flags, evaluate their likelihood of starting and minutes.\n"
            "2. If a player is fully fit with no rotation/injury concern mentioned, you don't need to include them, OR assign multiplier 1.0.\n"
            "3. Assign a 'minute_multiplier' between 0.0 and 1.0:\n"
            "   - 1.0: 100% expected starter (~80-90 mins)\n"
            "   - 0.85: High chance of starting but might be subbed early around 65-70 mins\n"
            "   - 0.50: 50/50 toss-up, bench cameo or managed minutes\n"
            "   - 0.20: High doubt, improbable start, likely 10-15 min cameo or rest\n"
            "   - 0.0: Ruled out, injured, transferred, or suspended\n"
            "4. Provide a clear, professional Arabic tactical summary ('summary_ar') and English ('summary_en').\n"
            "5. Assign 'risk_level': 'LOW', 'MEDIUM', 'HIGH', or 'CRITICAL'.\n\n"
            "Return a JSON array of objects with the following keys:\n"
            "[\n"
            "  {\n"
            "    \"player_id\": int,\n"
            "    \"player_name\": str,\n"
            "    \"fitness_sentiment\": \"fit_starter\" | \"managed_minutes\" | \"minor_doubt\" | \"major_doubt\" | \"ruled_out\",\n"
            "    \"minute_multiplier\": float,\n"
            "    \"summary_ar\": str,\n"
            "    \"summary_en\": str,\n"
            "    \"risk_level\": \"LOW\" | \"MEDIUM\" | \"HIGH\" | \"CRITICAL\",\n"
            "    \"headline_reference\": str\n"
            "  }\n"
            "]"
        )

        response_text = self._call_gemini(prompt, system_instruction)
        if not response_text:
            return {}

        try:
            # Clean possible markdown formatting if any
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            parsed_list = json.loads(cleaned)
            insights_by_id = {}
            if isinstance(parsed_list, list):
                for item in parsed_list:
                    pid = item.get("player_id")
                    if pid is not None:
                        # Sanitize minute_multiplier to [0.0, 1.0]
                        mult = item.get("minute_multiplier", 1.0)
                        try:
                            mult = max(0.0, min(1.0, float(mult)))
                        except (ValueError, TypeError):
                            mult = 1.0
                        item["minute_multiplier"] = mult
                        insights_by_id[int(pid)] = item

            logger.info(f"Generated {len(insights_by_id)} NLP press conference player insights.")
            return insights_by_id

        except Exception as e:
            logger.error(f"Failed to parse Gemini NLP response: {e}\nRaw output: {response_text[:300]}")
            return {}
