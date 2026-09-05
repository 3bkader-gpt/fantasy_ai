from typing import List, Dict, Any, Optional
from ...domain.models.player import Player
from ...domain.models.chip import ChipType, ChipRecommendation
from ...domain.models.squad import LineupSelection


class ChipEvaluator:
    """Evaluates squad health and projections to advise on chip activation."""

    def evaluate(
        self,
        squad_15: List[Player],
        lineup: LineupSelection,
        chips_available: Dict[str, int]
    ) -> Dict[str, Any]:
        recs: List[Dict[str, Any]] = []
        bench_xp = sum(p.xp for p in lineup.bench)
        captain_xp = lineup.captain.xp

        # 1. Bench Boost
        if chips_available.get("bboost", 0) > 0:
            if bench_xp >= 14.0 and all(p.xp >= 2.5 for p in lineup.bench):
                recs.append({
                    "chip": ChipType.BENCH_BOOST.value,
                    "reason": f"قوة دكة البدلاء استثنائية (مجموع نقاط متوقعة: {bench_xp:.1f} نقطة)، مما يجعل تفعيل Bench Boost فرصة ذهبية.",
                    "confidence": "HIGH"
                })

        # 2. Triple Captain
        if chips_available.get("3xc", 0) > 0:
            if captain_xp >= 10.5:
                recs.append({
                    "chip": ChipType.TRIPLE_CAPTAIN.value,
                    "reason": f"الكابتن {lineup.captain.name} يملك نقاط متوقعة خارقة ({captain_xp:.1f} xP) في مواجهة سهلة أو جولة مزدوجة (DGW). تفعيل Triple Captain خيار مطروح بقوة.",
                    "confidence": "HIGH" if captain_xp >= 12.0 else "MEDIUM"
                })

        # 3. Free Hit / Wildcard
        unfit_count = sum(1 for p in squad_15 if not p.is_available)
        blank_count = sum(1 for p in squad_15 if p.next_fixture == "BLANK")

        if chips_available.get("freehit", 0) > 0 and (blank_count >= 4 or (unfit_count + blank_count) >= 5):
            recs.append({
                "chip": ChipType.FREE_HIT.value,
                "reason": f"لديك {blank_count} لاعبين في جولة فراغ (Blank) أو مصابين. تفعيل Free Hit ينقذ جولتك دون المساس بهيكل الفريق المستقبلي.",
                "confidence": "VERY HIGH"
            })

        if chips_available.get("wildcard", 0) > 0 and unfit_count >= 4:
            recs.append({
                "chip": ChipType.WILDCARD.value,
                "reason": f"الفريق يعاني من {unfit_count} إصابات وغيابات حرجة. تفعيل Wildcard لإعادة بناء التشكيلة مجاناً هو الإجراء الأمثل.",
                "confidence": "HIGH"
            })

        return {
            "recommended_chip": recs[0]["chip"] if recs else None,
            "chip_recommendations": recs
        }
