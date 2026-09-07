import sys
import argparse
import logging
import warnings

warnings.filterwarnings("ignore")

from src.config import config
from src.infrastructure.fpl import FPLDataRepository, FPLClient
from src.infrastructure.xp import RuleBasedXPEngine
from src.infrastructure.optimization import SquadOptimizer
from src.infrastructure.ai import GeminiAdvisor
from src.infrastructure.notifications import TelegramNotifier
from src.application.use_cases import OptimizeGameweekUseCase, BuildInitialSquadUseCase
from src.presentation import ConsolePresenter, DashboardExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)


def run_manager(team_id: int, dry_run: bool, max_hits: int):
    """Composition Root: Wires dependencies and runs the gameweek optimization use case."""
    # 1. Instantiate Adapters (Infrastructure)
    repository = FPLDataRepository()
    gateway = FPLClient(dry_run=dry_run)
    xp_engine = RuleBasedXPEngine()
    advisor = GeminiAdvisor()
    notifier = TelegramNotifier()

    # 2. Inject into Use Case (Application)
    use_case = OptimizeGameweekUseCase(
        repository=repository,
        fpl_gateway=gateway,
        xp_engine=xp_engine,
        optimizer_factory=lambda players: SquadOptimizer(players),
        ai_advisor=advisor,
        notifier=notifier
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

    args = parser.parse_args()

    if args.build_squad:
        run_build_squad(budget=args.budget, min_chance=args.min_chance)
        sys.exit(0)

    effective_dry_run = False if args.live else (True if args.dry_run else config.dry_run)

    if not args.team_id:
        print("❌ Error: Please provide your FPL Team ID via --team-id or in .env file (FPL_TEAM_ID).")
        print("💡 Or run 'python main.py --build-squad' to generate an initial 15-man squad from scratch.")
        sys.exit(1)

    run_manager(team_id=args.team_id, dry_run=effective_dry_run, max_hits=args.hits)

