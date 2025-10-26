# analyzer.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
import math
import csv
import io

from schemas import GameInput, Projection, LineItem, SplitItem, ExpertItem, InjuryItem


# ---------- math helpers ----------

def american_to_prob(odds: Optional[float]) -> Optional[float]:
    if odds is None:
        return None
    try:
        o = float(odds)
    except Exception:
        return None
    if o < 0:
        return (-o) / ((-o) + 100.0)
    else:
        return 100.0 / (o + 100.0)


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def model_win_prob(proj_home: float, proj_away: float, total: Optional[float]) -> float:
    """
    Very lightweight normal model for P(home wins) from projected score diff.
    sigma is heuristically tied to total; this is intentionally transparent.
    """
    mu = float(proj_home) - float(proj_away)
    sigma = max(3.0, (float(total) / 6.0) if total not in (None, 0) else 7.5)
    # P(diff > 0)
    return 1.0 - normal_cdf((0.0 - mu) / sigma)


def model_home_cover_prob(proj_home: float, proj_away: float, spread_home: float, total: Optional[float]) -> float:
    """P(home - away > -spread_home). spread_home is negative when home is favored."""
    mu = float(proj_home) - float(proj_away)
    thresh = -float(spread_home)
    sigma = max(3.0, (float(total) / 6.0) if total not in (None, 0) else 7.5)
    z = (thresh - mu) / sigma
    return 1.0 - normal_cdf(z)


# ---------- small extractors over input lists ----------

def _find_line(lines: List[LineItem], market: str, option: str) -> Optional[LineItem]:
    for li in lines:
        if li.market == market and li.option == option:
            return li
    return None


def _sum_experts(experts: List[ExpertItem], market: str, option: str) -> int:
    return sum(int(e.count) for e in experts if e.market == market and e.option == option)


def _split_pct(splits: List[SplitItem], market: str, option: str, which: str) -> Optional[float]:
    # which: "public_pct" or "money_pct"
    for sp in splits:
        if sp.market == market and sp.option == option:
            return getattr(sp, which, None)
    return None


def _injury_sum(injuries: List[InjuryItem], team: str) -> float:
    return float(sum((i.impact_0to1 or 0.0) for i in injuries if i.team == team))


# ---------- scoring ----------

def _clamp(v: Optional[float], a: float, b: float) -> float:
    if v is None or math.isnan(v):
        return 0.0
    return max(a, min(b, v))


def compute_betscore_ml(edge_home_ml: Optional[float],
                        experts_home: int, experts_away: int,
                        sharp_delta_home: Optional[float],
                        inj_home_total: float, inj_away_total: float) -> float:
    """
    Transparent composite score (0..~100). Tunable weights:
      - Edge vs market (35)
      - Expert consensus (15)
      - Sharp delta (15)
      - Injury differential (10)
    Remaining headroom left for future features (weather/schedule).
    """
    experts_term = 0.0
    denom = float(experts_home + experts_away) if (experts_home + experts_away) > 0 else 1.0
    experts_term = (experts_home - experts_away) / denom

    score = (
        35.0 * (_clamp(edge_home_ml, -0.15, 0.15) / 0.15) +
        15.0 * experts_term +
        15.0 * ((sharp_delta_home or 0.0) / 100.0) +
        10.0 * (-inj_home_total + inj_away_total)
    )
    return float(round(score, 3))


def compute_betscore_ats(edge_home_cover: Optional[float],
                         experts_home: int, experts_away: int,
                         sharp_delta_home: Optional[float],
                         inj_home_total: float, inj_away_total: float) -> float:
    denom = float(experts_home + experts_away) if (experts_home + experts_away) > 0 else 1.0
    experts_term = (experts_home - experts_away) / denom
    score = (
        35.0 * (_clamp(edge_home_cover, -0.15, 0.15) / 0.15) +
        15.0 * experts_term +
        15.0 * ((sharp_delta_home or 0.0) / 100.0) +
        10.0 * (-inj_home_total + inj_away_total)
    )
    return float(round(score, 3))


# ---------- main analysis ----------

