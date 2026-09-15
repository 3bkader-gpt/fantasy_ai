"""
FPL Pure AI Manager - Autonomous Runner
========================================
Runs the 100% hands-free Pure AI daemon in the background.
Monitors all gameweeks, runs Two-Tier MILP optimizations,
executes live transfers and lineups, and sends Telegram reports.
"""

import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

if __name__ == "__main__":
    print("=" * 65)
    print("  🚀 Starting FPL Pure AI Autonomous Manager...")
    print("  📱 Mobile updates will be sent via Telegram.")
    print("=" * 65)
    
    from scheduler import run_scheduler
    # Runs pure AI with live execution enabled
    run_scheduler(
        hours_before_deadline=2.5,
        final_check_mins=20,
        force_live=True,
        pure_ai=True
    )
