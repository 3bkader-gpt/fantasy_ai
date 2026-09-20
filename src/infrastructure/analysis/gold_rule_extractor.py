import logging
from collections import Counter
from typing import Dict, List, Tuple, Any, Optional

from ...domain.models.hindsight_models import (
    PlayerGameweekRecord,
    HindsightResult,
    GoldRule,
)

logger = logging.getLogger("GoldRuleExtractor")

POSITION_NAME_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


class GoldRuleExtractor:
    """Reverse-engineers the mathematically optimal hindsight path into actionable Gold Rules."""

    def extract(
        self,
        result: HindsightResult,
        player_points: Dict[int, List[PlayerGameweekRecord]],
    ) -> List[GoldRule]:
        """Extract statistical heuristics and gold rules from the hindsight result."""
        if not result.decisions:
            return []

        # Index records by (gw, player_id)
        records_by_gw_player: Dict[Tuple[int, int], PlayerGameweekRecord] = {}
        for gw, records in player_points.items():
            for r in records:
                records_by_gw_player[(gw, r.player_id)] = r

        rules: List[GoldRule] = []
        rules.extend(self._extract_captain_rules(result, records_by_gw_player))
        rules.extend(self._extract_formation_rules(result))
        rules.extend(self._extract_transfer_rules(result, records_by_gw_player))
        rules.extend(self._extract_budget_allocation_rules(result, records_by_gw_player))
        rules.extend(self._extract_fixture_context_rules(result, records_by_gw_player))
        rules.extend(self._extract_price_efficiency_rules(result, records_by_gw_player))

        logger.info(f"Extracted {len(rules)} Gold Rules from hindsight path.")
        return rules

    def _extract_captain_rules(
        self,
        result: HindsightResult,
        records_by_gw_player: Dict[Tuple[int, int], PlayerGameweekRecord],
    ) -> List[GoldRule]:
        rules: List[GoldRule] = []
        n_gws = len(result.decisions)
        if n_gws == 0:
            return rules

        captains_data = []
        evidence_gws = []

        for d in result.decisions:
            rec = records_by_gw_player.get((d.gameweek, d.captain_id))
            if rec:
                captains_data.append(rec)
                evidence_gws.append(d.gameweek)

        if not captains_data:
            return rules

        # 1. Captain Position Preference
        pos_counts = Counter(r.element_type for r in captains_data)
        top_pos_id, top_pos_count = pos_counts.most_common(1)[0]
        top_pos_name = POSITION_NAME_MAP.get(top_pos_id, "UNK")
        pos_pct = round(top_pos_count / len(captains_data), 3)

        mid_fwd_count = pos_counts.get(3, 0) + pos_counts.get(4, 0)
        mid_fwd_pct = round(mid_fwd_count / len(captains_data), 3)

        if mid_fwd_pct >= 0.7:
            rules.append(
                GoldRule(
                    category="captain",
                    rule_text=f"Captains were exclusively attacking assets (MID/FWD) in {mid_fwd_pct * 100:.1f}% of gameweeks (preferred: {top_pos_name}).",
                    confidence=mid_fwd_pct,
                    evidence_gws=evidence_gws,
                    feature_values={
                        "attacking_pct": mid_fwd_pct,
                        "dominant_position": top_pos_name,
                        "position_breakdown": {
                            POSITION_NAME_MAP.get(k, "UNK"): v for k, v in pos_counts.items()
                        },
                    },
                )
            )

        # 2. Captain Price Tier & Premium Bias
        premium_count = sum(1 for r in captains_data if r.price >= 9.5)
        avg_cap_price = round(sum(r.price for r in captains_data) / len(captains_data), 2)
        premium_pct = round(premium_count / len(captains_data), 3)

        rules.append(
            GoldRule(
                category="captain",
                rule_text=f"Captains averaged £{avg_cap_price:.1f}m in cost; premium assets (>=£9.5m) were captained {premium_pct * 100:.1f}% of the time.",
                confidence=premium_pct if premium_pct >= 0.5 else round(1.0 - premium_pct, 3),
                evidence_gws=evidence_gws,
                feature_values={
                    "avg_price": avg_cap_price,
                    "premium_captain_pct": premium_pct,
                },
            )
        )

        # 3. Captain Home/Away & FDR
        home_count = sum(1 for r in captains_data if r.was_home)
        home_pct = round(home_count / len(captains_data), 3)
        easy_fdr_count = sum(1 for r in captains_data if r.fixture_difficulty <= 2)
        fdr_pct = round(easy_fdr_count / len(captains_data), 3)
        avg_fdr = round(sum(r.fixture_difficulty for r in captains_data) / len(captains_data), 2)

        rules.append(
            GoldRule(
                category="captain",
                rule_text=f"Captains played at Home {home_pct * 100:.1f}% of the time with an average FDR of {avg_fdr:.1f} (FDR <= 2 in {fdr_pct * 100:.1f}% of GWs).",
                confidence=max(home_pct, fdr_pct),
                evidence_gws=evidence_gws,
                feature_values={
                    "home_pct": home_pct,
                    "avg_fdr": avg_fdr,
                    "easy_fdr_pct": fdr_pct,
                },
            )
        )

        return rules

    def _extract_formation_rules(self, result: HindsightResult) -> List[GoldRule]:
        rules: List[GoldRule] = []
        formations = [d.formation for d in result.decisions]
        if not formations:
            return rules

        counts = Counter(formations)
        top_formation, top_count = counts.most_common(1)[0]
        confidence = round(top_count / len(formations), 3)
        evidence_gws = [d.gameweek for d in result.decisions if d.formation == top_formation]

        rules.append(
            GoldRule(
                category="formation",
                rule_text=f"Formation {top_formation} was mathematically optimal in {confidence * 100:.1f}% of gameweeks.",
                confidence=confidence,
                evidence_gws=evidence_gws,
                feature_values={
                    "dominant_formation": top_formation,
                    "frequency": top_count,
                    "all_formations": dict(counts),
                },
            )
        )
        return rules

    def _extract_transfer_rules(
        self,
        result: HindsightResult,
        records_by_gw_player: Dict[Tuple[int, int], PlayerGameweekRecord],
    ) -> List[GoldRule]:
        rules: List[GoldRule] = []
        transfers_in_pts = []
        transfers_out_pts = []
        transfer_gws = []

        for d in result.decisions:
            if d.transfers_in:
                transfer_gws.append(d.gameweek)
                for p_in in d.transfers_in:
                    rec_in = records_by_gw_player.get((d.gameweek, p_in))
                    if rec_in:
                        transfers_in_pts.append(rec_in.total_points)

                for p_out in d.transfers_out:
                    rec_out = records_by_gw_player.get((d.gameweek, p_out))
                    if rec_out:
                        transfers_out_pts.append(rec_out.total_points)

        total_transfers = len(transfers_in_pts)
        if total_transfers > 0:
            avg_in = round(sum(transfers_in_pts) / total_transfers, 2)
            avg_out = round(sum(transfers_out_pts) / max(1, len(transfers_out_pts)), 2)
            net_delta = round(avg_in - avg_out, 2)

            rules.append(
                GoldRule(
                    category="transfer",
                    rule_text=f"Optimal transfers in averaged {avg_in:.1f} pts in their debut GW vs {avg_out:.1f} pts for players sold (net immediate gain: +{net_delta:.1f} pts per transfer).",
                    confidence=0.85 if net_delta > 0 else 0.5,
                    evidence_gws=transfer_gws,
                    feature_values={
                        "total_transfers_made": total_transfers,
                        "avg_debut_points_in": avg_in,
                        "avg_points_out": avg_out,
                        "net_point_delta": net_delta,
                        "total_hits_taken": result.total_hits,
                    },
                )
            )

        # Hit aggressiveness rule
        if result.total_hits > 0:
            rules.append(
                GoldRule(
                    category="transfer",
                    rule_text=f"Taking {result.total_hits} hit(s) (-{result.total_hit_cost} pts) was mathematically optimal to capture explosive upside across gameweeks.",
                    confidence=0.8,
                    evidence_gws=[d.gameweek for d in result.decisions if d.hits_taken > 0],
                    feature_values={
                        "total_hits": result.total_hits,
                        "hit_cost": result.total_hit_cost,
                    },
                )
            )
        else:
            rules.append(
                GoldRule(
                    category="transfer",
                    rule_text="Zero hits were required; patient free-transfer rollover sufficed for the optimal point path.",
                    confidence=0.9,
                    evidence_gws=[d.gameweek for d in result.decisions],
                    feature_values={"total_hits": 0},
                )
            )

        return rules

    def _extract_budget_allocation_rules(
        self,
        result: HindsightResult,
        records_by_gw_player: Dict[Tuple[int, int], PlayerGameweekRecord],
    ) -> List[GoldRule]:
        rules: List[GoldRule] = []
        pos_spend: Dict[int, List[float]] = {1: [], 2: [], 3: [], 4: []}

        for d in result.decisions:
            for p in d.starting_xi:
                rec = records_by_gw_player.get((d.gameweek, p))
                if rec and rec.element_type in pos_spend:
                    pos_spend[rec.element_type].append(rec.price)

        total_starting_spend = sum(sum(prices) for prices in pos_spend.values())
        if total_starting_spend == 0:
            return rules

        spend_shares = {}
        for pos_id, prices in pos_spend.items():
            pos_name = POSITION_NAME_MAP.get(pos_id, "UNK")
            pos_total = sum(prices)
            share = round(pos_total / total_starting_spend, 3)
            avg_spend = round(pos_total / len(result.decisions), 2)
            spend_shares[pos_name] = {"share_pct": share, "avg_spend_m": avg_spend}

        # Sort positions by spend share
        sorted_shares = sorted(spend_shares.items(), key=lambda x: x[1]["share_pct"], reverse=True)
        top_pos, top_info = sorted_shares[0]

        rules.append(
            GoldRule(
                category="position_allocation",
                rule_text=f"Starting XI budget prioritized {top_pos} ({top_info['share_pct'] * 100:.1f}% of starting spend, avg £{top_info['avg_spend_m']:.1f}m).",
                confidence=round(top_info["share_pct"], 3),
                evidence_gws=[d.gameweek for d in result.decisions],
                feature_values=spend_shares,
            )
        )
        return rules

    def _extract_fixture_context_rules(
        self,
        result: HindsightResult,
        records_by_gw_player: Dict[Tuple[int, int], PlayerGameweekRecord],
    ) -> List[GoldRule]:
        rules: List[GoldRule] = []
        starter_home_flags = []
        starter_fdrs = []

        for d in result.decisions:
            for p in d.starting_xi:
                rec = records_by_gw_player.get((d.gameweek, p))
                if rec:
                    starter_home_flags.append(rec.was_home)
                    starter_fdrs.append(rec.fixture_difficulty)

        if not starter_home_flags:
            return rules

        home_pct = round(sum(1 for h in starter_home_flags if h) / len(starter_home_flags), 3)
        avg_fdr = round(sum(starter_fdrs) / len(starter_fdrs), 2)
        easy_fdr_pct = round(sum(1 for f in starter_fdrs if f <= 2) / len(starter_fdrs), 3)

        rules.append(
            GoldRule(
                category="fixture_context",
                rule_text=f"Optimal starting XIs leaned towards Home fixtures ({home_pct * 100:.1f}%) with an average FDR of {avg_fdr:.1f} (easy FDR <= 2 in {easy_fdr_pct * 100:.1f}% of picks).",
                confidence=max(home_pct, easy_fdr_pct),
                evidence_gws=[d.gameweek for d in result.decisions],
                feature_values={
                    "starting_home_pct": home_pct,
                    "avg_fdr": avg_fdr,
                    "easy_fdr_pct": easy_fdr_pct,
                },
            )
        )
        return rules

    def _extract_price_efficiency_rules(
        self,
        result: HindsightResult,
        records_by_gw_player: Dict[Tuple[int, int], PlayerGameweekRecord],
    ) -> List[GoldRule]:
        rules: List[GoldRule] = []
        # Tiers: Budget (< £6.0m), Mid (£6.0m - £9.0m), Premium (>= £9.5m)
        tiers = {
            "Budget (<£6.0m)": {"pts": 0, "cost": 0.0, "count": 0},
            "Mid-Tier (£6.0-£9.0m)": {"pts": 0, "cost": 0.0, "count": 0},
            "Premium (>=£9.5m)": {"pts": 0, "cost": 0.0, "count": 0},
        }

        for d in result.decisions:
            for p in d.starting_xi:
                rec = records_by_gw_player.get((d.gameweek, p))
                if rec:
                    if rec.price < 6.0:
                        t = tiers["Budget (<£6.0m)"]
                    elif rec.price <= 9.0:
                        t = tiers["Mid-Tier (£6.0-£9.0m)"]
                    else:
                        t = tiers["Premium (>=£9.5m)"]

                    t["pts"] += rec.total_points
                    t["cost"] += rec.price
                    t["count"] += 1

        tier_metrics = {}
        for name, data in tiers.items():
            pts_per_m = round(data["pts"] / max(0.1, data["cost"]), 2)
            avg_pts = round(data["pts"] / max(1, data["count"]), 2)
            tier_metrics[name] = {
                "total_picks": data["count"],
                "pts_per_million": pts_per_m,
                "avg_points": avg_pts,
            }

        # Find tier with highest pts per million
        best_ppm_tier = max(tier_metrics.items(), key=lambda x: x[1]["pts_per_million"])

        rules.append(
            GoldRule(
                category="price_efficiency",
                rule_text=f"{best_ppm_tier[0]} offered the highest points-per-million ({best_ppm_tier[1]['pts_per_million']} pts/£m) in the optimal starting XIs.",
                confidence=0.8,
                evidence_gws=[d.gameweek for d in result.decisions],
                feature_values=tier_metrics,
            )
        )
        return rules
