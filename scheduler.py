import time
import argparse
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.config import config
from src.infrastructure.fpl import FPLDataRepository, FPLClient
from src.infrastructure.notifications import TelegramNotifier
from main import run_manager


def check_final_safety(repo: FPLDataRepository, team_id: int, dry_run: bool):
    """Executes a zero-cache live sanity check T-20min before deadline."""
    print("\n🛡️ [FINAL SAFETY PULSE - T-20m] Checking live team status & warmup reports...")
    try:
        all_players = {p.id: p for p in repo.get_all_players(force_refresh=True)}
        gateway = FPLClient(dry_run=dry_run)
        gateway.login()
        team_data = gateway.get_my_team(team_id)
        picks = team_data.get("picks", [])
        if not picks:
            print("⚠️ No team picks found to verify.")
            return

        starters = picks[:11]
        alerts = []
        for pick in starters:
            p = all_players.get(pick.get("element"))
            if not p:
                continue
            is_cap = pick.get("is_captain", False)
            if p.status != "a" or (p.chance_of_playing_next_round is not None and p.chance_of_playing_next_round < config.min_starter_chance):
                alerts.append(f"⚠️ Starter {p.name} ({p.team_short}) flagged! Status: '{p.status}' | Chance: {p.chance_of_playing_next_round}% | {p.news}")
            if is_cap and (p.status != "a" or (p.chance_of_playing_next_round is not None and p.chance_of_playing_next_round < 100)):
                alerts.append(f"🚨 CAPTAIN {p.name} ({p.team_short}) doubt! Armband swap advised.")

        if alerts:
            msg = "🚨 **تنبيه أمان نهائي قبل الديدلاين (T-20m)**:\n" + "\n".join(alerts)
            print("\n" + msg)
            TelegramNotifier().send_markdown_message(msg)
        else:
            print("✅ All Starting XI players and Captain are 100% verified fit for kickoff!")
    except Exception as e:
        print(f"⚠️ Final safety check notice: {e}")


def run_scheduler(hours_before_deadline: float = 2.5, final_check_mins: int = 20, force_live: bool = False):
    """Two-Tier Scheduler: T-2.5h Tactical Optimization + T-20m Live Safety Pulse."""
    effective_dry_run = False if force_live else config.dry_run
    repo = FPLDataRepository(cache_ttl_minutes=5)
    gw_stage1_done: Optional[int] = None
    gw_stage2_done: Optional[int] = None

    print("\n" + "=" * 65)
    print("  ⏰ FPL Autonomous AI Manager - Two-Tier Scheduler")
    print("=" * 65)
    print(f"• Mode: {'🛡️ SIMULATION' if effective_dry_run else '🚀 LIVE EXECUTION'}")
    print(f"• Stage 1 (Tactical Window): {hours_before_deadline}h before Deadline")
    print(f"• Stage 2 (Safety Pulse):   {final_check_mins}m before Deadline")
    print("-" * 65)

    while True:
        try:
            current_gw, next_gw, deadline_str = repo.get_current_and_next_gw()
            if not deadline_str or next_gw is None:
                print("⚠️ Could not determine upcoming deadline. Retrying in 1 hour...")
                time.sleep(3600)
                continue

            deadline_dt = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
            time_until = deadline_dt - datetime.now(timezone.utc)
            t_stage1 = timedelta(hours=hours_before_deadline)
            t_stage2 = timedelta(minutes=final_check_mins)

            # Stage 1: Tactical Window
            if t_stage2 < time_until <= t_stage1 and gw_stage1_done != next_gw:
                print(f"\n🚨 [STAGE 1 TRIGGER] Tactical Window ({hours_before_deadline}h prior)!")
                run_manager(team_id=config.fpl_team_id, dry_run=effective_dry_run, max_hits=config.max_allowed_hits)
                gw_stage1_done = next_gw

            # Stage 2: Final Safety Pulse
            elif timedelta(seconds=0) < time_until <= t_stage2 and gw_stage2_done != next_gw:
                print(f"\n🚨 [STAGE 2 TRIGGER] Final Safety Pulse ({final_check_mins}m prior)!")
                check_final_safety(repo, team_id=config.fpl_team_id, dry_run=effective_dry_run)
                gw_stage2_done = next_gw

            elif time_until <= timedelta(seconds=0):
                print("ℹ️ Gameweek deadline has passed. Sleeping 30 mins...")
                time.sleep(1800)
                continue

            sleep_time = min(300, max(30, int(time_until.total_seconds() / 2)))
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n🛑 Scheduler stopped.")
            break
        except Exception as e:
            print(f"⚠️ Scheduler error: {e}. Retrying in 2 minutes...")
            time.sleep(120)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FPL AI Autonomous Scheduler")
    parser.add_argument("--hours-before", type=float, default=2.5, help="Hours before deadline for Stage 1")
    parser.add_argument("--final-mins", type=int, default=config.final_safety_check_mins, help="Minutes before deadline for Stage 2")
    parser.add_argument("--live", action="store_true", help="Run in Live Execution mode")
    args = parser.parse_args()

    run_scheduler(hours_before_deadline=args.hours_before, final_check_mins=args.final_mins, force_live=args.live)
