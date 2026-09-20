import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from tabulate import tabulate

from ..domain.models.hindsight_models import (
    PlayerGameweekRecord,
    HindsightResult,
    GoldRule,
)

logger = logging.getLogger("HindsightPresenter")


class HindsightPresenter:
    """Presents hindsight optimization results via clean console summaries and structured JSON exports."""

    def __init__(self, default_output_dir: Optional[Path] = None):
        self.output_dir = default_output_dir or Path("output")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_json(
        self,
        result: HindsightResult,
        rules: List[GoldRule],
        player_points: Dict[int, List[PlayerGameweekRecord]],
        filename: str = "hindsight_gold_rules.json",
    ) -> Path:
        """Export the full hindsight solution and extracted Gold Rules to a JSON file."""
        # Index records for easy enrichment
        records_by_gw_player: Dict[tuple, PlayerGameweekRecord] = {}
        for gw, records in player_points.items():
            for r in records:
                records_by_gw_player[(gw, r.player_id)] = r

        enriched_decisions = []
        for d in result.decisions:
            gw = d.gameweek

            def enrich_player(p_id: int) -> Dict[str, Any]:
                rec = records_by_gw_player.get((gw, p_id))
                if rec:
                    return {
                        "id": p_id,
                        "name": rec.web_name,
                        "position": ["GK", "DEF", "MID", "FWD"][rec.element_type - 1] if 1 <= rec.element_type <= 4 else "UNK",
                        "price": rec.price,
                        "points": rec.total_points,
                        "was_home": rec.was_home,
                        "opponent": rec.opponent_short,
                        "fdr": rec.fixture_difficulty,
                    }
                return {"id": p_id, "name": f"Player {p_id}", "points": 0}

            cap_rec = records_by_gw_player.get((gw, d.captain_id))
            vc_rec = records_by_gw_player.get((gw, d.vice_captain_id))

            decision_dict = {
                "gameweek": gw,
                "formation": d.formation,
                "gross_points": d.gross_points,
                "hit_cost": d.hit_cost,
                "net_points": d.total_points,
                "hits_taken": d.hits_taken,
                "bank": d.bank,
                "team_value": d.team_value,
                "captain": {
                    "id": d.captain_id,
                    "name": cap_rec.web_name if cap_rec else f"Player {d.captain_id}",
                    "points": cap_rec.total_points if cap_rec else 0,
                    "effective_points": (cap_rec.total_points * 2) if cap_rec else 0,
                },
                "vice_captain": {
                    "id": d.vice_captain_id,
                    "name": vc_rec.web_name if vc_rec else f"Player {d.vice_captain_id}",
                    "points": vc_rec.total_points if vc_rec else 0,
                },
                "starting_xi": [enrich_player(p) for p in d.starting_xi],
                "bench": [enrich_player(p) for p in d.bench],
                "transfers_in": [enrich_player(p) for p in d.transfers_in],
                "transfers_out": [enrich_player(p) for p in d.transfers_out],
            }
            enriched_decisions.append(decision_dict)

        export_data = {
            "summary": {
                "gameweek_range": list(result.gameweek_range),
                "total_net_points": result.total_points,
                "total_hits": result.total_hits,
                "total_hit_cost": result.total_hit_cost,
                "gameweeks_count": len(result.decisions),
                "average_points_per_gw": round(result.total_points / max(1, len(result.decisions)), 1),
            },
            "gold_rules": [r.to_dict() for r in rules],
            "gameweeks": enriched_decisions,
        }

        output_path = self.output_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Hindsight results exported to: {output_path.resolve()}")
        return output_path

    def print_summary(
        self,
        result: HindsightResult,
        rules: List[GoldRule],
        player_points: Dict[int, List[PlayerGameweekRecord]],
    ) -> None:
        """Print a formatted console overview of optimal gameweeks and gold rules."""
        records_by_gw_player: Dict[tuple, PlayerGameweekRecord] = {}
        for gw, records in player_points.items():
            for r in records:
                records_by_gw_player[(gw, r.player_id)] = r

        print("\n" + "=" * 90)
        print("🏆 HINDSIGHT OPTIMIZATION ENGINE — ABSOLUTE MAXIMUM POINT PATH")
        print("=" * 90)

        gw_rows = []
        for d in result.decisions:
            cap_rec = records_by_gw_player.get((d.gameweek, d.captain_id))
            cap_str = f"{cap_rec.web_name if cap_rec else d.captain_id} ({cap_rec.total_points * 2 if cap_rec else 0}p)"

            tin_names = []
            for p in d.transfers_in:
                r = records_by_gw_player.get((d.gameweek, p))
                tin_names.append(r.web_name if r else str(p))

            tout_names = []
            for p in d.transfers_out:
                r = records_by_gw_player.get((d.gameweek, p))
                tout_names.append(r.web_name if r else str(p))

            transfers_str = ""
            if tin_names or tout_names:
                transfers_str = f"+{','.join(tin_names)} / -{','.join(tout_names)}"
            else:
                transfers_str = "None"

            gw_rows.append([
                f"GW{d.gameweek}",
                d.formation,
                cap_str,
                transfers_str[:28] + ("..." if len(transfers_str) > 28 else ""),
                f"-{d.hit_cost}" if d.hit_cost > 0 else "0",
                f"£{d.bank:.1f}m",
                d.gross_points,
                f"🎯 {d.total_points}",
            ])

        print(
            tabulate(
                gw_rows,
                headers=["GW", "Form", "Captain (2x)", "Transfers (In/Out)", "Hits", "Bank", "Gross", "Net Pts"],
                tablefmt="rounded_grid",
            )
        )

        print(f"\n📊 TOTAL NET POINTS: {result.total_points} pts across {len(result.decisions)} Gameweeks")
        print(f"📉 TOTAL HITS: {result.total_hits} (-{result.total_hit_cost} pts)")
        print(f"⚡ AVERAGE PER GW: {result.total_points / max(1, len(result.decisions)):.1f} pts/GW\n")

        print("=" * 90)
        print("✨ EXTRACTED GOLD RULES (WINNING STATISTICAL HEURISTICS)")
        print("=" * 90)

        rule_rows = []
        for r in rules:
            rule_rows.append([
                r.category.upper().replace("_", " "),
                r.rule_text,
                f"{r.confidence * 100:.0f}%",
                f"GWs: {','.join(map(str, r.evidence_gws))}",
            ])

        print(
            tabulate(
                rule_rows,
                headers=["Category", "Discovered Rule", "Confidence", "Evidence"],
                tablefmt="rounded_grid",
                maxcolwidths=[18, 48, 12, 14],
            )
        )
        print("=" * 90 + "\n")
