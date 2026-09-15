import time
import argparse
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.config import config
from src.infrastructure.fpl import FPLDataRepository, FPLClient
from src.infrastructure.notifications import TelegramNotifier
from main import run_manager


def check_final_safety(repo: FPLDataRepository, team_id: int, dry_run: bool, auto_fix: bool = True):
    """Executes a zero-cache live sanity check T-20min before deadline,

    with autonomous self-healing in Pure AI mode.
    """
    print("\n🛡️ [FINAL SAFETY PULSE - T-20m] Checking live team status & warmup reports...")
    notifier = TelegramNotifier()
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
        bench = picks[11:]
        alerts = []
        needs_lineup_resubmit = False

        # 1. Injury & Availability Check
        for pick in starters:
            p = all_players.get(pick.get("element"))
            if not p:
                continue
            is_cap = pick.get("is_captain", False)
            if p.status in ("i", "u", "s", "n") or (p.chance_of_playing_next_round is not None and p.chance_of_playing_next_round == 0):
                alerts.append(f"🚨 **إصابة مفاجئة مؤكدة**: {p.name} ({p.team_short}) لن يشارك!")
                if auto_fix and bench:
                    # Find first fit bench outfield player
                    for b_pick in bench[1:]:  # skip bench GK
                        bp = all_players.get(b_pick.get("element"))
                        if bp and bp.status == "a":
                            # swap positions
                            pos_starter = pick["position"]
                            pick["position"] = b_pick["position"]
                            b_pick["position"] = pos_starter
                            needs_lineup_resubmit = True
                            alerts.append(f"🔄 **تصحيح ذاتي**: تم تبديل {p.name} بالبديل {bp.name} تلقائياً.")
                            break

            elif p.chance_of_playing_next_round is not None and p.chance_of_playing_next_round < config.min_starter_chance:
                alerts.append(f"⚠️ Starter {p.name} ({p.team_short}) doubt! Status: '{p.status}' | Chance: {p.chance_of_playing_next_round}%")

            # Captain safety
            if is_cap and (p.status != "a" or (p.chance_of_playing_next_round is not None and p.chance_of_playing_next_round < 100)):
                alerts.append(f"🚨 CAPTAIN {p.name} ({p.team_short}) doubt! Switching armband to Vice-Captain.")
                if auto_fix:
                    for s_pick in starters:
                        if s_pick.get("is_vice_captain"):
                            pick["is_captain"] = False
                            s_pick["is_captain"] = True
                            needs_lineup_resubmit = True
                            vc_p = all_players.get(s_pick.get("element"))
                            alerts.append(f"👑 **تصحيح ذاتي**: تم نقل شارة الكابتن إلى {vc_p.name if vc_p else 'نائب الكابتن'} فوراً.")
                            break

        # 2. Goalkeeper Anti-Correlation & Conflict of Interest Check
        starting_gk_pick = starters[0] if starters else None
        bench_gk_pick = bench[0] if bench else None
        if starting_gk_pick and bench_gk_pick:
            gk_player = all_players.get(starting_gk_pick.get("element"))
            bench_gk_player = all_players.get(bench_gk_pick.get("element"))
            if gk_player:
                from src.infrastructure.optimization.lineup_solver import get_opponent_code
                gk_opp = get_opponent_code(gk_player.next_fixture)
                if gk_opp:
                    conflicting_att = [
                        all_players[pick["element"]].name
                        for pick in starters[1:]
                        if pick.get("element") in all_players and
                        all_players[pick["element"]].position in ("MID", "FWD") and
                        all_players[pick["element"]].team_short.upper() == gk_opp
                    ]
                    if conflicting_att:
                        alerts.append(
                            f"⚔️ **تضارب مصالح تكتيكي (Conflict of Interest)**: الحارس الأساسي {gk_player.name} ({gk_player.team_short}) "
                            f"يواجه مهاجمينا ({', '.join(conflicting_att)})!"
                        )
                        if auto_fix and bench_gk_player and bench_gk_player.status == "a":
                            # Check if bench GK has conflict
                            bench_opp = get_opponent_code(bench_gk_player.next_fixture)
                            bench_conflict = any(
                                all_players[pk["element"]].team_short.upper() == bench_opp
                                for pk in starters[1:] if pk.get("element") in all_players
                            )
                            if not bench_conflict:
                                pos_start = starting_gk_pick["position"]
                                starting_gk_pick["position"] = bench_gk_pick["position"]
                                bench_gk_pick["position"] = pos_start
                                needs_lineup_resubmit = True
                                alerts.append(f"🧤 **تصحيح تكتيكي ذاتي**: تم تصعيد الحارس {bench_gk_player.name} أساسياً ونزول {gk_player.name} دكة لتفادي تضارب المصالح.")

        # 3. Submit self-healing lineup if modified
        if needs_lineup_resubmit:
            sorted_picks = sorted(picks, key=lambda x: x["position"])
            res = gateway.set_lineup(team_id=team_id, picks_payload=sorted_picks)
            print(f"✅ Self-healing lineup submitted to FPL: {res}")
            alerts.append("🚀 **تم حفظ واعتماد التشكيلة المعدلة ذاتياً على سيرفرات الفانتازي بنجاح.**")

        if alerts:
            msg = "🛡️ **تقرير فحص الأمان الآلي قبل الديدلاين (Pure AI Pulse - T-20m)**:\n\n" + "\n\n".join(alerts)
            print("\n" + msg)
            notifier.send_message(msg)
        else:
            ok_msg = "✅ **فحص الأمان التكتيكي (T-20m)**: التشكيل الأساسي والكابتن جاهزون بنسبة 100% ولا يوجد أي تضارب أو إصابات!"
            print(ok_msg)
            notifier.send_message(ok_msg)
    except Exception as e:
        print(f"⚠️ Final safety check notice: {e}")


