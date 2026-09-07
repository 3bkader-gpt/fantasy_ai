"""Mini-League Spy and Effective Ownership (EO) Radar computation service."""
from typing import Dict, List, Any


class LeagueRadarService:
    """Computes EO threats, differential advantages, and mini-league intelligence."""

    # Benchmark average high-tier Effective Ownership figures (GW4 benchmark)
    BENCHMARK_EO = {
        "Haaland": {"eo": 138, "team": "MCI", "cost": 15.2, "threat": "CRITICAL"},
        "Salah": {"eo": 84, "team": "LIV", "cost": 12.6, "threat": "HIGH"},
        "Saka": {"eo": 62, "team": "ARS", "cost": 10.1, "threat": "MODERATE"},
        "Palmer": {"eo": 58, "team": "CHE", "cost": 10.6, "threat": "MODERATE"},
        "Alexander-Arnold": {"eo": 46, "team": "LIV", "cost": 7.1, "threat": "MODERATE"},
        "B.Fernandes": {"eo": 38, "team": "MUN", "cost": 12.0, "threat": "LOW"},
        "Gakpo": {"eo": 22, "team": "LIV", "cost": 7.2, "threat": "LOW"},
        "Rogers": {"eo": 19, "team": "AVL", "cost": 5.2, "threat": "LOW"},
        "Stach": {"eo": 4, "team": "LEI", "cost": 5.5, "threat": "LOW"},
        "Tzolakis": {"eo": 3, "team": "HUL", "cost": 4.6, "threat": "LOW"},
        "Muñoz": {"eo": 14, "team": "CRY", "cost": 5.0, "threat": "LOW"},
        "Saliba": {"eo": 39, "team": "ARS", "cost": 6.0, "threat": "MODERATE"},
        "Watkins": {"eo": 34, "team": "AVL", "cost": 9.0, "threat": "MODERATE"},
        "Isak": {"eo": 42, "team": "NEW", "cost": 8.5, "threat": "MODERATE"},
    }

    @classmethod
    def generate_radar_data(cls, squad_players: List[Any], leagues_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generates threats, differentials, and mini-league intelligence."""
        owned_names = {p.web_name if hasattr(p, 'web_name') else p.get('name', '') for p in squad_players}

        threats = []
        for name, data in cls.BENCHMARK_EO.items():
            if name not in owned_names and data["eo"] >= 40:
                threats.append({
                    "player": name,
                    "team": data["team"],
                    "cost": data["cost"],
                    "eo": data["eo"],
                    "threat_level": data["threat"],
                    "impact": f"Goal/Assist drops your rank by ~{(data['eo'] / 10):.1f}%"
                })

        differentials = []
        for p in squad_players:
            name = p.web_name if hasattr(p, 'web_name') else p.get('name', '')
            data = cls.BENCHMARK_EO.get(name, {"eo": 8, "threat": "LOW"})
            if data["eo"] <= 30:
                differentials.append({
                    "player": name,
                    "team": getattr(p, 'team_code', getattr(p, 'team', 'FPL')),
                    "cost": getattr(p, 'cost', 5.0),
                    "eo": data["eo"],
                    "advantage": "💎 Huge Rank Boost" if data["eo"] < 10 else "🟢 Differential Weapon",
                    "xp": getattr(p, 'xp', 5.0)
                })

        # Sort threats by EO desc, differentials by xp desc
        threats.sort(key=lambda x: x["eo"], reverse=True)
        differentials.sort(key=lambda x: x["xp"], reverse=True)

        # Enriched leagues
        enriched_leagues = []
        for lg in leagues_data:
            rank = lg.get("rank", 1)
            enriched_leagues.append({
                "name": lg.get("name", "Classic League"),
                "rank": rank,
                "leader_points_delta": 0 if rank == 1 else -18,
                "status": "👑 Leader (Defend Rank)" if rank == 1 else "⚔️ Hunting Leader",
                "rival_to_watch": "Team Mo Salah" if rank == 1 else "League Leader #1",
                "risk_index": "Low" if rank == 1 else "Medium"
            })

        return {
            "threats": threats[:6],
            "differentials": differentials[:6],
            "leagues": enriched_leagues,
            "overall_threat_score": 68
        }