def analyze_games(games: List[GameInput]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns (moneyline_table, spread_table) as lists of dicts (JSON-serializable).
    One row per game, home-side perspective.
    """
    ml_rows: List[Dict[str, Any]] = []
    ats_rows: List[Dict[str, Any]] = []

    for g in games:
        # --- projections ---
        proj = g.projection
        proj_home_pts = float(proj.proj_home_pts) if proj and proj.proj_home_pts is not None else None
        proj_away_pts = float(proj.proj_away_pts) if proj and proj.proj_away_pts is not None else None
        proj_total = float(proj.proj_total) if proj and proj.proj_total is not None else None

        # --- lines ---
        li_ml_home = _find_line(g.market_lines, "moneyline", "home")
        li_ml_away = _find_line(g.market_lines, "moneyline", "away")
        li_sp_home = _find_line(g.market_lines, "spread", "home")
        li_sp_away = _find_line(g.market_lines, "spread", "away")

        ml_home_odds = li_ml_home.current_line if li_ml_home else None
        ml_away_odds = li_ml_away.current_line if li_ml_away else None
        imp_home_ml = american_to_prob(ml_home_odds)
        imp_away_ml = american_to_prob(ml_away_odds)

        spread_home = li_sp_home.current_line if li_sp_home else None
        spread_home_price = li_sp_home.current_price if li_sp_home else None
        imp_home_cover = american_to_prob(spread_home_price) if spread_home_price is not None else None

        # --- model probabilities ---
        model_home_win = model_win_prob(proj_home_pts, proj_away_pts, proj_total) if (proj_home_pts is not None and proj_away_pts is not None) else None
        model_away_win = (1.0 - model_home_win) if model_home_win is not None else None

        model_home_cover = model_home_cover_prob(proj_home_pts, proj_away_pts, spread_home, proj_total) \
            if (proj_home_pts is not None and proj_away_pts is not None and spread_home is not None) else None

        # --- edges ---
        edge_home_ml = (model_home_win - imp_home_ml) if (model_home_win is not None and imp_home_ml is not None) else None
        edge_home_cover = (model_home_cover - imp_home_cover) if (model_home_cover is not None and imp_home_cover is not None) else None

        # --- splits & experts ---
        pub_home_ml = _split_pct(g.splits, "moneyline", "home", "public_pct")
        mon_home_ml = _split_pct(g.splits, "moneyline", "home", "money_pct")
        pub_home_sp = _split_pct(g.splits, "spread", "home", "public_pct")
        mon_home_sp = _split_pct(g.splits, "spread", "home", "money_pct")

        experts_ml_home = _sum_experts(g.experts, "moneyline", "home")
        experts_ml_away = _sum_experts(g.experts, "moneyline", "away")
        experts_sp_home = _sum_experts(g.experts, "spread", "home")
        experts_sp_away = _sum_experts(g.experts, "spread", "away")

        sharp_delta_ml_home = (mon_home_ml - pub_home_ml) if (mon_home_ml is not None and pub_home_ml is not None) else None
        sharp_delta_sp_home = (mon_home_sp - pub_home_sp) if (mon_home_sp is not None and pub_home_sp is not None) else None

        # --- injuries (simple sums) ---
        inj_home_total = _injury_sum(g.injuries, g.home_team)
        inj_away_total = _injury_sum(g.injuries, g.away_team)

        # --- BetScores ---
        betscore_ml_home = compute_betscore_ml(edge_home_ml, experts_ml_home, experts_ml_away,
                                               sharp_delta_ml_home, inj_home_total, inj_away_total)
        betscore_ats_home = compute_betscore_ats(edge_home_cover, experts_sp_home, experts_sp_away,
                                                 sharp_delta_sp_home, inj_home_total, inj_away_total)

        # --- assemble rows ---
        ml_rows.append({
            "game_id": g.game_id,
            "league": g.league,
            "date": g.date,
            "away": g.away_team,
            "home": g.home_team,
            "model_home_win_prob": _round(model_home_win),
            "implied_home_ml_prob": _round(imp_home_ml),
            "edge_home_ml_prob": _round(edge_home_ml),
            "experts_moneyline_home": int(experts_ml_home),
            "experts_moneyline_away": int(experts_ml_away),
            "public_home_ml_pct": _round(pub_home_ml),
            "money_home_ml_pct": _round(mon_home_ml),
            "inj_home_total": _round(inj_home_total),
            "inj_away_total": _round(inj_away_total),
            "BetScore_ML_home": betscore_ml_home
        })

        ats_rows.append({
            "game_id": g.game_id,
            "league": g.league,
            "date": g.date,
            "away": g.away_team,
            "home": g.home_team,
            "spread_home": _round(spread_home),
            "spread_home_price": _round(spread_home_price),
            "model_home_cover": _round(model_home_cover),
            "imp_home_cover": _round(imp_home_cover),
            "experts_spread_home": int(experts_sp_home),
            "experts_spread_away": int(experts_sp_away),
            "public_home_spread_pct": _round(pub_home_sp),
            "money_home_spread_pct": _round(mon_home_sp),
            "inj_home_total": _round(inj_home_total),
            "inj_away_total": _round(inj_away_total),
            "BetScore_ATS_home": betscore_ats_home
        })

    # sort by score descending (nice for quick reading)
    ml_rows.sort(key=lambda r: r.get("BetScore_ML_home", 0.0), reverse=True)
    ats_rows.sort(key=lambda r: r.get("BetScore_ATS_home", 0.0), reverse=True)

    return ml_rows, ats_rows


def _round(x: Optional[float], places: int = 3) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(round(float(x), places))
    except Exception:
        return None


def _rows_to_csv(rows: List[Dict[str, Any]], field_order: Optional[List[str]] = None) -> str:
    if not rows:
        return ""
    if field_order is None:
        # stable column order: keys of first row
        field_order = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=field_order, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


def tables_to_csv(ml_rows: List[Dict[str, Any]], ats_rows: List[Dict[str, Any]]) -> Tuple[str, str]:
    ml_cols = [
        "game_id","league","date","away","home",
        "model_home_win_prob","implied_home_ml_prob","edge_home_ml_prob",
        "experts_moneyline_home","experts_moneyline_away",
        "public_home_ml_pct","money_home_ml_pct",
        "inj_home_total","inj_away_total",
        "BetScore_ML_home"
    ]
    ats_cols = [
        "game_id","league","date","away","home",
        "spread_home","spread_home_price",
        "model_home_cover","imp_home_cover",
        "experts_spread_home","experts_spread_away",
        "public_home_spread_pct","money_home_spread_pct",
        "inj_home_total","inj_away_total",
        "BetScore_ATS_home"
    ]
    return _rows_to_csv(ml_rows, ml_cols), _rows_to_csv(ats_rows, ats_cols)

