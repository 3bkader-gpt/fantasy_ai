import json
import math
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

from ...domain.models.player import Player
from ...domain.models.squad import LineupSelection
from ...domain.models.transfer import TransferPlan
from ...config import config

logger = logging.getLogger("PredictionLogger")


class PredictionLogger:
    """Logs pre-deadline ProbabilisticXPEngine predictions for true Out-of-Sample
    post-gameweek calibration (MAE, RMSE, Spearman rank correlation, GK & Captain accuracy).
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or (config.root_dir / "output" / "predictions")

    def log_pre_deadline(
        self,
        gw: int,
        all_players: List[Player],
        plan: TransferPlan,
        deadline: Optional[str] = None,
    ) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_file = self.output_dir / f"gw_{gw}_predictions.json"

        players_snapshot = [
            {
                "id": p.id,
                "name": p.name,
                "position": p.position,
                "team_short": p.team_short,
                "cost": p.cost,
                "xp": p.xp,
                "horizon_xp": p.horizon_xp,
                "expected_minutes": p.expected_minutes,
                "expected_cs_prob": getattr(p, "expected_cs_prob", 0.0),
                "expected_team_goals": getattr(p, "expected_team_goals", 0.0),
                "expected_defcon_pts": getattr(p, "expected_defcon_pts", 0.0),
                "market_scorer_prob": getattr(p, "market_scorer_prob", None),
                "next_fixture": p.next_fixture,
            }
            for p in all_players
            if p.expected_minutes > 0 or p.xp > 0
        ]

        lineup: LineupSelection = plan.final_lineup
        payload = {
            "gameweek": gw,
            "logged_at_utc": datetime.now(timezone.utc).isoformat(),
            "deadline": deadline,
            "formation": lineup.formation,
            "predicted_xi_xp": lineup.total_expected_points,
            "captain_id": lineup.captain.id,
            "captain_name": lineup.captain.name,
            "captain_xp": lineup.captain.xp,
            "starting_gk_id": lineup.starting_xi[0].id if lineup.starting_xi else None,
            "starting_xi_ids": [p.id for p in lineup.starting_xi],
            "bench_ids": [p.id for p in lineup.bench],
            "recommended_chip": (plan.chip_recommendation or {}).get("recommended_chip"),
            "auto_activate_chip": (plan.chip_recommendation or {}).get("auto_activate_chip"),
            "transfers_count": len(plan.transfers),
            "hits_cost": plan.hits_cost,
            "players": players_snapshot,
        }

        out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(
            f"Saved Out-of-Sample pre-deadline prediction snapshot for GW{gw} "
            f"({len(players_snapshot)} active players) to {out_file}."
        )
        return out_file

    def evaluate_gameweek(self, gw: int, live_elements: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluates a previously saved pre-deadline prediction file against actual GW live stats."""
        pred_file = self.output_dir / f"gw_{gw}_predictions.json"
        if not pred_file.exists():
            raise FileNotFoundError(f"No pre-deadline prediction log found for GW{gw} at {pred_file}")

        data = json.loads(pred_file.read_text(encoding="utf-8"))
        preds, actuals = [], []

        for p in data.get("players", []):
            st = live_elements.get(p["id"])
            if not st or st.get("minutes", 0) < 60:
                continue
            preds.append(float(p["xp"]))
            actuals.append(float(st.get("total_points", 0)))

        n = len(actuals)
        mae = round(sum(abs(x - y) for x, y in zip(preds, actuals)) / n, 3) if n else 0.0
        rmse = round(math.sqrt(sum((x - y) ** 2 for x, y in zip(preds, actuals)) / n), 3) if n else 0.0

        rho = 0.0
        if n >= 5:
            try:
                from scipy.stats import spearmanr
                rho = round(float(spearmanr(preds, actuals).statistic), 4)
            except Exception:
                rho = 0.0

        xi_ids = data.get("starting_xi_ids", [])
        cap_id = data.get("captain_id")
        gk_id = data.get("starting_gk_id")
        xi_actual = sum(live_elements.get(pid, {}).get("total_points", 0) for pid in xi_ids)
        cap_actual = live_elements.get(cap_id, {}).get("total_points", 0) if cap_id else 0
        gk_actual = live_elements.get(gk_id, {}).get("total_points", 0) if gk_id else 0

        report = {
            "gameweek": gw,
            "sample_size_60m": n,
            "mae": mae,
            "rmse": rmse,
            "spearman_rho": rho,
            "predicted_xi_xp": data.get("predicted_xi_xp", 0.0),
            "actual_xi_with_cap": xi_actual + cap_actual,
            "captain_name": data.get("captain_name"),
            "captain_actual_pts": cap_actual,
            "gk_actual_pts": gk_actual,
        }
        eval_file = self.output_dir / f"gw_{gw}_calibration.json"
        eval_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    def auto_calibrate_finished_gws(
        self,
        finished_gws: List[int],
        notifier: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Automatically calibrates any logged pre-deadline GW that has now finished
        and dispatches a concise Arabic calibration summary to Telegram — zero manual commands needed.
        """
        import requests
        reports: List[Dict[str, Any]] = []
        if not self.output_dir.exists():
            return reports

        for gw in sorted(set(finished_gws)):
            pred_file = self.output_dir / f"gw_{gw}_predictions.json"
            eval_file = self.output_dir / f"gw_{gw}_calibration.json"
            if not pred_file.exists() or eval_file.exists():
                continue
            try:
                res = requests.get(f"{config.fpl_base_url}/event/{gw}/live/", timeout=15)
                if res.status_code != 200:
                    continue
                live_elements = {el["id"]: el["stats"] for el in res.json().get("elements", [])}
                rep = self.evaluate_gameweek(gw=gw, live_elements=live_elements)
                reports.append(rep)
                logger.info(
                    f"Auto-calibrated GW{gw}: MAE={rep['mae']}, RMSE={rep['rmse']}, "
                    f"Spearman={rep['spearman_rho']}, XI={rep['actual_xi_with_cap']} vs pred {rep['predicted_xi_xp']}"
                )
                if notifier:
                    msg = (
                        f"🧪 <b>تقرير المعايرة التلقائية (Out-of-Sample) — GW{gw}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"• <b>نقاط التشكيلة الفعلية:</b> {rep['actual_xi_with_cap']} (المتوقع: {rep['predicted_xi_xp']:.1f} xP)\n"
                        f"• <b>الكابتن ({rep['captain_name']}):</b> {rep['captain_actual_pts']} نقطة أساس\n"
                        f"• <b>الحارس الأساسي:</b> {rep['gk_actual_pts']} نقطة\n"
                        f"• <b>دقة النموذج (N={rep['sample_size_60m']}):</b> MAE={rep['mae']} | RMSE={rep['rmse']} | ρ={rep['spearman_rho']}"
                    )
                    notifier.send_message(msg)
            except Exception as e:
                logger.debug(f"Auto-calibration skipped for GW{gw}: {e}")
        return reports
