import pytest
from src.domain.models.hindsight_models import (
    PlayerGameweekRecord,
    HindsightGameweekDecision,
    HindsightResult,
)
from src.infrastructure.analysis.gold_rule_extractor import GoldRuleExtractor


def test_gold_rule_extractor():
    """Verify that GoldRuleExtractor correctly identifies patterns in optimal decisions."""
    # Synthetic records
    records_gw1 = [
        PlayerGameweekRecord(1, 1, 6, 90, 0, 0, 1, 0, True, 2, "CHE", 2, 5.0, 1, "Raya", 1),
        PlayerGameweekRecord(4, 1, 6, 90, 0, 0, 1, 0, True, 2, "CHE", 2, 5.5, 2, "Saliba", 1),
        PlayerGameweekRecord(5, 1, 6, 90, 0, 0, 1, 0, True, 2, "CHE", 2, 5.0, 2, "Gabriel", 1),
        PlayerGameweekRecord(6, 1, 2, 90, 0, 0, 0, 0, True, 3, "LIV", 3, 4.5, 2, "Konsa", 2),
        PlayerGameweekRecord(11, 1, 15, 90, 2, 1, 0, 3, True, 2, "CHE", 2, 12.5, 3, "Salah", 3),
        PlayerGameweekRecord(12, 1, 10, 90, 1, 1, 0, 2, True, 2, "CHE", 2, 8.5, 3, "Saka", 1),
        PlayerGameweekRecord(13, 1, 7, 90, 1, 0, 0, 1, True, 2, "CHE", 2, 7.0, 3, "Palmer", 4),
        PlayerGameweekRecord(14, 1, 5, 90, 0, 1, 0, 0, True, 2, "CHE", 2, 6.0, 3, "Gordon", 5),
        PlayerGameweekRecord(15, 1, 6, 90, 0, 1, 0, 0, True, 2, "CHE", 2, 5.5, 3, "Rogers", 2),
        PlayerGameweekRecord(18, 1, 13, 90, 2, 0, 0, 3, True, 2, "CHE", 2, 15.0, 4, "Haaland", 6),
        PlayerGameweekRecord(19, 1, 8, 90, 1, 0, 0, 1, True, 2, "CHE", 2, 7.5, 4, "Isak", 5),
        # Bench
        PlayerGameweekRecord(2, 1, 2, 0, 0, 0, 0, 0, False, 2, "CHE", 2, 4.5, 1, "BenchGK", 7),
        PlayerGameweekRecord(7, 1, 1, 0, 0, 0, 0, 0, False, 2, "CHE", 2, 4.0, 2, "BenchDef1", 8),
        PlayerGameweekRecord(8, 1, 1, 0, 0, 0, 0, 0, False, 2, "CHE", 2, 4.0, 2, "BenchDef2", 9),
        PlayerGameweekRecord(20, 1, 1, 0, 0, 0, 0, 0, False, 2, "CHE", 2, 4.5, 4, "BenchFwd", 10),
    ]

    player_points = {1: records_gw1}

    decision = HindsightGameweekDecision(
        gameweek=1,
        squad_15=[1, 4, 5, 6, 11, 12, 13, 14, 15, 18, 19, 2, 7, 8, 20],
        starting_xi=[1, 4, 5, 6, 11, 12, 13, 14, 15, 18, 19],
        bench=[2, 7, 8, 20],
        captain_id=11,  # Salah (MID, £12.5m, Home, FDR 2)
        formation="3-5-2",
        transfers_in=[],
        transfers_out=[],
        hits_taken=0,
        hit_cost=0,
        gross_points=100,
        total_points=100,
        bank=0.5,
        team_value=99.5,
    )

    result = HindsightResult(
        gameweek_range=(1, 1),
        decisions=[decision],
        total_points=100,
        total_hits=0,
        total_hit_cost=0,
    )

    extractor = GoldRuleExtractor()
    rules = extractor.extract(result, player_points)

    assert len(rules) > 0
    categories = {r.category for r in rules}

    # Verify categories extracted
    assert "captain" in categories
    assert "formation" in categories
    assert "position_allocation" in categories
    assert "fixture_context" in categories
    assert "price_efficiency" in categories

    # Verify formation rule
    formation_rule = next(r for r in rules if r.category == "formation")
    assert "3-5-2" in formation_rule.rule_text
    assert formation_rule.confidence == 1.0

    # Verify captain rule
    captain_rules = [r for r in rules if r.category == "captain"]
    assert any("MID/FWD" in r.rule_text for r in captain_rules)
