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
        chips_available: Dict[str, int],
        next_gw: int = 1
    ) -> Dict[str, Any]:
        recs: List[Dict[str, Any]] = []
        bench_xp = sum(p.xp for p in lineup.bench)
        captain_xp = lineup.captain.xp

        # Half-season expiration awareness (GW1-19 first half, GW20-38 second half)
        half_end_gw = 19 if next_gw <= 19 else 38
        gws_remaining = max(1, half_end_gw - next_gw + 1)

        # Count chips still available for this half
        avail_names = [
            c for c in ("bboost", "3xc", "freehit", "wildcard")
            if chips_available.get(c, 0) > 0
        ]
        # Urgency mode: remaining GWs in half <= remaining chips + 1 (use-it-or-lose-it)
        urgent = len(avail_names) > 0 and gws_remaining <= (len(avail_names) + 1)

        # 1. Bench Boost
        if chips_available.get("bboost", 0) > 0:
            bb_threshold = 10.0 if urgent else 14.0
            min_bench_player = 1.5 if urgent else 2.5
            if bench_xp >= bb_threshold and all(p.xp >= min_bench_player for p in lineup.bench):
                recs.append({
                    "chip": ChipType.BENCH_BOOST.value,
                    "reason": (
                        f"قوة دكة البدلاء ({bench_xp:.1f} xP)"
                        + (f" مع اقتراب انتهاء خواص النصف الأول عند GW{half_end_gw} (متبقي {gws_remaining} جولات)." if urgent else " استثنائية، مما يجعل تفعيل Bench Boost فرصة ذهبية.")
                    ),
                    "confidence": "HIGH",
                    "urgent": urgent,
                    "auto_safe": True
                })

        # 2. Triple Captain
        if chips_available.get("3xc", 0) > 0:
            tc_threshold = 7.5 if urgent else 9.0
            if captain_xp >= tc_threshold:
                recs.append({
                    "chip": ChipType.TRIPLE_CAPTAIN.value,
                    "reason": (
                        f"الكابتن {lineup.captain.name} يملك نقاط متوقعة عالية ({captain_xp:.1f} xP)"
                        + (f" ومع اقتراب انتهاء خواص النصف عند GW{half_end_gw} (متبقي {gws_remaining} جولات) يُنصح بتفعيل Triple Captain." if urgent else " في مواجهة سهلة أو جولة مزدوجة (DGW).")
                    ),
                    "confidence": "HIGH" if (captain_xp >= 9.5 or urgent) else "MEDIUM",
                    "urgent": urgent,
                    "auto_safe": True
                })

        # 3. Free Hit / Wildcard
        unfit_count = sum(1 for p in squad_15 if not p.is_available)
        blank_count = sum(1 for p in squad_15 if p.next_fixture == "BLANK")

        if chips_available.get("freehit", 0) > 0 and (blank_count >= 4 or (unfit_count + blank_count) >= 5):
            recs.append({
                "chip": ChipType.FREE_HIT.value,
                "reason": f"لديك {blank_count} لاعبين في جولة فراغ (Blank) أو مصابين. تفعيل Free Hit ينقذ جولتك دون المساس بهيكل الفريق المستقبلي.",
                "confidence": "VERY HIGH",
                "urgent": urgent,
                "auto_safe": False
            })

        if chips_available.get("wildcard", 0) > 0 and (unfit_count >= 4 or (urgent and gws_remaining <= 2)):
            recs.append({
                "chip": ChipType.WILDCARD.value,
                "reason": (
                    f"تبقى {gws_remaining} جولات فقط على انتهاء Wildcard النصف الأول (GW{half_end_gw}) — يُنصح بتفعيلها لإعادة هيكلة التشكيلة مجاناً."
                    if urgent and unfit_count < 4
                    else f"الفريق يعاني من {unfit_count} إصابات وغيابات حرجة. تفعيل Wildcard لإعادة بناء التشكيلة مجاناً هو الإجراء الأمثل."
                ),
                "confidence": "HIGH",
                "urgent": urgent,
                "auto_safe": False
            })

        # Determine if a safe chip (bboost / 3xc) should be auto-activated on set_lineup
        auto_activate_chip = None
        for r in recs:
            if r.get("auto_safe") and (r.get("confidence") == "HIGH" or r.get("urgent")):
                auto_activate_chip = r["chip"]
                break

        return {
            "recommended_chip": recs[0]["chip"] if recs else None,
            "auto_activate_chip": auto_activate_chip,
            "gws_remaining_in_half": gws_remaining,
            "urgent_window": urgent,
            "chip_recommendations": recs
        }