def run_scheduler(hours_before_deadline: float = 2.5, final_check_mins: int = 20, force_live: bool = False, pure_ai: bool = False):
    """Autonomous Two-Tier Scheduler with Pure AI hands-free background execution."""
    effective_dry_run = False if (force_live or pure_ai) else config.dry_run
    repo = FPLDataRepository(cache_ttl_minutes=5)
    notifier = TelegramNotifier()
    gw_stage1_done: Optional[int] = None
    gw_stage2_done: Optional[int] = None

    print("\n" + "=" * 65)
    print(f"  🤖 FPL Pure AI Autonomous Manager 24/7 Daemon")
    print("=" * 65)
    print(f"• Pure AI Hands-Free Mode: {'🟢 ACTIVE' if pure_ai else '⚪ OFF'}")
    print(f"• Execution Target:        {'🚀 LIVE FPL ACCOUNT' if not effective_dry_run else '🛡️ SIMULATION'}")
    print(f"• Stage 1 (Tactical Run):   {hours_before_deadline}h before Deadline")
    print(f"• Stage 2 (Safety Pulse):   {final_check_mins}m before Deadline")
    print(f"• Team ID:                 {config.fpl_team_id}")
    print("-" * 65)

    if pure_ai:
        try:
            notifier.send_message(
                f"🤖 **بدء تشغيل نظام الـ Pure AI المستقل بالكامل (24/7)**\n\n"
                f"• **الفريق:** `{config.fpl_team_id}`\n"
                f"• **حالة التنفيذ:** `{'مباشر على الحساب 🚀' if not effective_dry_run else 'محاكاة 🧪'}`\n"
                f"• **نظام العمل:** آلي بالكامل بدون الحاجة لأي تدخل منك أثناء سفرك.\n"
                f"• سيتم إرسال تقرير فوري لكل جولة عند تنفيذ التبديلات وفحص الأمان."
            )
            print("📱 Telegram startup notification dispatched.")
        except Exception as e:
            print(f"⚠️ Could not dispatch Telegram startup notification: {e}")

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
                print(f"\n🚨 [STAGE 1 TRIGGER] Pure AI Tactical Window ({hours_before_deadline}h prior to GW{next_gw})!")
                run_manager(team_id=config.fpl_team_id, dry_run=effective_dry_run, max_hits=config.max_allowed_hits)
                gw_stage1_done = next_gw

            # Stage 2: Final Safety Pulse
            elif timedelta(seconds=0) < time_until <= t_stage2 and gw_stage2_done != next_gw:
                print(f"\n🚨 [STAGE 2 TRIGGER] Pure AI Final Safety Pulse ({final_check_mins}m prior to GW{next_gw})!")
                check_final_safety(repo, team_id=config.fpl_team_id, dry_run=effective_dry_run, auto_fix=True)
                gw_stage2_done = next_gw

            elif time_until <= timedelta(seconds=0):
                print(f"ℹ️ Gameweek {next_gw} deadline has passed. Sleeping 1 hour for game updates...")
                time.sleep(3600)
                continue

            sleep_time = min(300, max(30, int(time_until.total_seconds() / 2)))
            hours = int(time_until.total_seconds() // 3600)
            mins = int((time_until.total_seconds() % 3600) // 60)
            print(f"⏳ [HEARTBEAT] Next: GW{next_gw} deadline in {hours}h {mins}m. Daemon active (sleeping {sleep_time}s)...")
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n🛑 Pure AI Scheduler stopped by user.")
            break
        except Exception as e:
            print(f"⚠️ Pure AI Scheduler error: {e}. Recovering in 2 minutes...")
            time.sleep(120)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FPL Pure AI Autonomous Scheduler")
    parser.add_argument("--hours-before", type=float, default=2.5, help="Hours before deadline for Stage 1 (default: 2.5)")
    parser.add_argument("--final-mins", type=int, default=config.final_safety_check_mins, help="Minutes before deadline for Stage 2 (default: 20)")
    parser.add_argument("--live", action="store_true", help="Run in Live Execution mode on real FPL account")
    parser.add_argument("--pure-ai", action="store_true", help="Run 100% autonomous hands-free mode for travel")
    parser.add_argument("--dry-run", action="store_true", help="Force simulation mode")
    args = parser.parse_args()

    force_live = args.live or (args.pure_ai and not args.dry_run)
    run_scheduler(
        hours_before_deadline=args.hours_before,
        final_check_mins=args.final_mins,
        force_live=force_live,
        pure_ai=args.pure_ai
    )
