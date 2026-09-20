import sys
import argparse
import logging
import warnings

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

warnings.filterwarnings("ignore")

from src.config import config
from src.infrastructure.fpl import FPLDataRepository, FPLClient
from src.infrastructure.xp import RuleBasedXPEngine
from src.infrastructure.optimization import SquadOptimizer
from src.infrastructure.ai import GeminiAdvisor
from src.infrastructure.notifications import TelegramNotifier
from src.application.use_cases import (
    OptimizeGameweekUseCase,
    BuildInitialSquadUseCase,
    RunHindsightUseCase,
)
from src.presentation import ConsolePresenter, DashboardExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)


def run_hindsight(gw_start: int = 1, gw_end: int = None, budget: float = 100.0, output_json: str = "hindsight_gold_rules.json"):
    """Runs the Hindsight Optimization Engine to discover the absolute maximum point path and Gold Rules."""
    use_case = RunHindsightUseCase()
    result, rules, export_path = use_case.execute(
        gw_start=gw_start,
        gw_end=gw_end,
        initial_budget=budget,
        export_json=True,
        output_filename=output_json,
    )
    return result, rules, export_path


def run_manager(team_id: int, dry_run: bool, max_hits: int, apply_gold_rules: bool = True):
    """Composition Root: Wires dependencies and runs the gameweek optimization use case."""
    # 1. Instantiate Adapters (Infrastructure)
    repository = FPLDataRepository()
    gateway = FPLClient(dry_run=dry_run)
    xp_engine = RuleBasedXPEngine()
    advisor = GeminiAdvisor()
    notifier = TelegramNotifier()

    gold_rule_config = None
    if apply_gold_rules:
        from src.infrastructure.analysis import load_gold_rule_config
        gold_rule_config = load_gold_rule_config("output/hindsight_gold_rules.json")

    # 2. Inject into Use Case (Application)
    use_case = OptimizeGameweekUseCase(
        repository=repository,
        fpl_gateway=gateway,
        xp_engine=xp_engine,
        optimizer_factory=lambda players, gold_rule_config=None: SquadOptimizer(players, gold_rule_config=gold_rule_config),
        ai_advisor=advisor,
        notifier=notifier,
        gold_rule_config=gold_rule_config
    )

    # 3. Execute
    dto = use_case.execute(
        team_id=team_id,
        dry_run=dry_run,
        max_hits=max_hits,
        horizon_weeks=config.horizon_weeks,
        horizon_decay=config.horizon_decay
    )

    # 4. Present & Export
    ConsolePresenter().display_plan(dto)
    DashboardExporter().export(dto)
    return dto


def run_build_squad(budget: float = 100.0, min_chance: int = config.min_starter_chance):
    """Builds optimal initial 15-man squad for £100m using Two-Tier MILP and E[Min] model."""
    repository = FPLDataRepository()
    xp_engine = RuleBasedXPEngine()
    advisor = GeminiAdvisor()

    use_case = BuildInitialSquadUseCase(
        repository=repository,
        xp_engine=xp_engine,
        advisor=advisor
    )
    dto = use_case.execute(
        budget=budget,
        horizon_weeks=config.horizon_weeks,
        horizon_decay=config.horizon_decay,
        min_starter_chance=min_chance
    )
    ConsolePresenter().display_initial_squad(dto)
    return dto


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FPL Autonomous AI Manager")
    parser.add_argument("--team-id", type=int, default=config.fpl_team_id, help="FPL Team ID")
    parser.add_argument("--live", action="store_true", help="Execute real transfers on FPL account (Disables Dry Run)")
    parser.add_argument("--dry-run", action="store_true", help="Force Simulation mode (Default: True)")
    parser.add_argument("--hits", type=int, default=config.max_allowed_hits, help="Max hits allowed")
    parser.add_argument("--build-squad", action="store_true", help="Build optimal initial 15-man squad (Draft 1) for £100m")
    parser.add_argument("--budget", type=float, default=100.0, help="Initial budget in millions (default: 100.0)")
    parser.add_argument("--min-chance", type=int, default=config.min_starter_chance, help="Minimum playing chance %% for starters (default: 75)")
    parser.add_argument("--hindsight", action="store_true", help="Run Hindsight Optimization Engine on finished gameweeks")
    parser.add_argument("--gw-start", type=int, default=1, help="Starting gameweek for hindsight analysis (default: 1)")
    parser.add_argument("--gw-end", type=int, default=None, help="Ending gameweek for hindsight analysis (default: current played GW)")
    parser.add_argument("--output-json", type=str, default="hindsight_gold_rules.json", help="Filename for exported Gold Rules JSON (default: hindsight_gold_rules.json)")
    parser.add_argument("--no-gold-rules", action="store_true", help="Disable Hindsight Gold Rules heuristics and use unweighted baseline")

    args = parser.parse_args()

    if args.hindsight:
        try:
            run_hindsight(
                gw_start=args.gw_start,
                gw_end=args.gw_end,
                budget=args.budget,
                output_json=args.output_json,
            )
            sys.exit(0)
        except Exception as e:
            import traceback
            print(f"\n❌ Error during hindsight optimization: {e}")
            traceback.print_exc()
            sys.exit(1)

    if args.build_squad:
        run_build_squad(budget=args.budget, min_chance=args.min_chance)
        sys.exit(0)

    effective_dry_run = False if args.live else (True if args.dry_run else config.dry_run)

    if not args.team_id:
        print("❌ Error: Please provide your FPL Team ID via --team-id or in .env file (FPL_TEAM_ID).")
        print("💡 Or run 'python main.py --build-squad' to generate an initial 15-man squad from scratch.")
        print("💡 Or run 'python main.py --hindsight' to run the Hindsight Optimization Engine.")
        sys.exit(1)

    try:
        run_manager(
            team_id=args.team_id,
            dry_run=effective_dry_run,
            max_hits=args.hits,
            apply_gold_rules=(not args.no_gold_rules)
        )
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"\n❌ Error during execution: {e}")
        traceback.print_exc()
        sys.exit(1)

