import sys
from ..application.dtos.gameweek_dto import GameweekPlanDTO
from ..application.dtos.initial_squad_dto import InitialSquadDTO


class ConsolePresenter:
    """Formats and prints gameweek optimization results and tactical briefings."""

    @staticmethod
    def setup_utf8():
        if sys.platform == "win32":
            try:
                sys.stdout.reconfigure(encoding="utf-8")
                sys.stderr.reconfigure(encoding="utf-8")
            except Exception:
                pass

    @staticmethod
    def print_banner(title: str):
        print("\n" + "=" * 65)
        print(f"  ⚽ {title}")
        print("=" * 65)

    def display_plan(self, dto: GameweekPlanDTO):
        self.setup_utf8()

        self.print_banner(f"Optimization Results for GW {dto.gameweek}")
        print(f"• Manager: {dto.manager_name} | Squad: {dto.team_name}")
        if dto.rank:
            print(f"• Overall Rank: {dto.rank:,} | Total Points: {dto.total_points}")
        print(f"• Squad Value: £{dto.team_value:.1f}m | Available Bank: £{dto.bank:.1f}m")
        print(f"• Free Transfers: {dto.free_transfers} | Deadline: {dto.deadline or 'TBD'}")

        # Transfers
        print("-" * 65)
        if dto.plan.transfers:
            print("🔄 RECOMMENDED TRANSFERS (3-GW Horizon Evaluated):")
            for t in dto.plan.transfers:
                p_out, p_in = t.player_out, t.player_in
                print(f"  🔴 OUT: {p_out.name:<15} ({p_out.position:<3} | {p_out.team_short:<3}) [GW xP: {p_out.xp:.1f} | 3-GW: {p_out.horizon_xp:.1f}]")
                print(f"  🟢 IN:  {p_in.name:<15} ({p_in.position:<3} | {p_in.team_short:<3}) [GW xP: {p_in.xp:.1f} | 3-GW: {p_in.horizon_xp:.1f} | £{p_in.cost}m | {p_in.price_trend}]")
                print(f"        Upcoming: {p_in.horizon_fixtures}")
            print(f"  • Hits Cost: -{dto.plan.hits_cost} pts | Net EV: +{dto.plan.net_gain:.2f} | 3-GW EV: +{dto.plan.horizon_gain:.2f}")
        else:
            print("🔄 TRANSFERS: No changes needed. Rolled free transfer to next week.")

        # Chips
        if dto.plan.chip_recommendation and dto.plan.chip_recommendation.get("chip_recommendations"):
            print("\n🃏 CHIP STRATEGY RECOMMENDATIONS:")
            for r in dto.plan.chip_recommendation["chip_recommendations"]:
                print(f"  ⭐ Chip: {r['chip'].upper()} | Confidence: {r['confidence']} | {r['reason']}")

        # Lineup
        lineup = dto.plan.final_lineup
        print(f"\n🌟 STARTING XI (Formation: {lineup.formation} | Total xP: {lineup.total_expected_points}):")
        print(f"  👑 Captain (C): {lineup.captain.name} ({lineup.captain.team_short}) [xP: {lineup.captain.xp:.1f}]")
        print(f"  🥈 Vice (VC):   {lineup.vice_captain.name} ({lineup.vice_captain.team_short}) [xP: {lineup.vice_captain.xp:.1f}]")
        print("  📋 Starters:")
        for p in lineup.starting_xi:
            role = " (C)" if p.id == lineup.captain.id else (" (VC)" if p.id == lineup.vice_captain.id else "")
            print(f"    - {p.position:<3} {p.name:<16} ({p.team_short:<3}) [xP: {p.xp:.1f}] {p.next_fixture}{role}")

        print("\n🪑 BENCH:")
        for idx, p in enumerate(lineup.bench, start=1):
            print(f"    {idx}. {p.position:<3} {p.name:<16} ({p.team_short:<3}) [xP: {p.xp:.1f}] {p.next_fixture}")

        # AI Tactical Briefing
        self.print_banner(f"تقرير المدير الفني للجولة {dto.gameweek}")
        print(dto.briefing)
        print("=" * 65)

        # Status mode
        if dto.dry_run:
            print("\n🛡️ [DRY RUN ACTIVE] Simulation complete! No changes were made to your account.")
            print("💡 To enable real automatic transfers, set DRY_RUN=False in your .env or pass --live.")
        else:
            print("\n🚀 [LIVE EXECUTION COMPLETE] Official account updated successfully!")

    def display_initial_squad(self, dto: InitialSquadDTO):
        self.setup_utf8()

        self.print_banner(f"Optimal Initial 15-Man Squad (Draft 1 - Baseline)")
        print(f"• Target Gameweek: GW {dto.target_gameweek} | Deadline: {dto.deadline or 'TBD'}")
        print(f"• Starting XI Cost: £{dto.starters_cost:.1f}m | Bench Cost: £{dto.bench_cost:.1f}m")
        print(f"• Total Squad Cost: £{dto.total_cost:.1f}m / £100.0m | Bank: £{dto.remaining_bank:.1f}m")
        print(f"• Combined 3-GW Horizon xP: {dto.total_squad_horizon_xp:.1f} pts")
        print("-" * 65)

        lineup = dto.lineup
        print(f"\n🌟 STARTING XI (Formation: {lineup.formation} | Total Immediate xP: {lineup.total_expected_points:.1f}):")
        print(f"  👑 Captain (C): {lineup.captain.name} ({lineup.captain.team_short}) [GW xP: {lineup.captain.xp:.1f} | 3-GW: {lineup.captain.horizon_xp:.1f}]")
        print(f"  🥈 Vice (VC):   {lineup.vice_captain.name} ({lineup.vice_captain.team_short}) [GW xP: {lineup.vice_captain.xp:.1f} | 3-GW: {lineup.vice_captain.horizon_xp:.1f}]")
        print("  📋 Starters:")
        for p in lineup.starting_xi:
            role = " (C)" if p.id == lineup.captain.id else (" (VC)" if p.id == lineup.vice_captain.id else "")
            print(f"    - {p.position:<3} {p.name:<16} ({p.team_short:<3}) £{p.cost:<4.1f}m [xP: {p.xp:.1f} | E[Min]: {p.expected_minutes:.0f}'] {p.next_fixture}{role}")

        print("\n🪑 BENCH ENABLERS:")
        for idx, p in enumerate(lineup.bench, start=1):
            print(f"    {idx}. {p.position:<3} {p.name:<16} ({p.team_short:<3}) £{p.cost:<4.1f}m [xP: {p.xp:.1f} | E[Min]: {p.expected_minutes:.0f}'] {p.next_fixture}")

        self.print_banner("التحليل الفني والتكتيكي للمدير الذكي (Draft 1 Review)")
        print(dto.briefing)
        print("=" * 65)

