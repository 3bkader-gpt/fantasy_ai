import os
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.run_hindsight import RunHindsightUseCase
from src.infrastructure.optimization.hindsight_solver import HindsightSolver
from src.infrastructure.analysis.gold_rule_extractor import GoldRuleExtractor
from src.presentation.hindsight_presenter import HindsightPresenter
from src.domain.models.hindsight_models import PlayerGameweekRecord


def create_synthetic_player_pool():
    player_points = {1: [], 2: []}
    specs = [
        (1, 1, 1, 5.0, 6, 2),
        (2, 1, 2, 4.5, 2, 7),
        (3, 1, 3, 4.0, 0, 0),
        (4, 2, 1, 5.5, 8, 2),
        (5, 2, 2, 5.0, 6, 6),
        (6, 2, 3, 4.5, 2, 9),
        (7, 2, 4, 4.5, 5, 2),
        (8, 2, 5, 4.0, 1, 1),
        (9, 2, 6, 4.0, 0, 8),
        (10, 2, 7, 4.0, 0, 0),
        (11, 3, 1, 10.0, 15, 3),
        (12, 3, 2, 8.5, 7, 12),
        (13, 3, 3, 7.0, 5, 5),
        (14, 3, 4, 6.0, 6, 2),
        (15, 3, 5, 5.5, 3, 10),
        (16, 3, 6, 4.5, 2, 2),
        (17, 3, 7, 4.5, 1, 1),
        (18, 4, 1, 12.0, 13, 16),
        (19, 4, 2, 7.5, 8, 2),
        (20, 4, 3, 5.5, 2, 9),
        (21, 4, 4, 4.5, 1, 1),
    ]
    for p_id, pos, team, price, gw1_pts, gw2_pts in specs:
        for gw, pts in [(1, gw1_pts), (2, gw2_pts)]:
            player_points[gw].append(
                PlayerGameweekRecord(
                    player_id=p_id,
                    gameweek=gw,
                    total_points=pts,
                    minutes=90 if pts > 0 else 0,
                    goals_scored=1 if pts > 5 else 0,
                    assists=0,
                    clean_sheets=1 if pos <= 2 and pts >= 6 else 0,
                    bonus=3 if pts >= 10 else 0,
                    was_home=True if gw == 1 else False,
                    opponent_id=team + 1,
                    opponent_short="OPP",
                    fixture_difficulty=2 if gw == 1 else 3,
                    price=price,
                    element_type=pos,
                    web_name=f"Player_{p_id}",
                    team_id=team,
                )
            )
    return player_points


def test_hindsight_pipeline_end_to_end(tmp_path):
    """Test the full hindsight pipeline end-to-end with mock collector and file export."""
    synthetic_data = create_synthetic_player_pool()

    # Mock HistoricalDataCollector
    mock_collector = MagicMock()
    mock_collector.collect_range.return_value = synthetic_data

    # Mock FPLDataRepository
    mock_repo = MagicMock()
    mock_repo.get_current_and_next_gw.return_value = (2, 3, "2026-09-26T10:00:00Z")

    # Presenter pointing to tmp_path
    presenter = HindsightPresenter(default_output_dir=tmp_path)
    solver = HindsightSolver(time_limit_seconds=10.0)
    extractor = GoldRuleExtractor()

    use_case = RunHindsightUseCase(
        collector=mock_collector,
        solver=solver,
        extractor=extractor,
        presenter=presenter,
        repository=mock_repo,
    )

    result, rules, export_path = use_case.execute(
        gw_start=1,
        gw_end=2,
        initial_budget=100.0,
        export_json=True,
        output_filename="test_gold_rules.json",
    )

    # 1. Check Result
    assert result is not None
    assert result.gameweek_range == (1, 2)
    assert len(result.decisions) == 2
    assert result.total_points > 0

    # 2. Check Rules
    assert len(rules) > 0
    assert any(r.category == "captain" for r in rules)

    # 3. Check JSON Export
    assert export_path is not None
    assert export_path.exists()

    with open(export_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "summary" in data
    assert "gold_rules" in data
    assert "gameweeks" in data
    assert data["summary"]["total_net_points"] == result.total_points
    assert len(data["gameweeks"]) == 2
