import logging
from typing import List, Dict, Any, Optional
import requests

from ...domain.interfaces.ai_advisor import IAIAdvisor
from ...domain.models.player import Player
from ...domain.models.transfer import Transfer
from ...domain.models.squad import LineupSelection
from ...config import config

from .rate_limiter import GeminiRateLimiter

logger = logging.getLogger("GeminiAdvisor")


class GeminiAdvisor(IAIAdvisor):
    """Provides tactical reasoning and generates Arabic manager briefings using Google Gemini."""

    def __init__(self, api_key: str = config.gemini_api_key, primary_model: str = config.gemini_model):
        self.api_key = api_key
        # Order fallback models from newest to oldest
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

    def _call_gemini(self, prompt: str, system_instruction: str) -> str:
        if not self.api_key:
            return "⚠️ لم يتم ضبط GEMINI_API_KEY في ملف .env. تم تخطي تقرير الذكاء الاصطناعي."

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048}
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        last_error = ""
        for model in self.models:
            if not self.rate_limiter.can_call(model):
                logger.info(f"Skipping model {model} due to rate limits quota.")
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
                        logger.info(f"Logged Gemini usage for {model}: {tokens} tokens. Quota updated.")
                        return candidates[0]["content"]["parts"][0]["text"]
                last_error = f"Model {model} returned {res.status_code}: {res.text[:120]}"
            except Exception as e:
                last_error = f"{model} error: {e}"
                logger.warning(last_error)

        return f"⚠️ تعذر الاتصال بـ Gemini API: {last_error}"

    def generate_briefing(
        self,
        gw: int,
        deadline: Optional[str],
        current_squad: List[Player],
        recommended_transfers: List[Transfer],
        lineup: LineupSelection,
        points_gain: float,
        hits_cost: int,
        bank: float,
        rank: Optional[int] = None,
        chips_available: Optional[Dict[str, int]] = None,
        chip_recommendation: Optional[Dict[str, Any]] = None,
        market_trends: Optional[List[Player]] = None,
        leagues: Optional[List[Dict[str, Any]]] = None,
        gold_rules: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        posture = (
            f"DEFENSIVE - تأمين الترتيب ({rank:,})" if rank and rank < 50000 else
            f"AGGRESSIVE - هجومي تعويضي ({rank:,})" if rank and rank > 500000 else
            f"BALANCED - متوازن ({rank:,})" if rank else "BALANCED - متوازن لتعظيم النقاط"
        )

        system_instruction = (
            "أنت الخبير والمدير الفني الأعلى كفاءة لفريق فانتازي الدوري الإنجليزي (Elite Autonomous FPL AI Manager).\n"
            "تعتمد على أحدث التحليلات الإحصائية (xP + FDR) والبرمجة الرياضية ومحرك القواعد الذهبية التاريخية (Hindsight Gold Rules Engine).\n"
            "مبادئك: 'Points are Points'، بيع اللاعبين المتراجعين بلا عواطف، الجرأة المحسوبة في أخذ الـ Hits إذا أثبتت القواعد الذهبية جدواها (+6.8 net gain)، وتفضيل الكباتن ذوي السقف العالي وفقاً للأنماط التاريخية المثبتة.\n"
            "أسلوبك حاسم، تحليلي، عميق، ومحفز باللغة العربية الفصحى الأنيقة."
        )

        transfers_desc = []
        if recommended_transfers:
            for t in recommended_transfers:
                p_out, p_in = t.player_out, t.player_in
                transfers_desc.append(
                    f"- 🔴 بيع: {p_out.name} ({p_out.position} - {p_out.team_short}) [xP: {p_out.xp:.1f}] ──► "
                    f"🟢 شراء: {p_in.name} ({p_in.position} - {p_in.team_short}) [xP: {p_in.xp:.1f} | جدول: {p_in.horizon_fixtures} | £{p_in.cost}m]"
                )
        else:
            transfers_desc.append("لا توجد تبديلات مطلوبة لهذه الجولة (الحفاظ على التشكيلة وترحيل التبديل المجاني).")

        flagged = [p for p in current_squad if not p.is_available]
        injuries_desc = [f"- ⚠️ {p.name} ({p.team_short}): الحالة '{p.status}' - {p.news or 'لا تفاصيل'}" for p in flagged]

        chips_str = ""
        if chips_available:
            avail = [f"{k}: {v}" for k, v in chips_available.items() if v > 0]
            chips_str = f"الخواص المتاحة: {', '.join(avail) if avail else 'مستهلكة بالكامل'}\n"
        if chip_recommendation and chip_recommendation.get("chip_recommendations"):
            recs = [f"- خاصية {r['chip']}: {r['reason']} (الثقة: {r['confidence']})" for r in chip_recommendation["chip_recommendations"]]
            chips_str += "توصيات الخواص:\n" + "\n".join(recs)
        else:
            chips_str += "توصية الخواص: الاحتفاظ بها للجولات المزدوجة (DGW)."

        market_str = ""
        if market_trends:
            diffs = [p.name for p in market_trends if p.is_differential][:3]
            flops = [p.name for p in market_trends if p.is_flop_risk][:3]
            if diffs: market_str += f"- Differentials واعدة: {', '.join(diffs)}\n"
            if flops: market_str += f"- مخاطر Flop تجنبها أو بادر ببيعها: {', '.join(flops)}\n"

        gold_rules_str = ""
        if gold_rules:
            rules_formatted = []
            for r in gold_rules:
                cat = r.get("category", "").upper()
                text = r.get("rule_text", "")
                conf = r.get("confidence", 0.0)
                rules_formatted.append(f"  • [{cat}] {text} (نسبة الثقة: {conf*100:.0f}%)")
            gold_rules_str = "\n".join(rules_formatted)

        prompt = f"""
تحليل خطة الجولة رقم {gw}:
- استراتيجية الترتيب: {posture} | الديدلاين: {deadline or 'قريباً'}
- الرصيد: £{bank:.1f}m | تكلفة التبديلات: -{hits_cost} نقطة | صافي الزيادة المتوقعة: +{points_gain:.2f} نقطة

القواعد الذهبية المستخرجة من محرك الـ Hindsight التاريخي:
{gold_rules_str or 'لا توجد قواعد تاريخية محملة.'}

قرارات التبديل:
{chr(10).join(transfers_desc)}

تقرير الغيابات:
{chr(10).join(injuries_desc) if injuries_desc else 'لا توجد غيابات مقلقة.'}

شارة القيادة:
- الكابتن (C): {lineup.captain.name} ({lineup.captain.team_short}) - xP: {lineup.captain.xp:.1f}
- النائب (VC): {lineup.vice_captain.name} ({lineup.vice_captain.team_short}) - xP: {lineup.vice_captain.xp:.1f}

التشكيل الأساسي ({lineup.formation}):
{', '.join([f"{p.name} ({p.team_short})" for p in lineup.starting_xi])}

استراتيجية الخواص:
{chips_str}

رادار السوق:
{market_str or 'السوق مستقر.'}

المطلوب:
اكتب تقريراً تكتيكياً شاملاً ومقنعاً باللغة العربية يشمل:
1. التكتيك المعتمد وموقف الترتيب.
2. مدى مطابقة القرارات للقواعد الذهبية (Gold Rules Compliance): حلل وبرهن صراحة كيف يتوافق قرار التبديل، وجدوى السالب (-4 Hit)، واختيار الكابتن، وتشكيل خط الوسط مع القواعد التاريخية المثبتة.
3. التحليل الرياضي والتكتيكي للتبديلات وتبرير بيع اللاعبين وشراء البدلاء وجدوى الـ Hit إن وجد على مدى 3 جولات.
4. مبررات شارة القيادة (C) والنائب (VC) بالاستناد إلى قاعدة الكابتن الذهبية.
5. نصيحة استراتيجية الخواص وحماية ميزانية الفريق.
"""
        return self._call_gemini(prompt, system_instruction)
