import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from ..application.dtos.gameweek_dto import GameweekPlanDTO
from .league_radar import LeagueRadarService

logger = logging.getLogger("DashboardExporter")


class DashboardExporter:
    """Exports gameweek optimization DTO and squad state into JSON for Cloudflare Pages."""

    @staticmethod
    def _player_to_dict(p, is_c: bool = False, is_vc: bool = False) -> Dict[str, Any]:
        return {
            "id": p.id,
            "name": p.name,
            "team": p.team_short,
            "position": p.position,
            "cost": getattr(p, "cost", 0.0),
            "xp": round(float(p.xp), 1),
            "horizon_xp": round(float(getattr(p, "horizon_xp", p.xp)), 1),
            "fixture": getattr(p, "next_fixture", ""),
            "expected_minutes": getattr(p, "expected_minutes", 90),
            "is_captain": is_c,
            "is_vice_captain": is_vc,
            "fixtures_5gw": getattr(p, "fixtures_5gw", []),
            "press_insight": getattr(p, "press_insight", None)
        }


    def export(self, dto: GameweekPlanDTO, output_path: str = "dashboard/data/squad_data.json") -> str:
        lineup = dto.plan.final_lineup
        cap_id = lineup.captain.id if lineup.captain else None
        vc_id = lineup.vice_captain.id if lineup.vice_captain else None

        starters = [
            self._player_to_dict(p, is_c=(p.id == cap_id), is_vc=(p.id == vc_id))
            for p in lineup.starting_xi
        ]
        bench = [
            self._player_to_dict(p, is_c=False, is_vc=False)
            for p in lineup.bench
        ]

        transfers = []
        if dto.plan.transfers:
            for t in dto.plan.transfers:
                transfers.append({
                    "player_out": {"name": t.player_out.name, "team": t.player_out.team_short, "xp": round(float(t.player_out.xp), 1)},
                    "player_in": {"name": t.player_in.name, "team": t.player_in.team_short, "cost": t.player_in.cost, "xp": round(float(t.player_in.xp), 1)}
                })

        # Curated market candidates for What-If simulator (Top 20 per position)
        candidates = []
        if getattr(dto, "all_players", None):
            by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
            for p in dto.all_players:
                if p.is_available and p.xp > 0 and p.position in by_pos:
                    by_pos[p.position].append(p)
            for pos, plist in by_pos.items():
                plist.sort(key=lambda x: (x.xp, x.horizon_xp), reverse=True)
                for p in plist[:20]:
                    candidates.append({
                        "id": p.id,
                        "name": p.name,
                        "team": p.team_short,
                        "position": p.position,
                        "cost": getattr(p, "cost", 0.0),
                        "xp": round(float(p.xp), 1),
                        "horizon_xp": round(float(getattr(p, "horizon_xp", p.xp)), 1),
                        "fixture": getattr(p, "next_fixture", ""),
                        "fixtures_5gw": getattr(p, "fixtures_5gw", [])
                    })

        raw_leagues = getattr(dto, "leagues", None) or []

        radar_data = LeagueRadarService.generate_radar_data(lineup.starting_xi + lineup.bench, raw_leagues)

        data = {
            "meta": {
                "manager_name": dto.manager_name or "Pep GPT",
                "team_name": dto.team_name or "هبد اصطناعي",
                "gameweek": dto.gameweek,
                "deadline": dto.deadline or "2026-09-12T12:30:00Z",
                "rank": dto.rank or 0,
                "total_points": dto.total_points or 0,
                "team_value": round(float(dto.team_value), 1),
                "bank": round(float(dto.bank), 1),
                "free_transfers": dto.free_transfers,
                "dry_run": dto.dry_run,
                "last_updated": datetime.utcnow().isoformat() + "Z"
            },
            "formation": lineup.formation,
            "total_xp": round(float(lineup.total_expected_points), 1),
            "captain": self._player_to_dict(lineup.captain, is_c=True) if lineup.captain else None,
            "vice_captain": self._player_to_dict(lineup.vice_captain, is_vc=True) if lineup.vice_captain else None,
            "starters": starters,
            "bench": bench,
            "transfers": transfers,
            "market_candidates": candidates,
            "briefing": dto.briefing,
            "leagues": radar_data["leagues"],
            "eo_radar": radar_data,
            "press_insights": getattr(dto, "press_conference_insights", None) or [
                p.get("press_insight") for p in (starters + bench) if p.get("press_insight")
            ],
            "press_wire": getattr(dto, "press_wire", [])
        }



        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Dashboard data exported successfully to {output_path}")
        return output_path
