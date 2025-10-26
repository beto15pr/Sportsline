# schemas.py
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, validator


class Projection(BaseModel):
    proj_home_pts: float
    proj_away_pts: float
    proj_total: Optional[float] = None
    proj_spread_home: Optional[float] = None
    proj_spread_away: Optional[float] = None
    grade: Optional[str] = None


class LineItem(BaseModel):
    market: str  # "moneyline" | "spread" | "total"
    option: str  # "home" | "away" | "over" | "under"
    open_line: Optional[float] = None
    open_price: Optional[float] = None
    current_line: Optional[float] = None   # for ML: American odds; for spread/total: the number (e.g., -3.5 / 46.5)
    current_price: Optional[float] = None  # for spread/total price (e.g., -110)
    book: Optional[str] = None

    @validator("market")
    def _market_ok(cls, v):
        v = v.lower()
        if v not in {"moneyline", "spread", "total"}:
            raise ValueError("market must be moneyline|spread|total")
        return v

    @validator("option")
    def _option_ok(cls, v, values):
        v = v.lower()
        mkt = values.get("market", "").lower()
        if mkt in {"moneyline", "spread"} and v not in {"home", "away"}:
            raise ValueError("option must be home|away for moneyline/spread")
        if mkt == "total" and v not in {"over", "under"}:
            raise ValueError("option must be over|under for total")
        return v


class SplitItem(BaseModel):
    market: str   # same domains as LineItem.market
    option: str   # same option domain rules
    public_pct: Optional[float] = None
    money_pct: Optional[float] = None

    @validator("market")
    def _market_ok(cls, v):
        v = v.lower()
        if v not in {"moneyline", "spread", "total"}:
            raise ValueError("market must be moneyline|spread|total")
        return v

    @validator("option")
    def _option_ok(cls, v, values):
        v = v.lower()
        mkt = values.get("market", "").lower()
        if mkt in {"moneyline", "spread"} and v not in {"home", "away"}:
            raise ValueError("option must be home|away for moneyline/spread")
        if mkt == "total" and v not in {"over", "under"}:
            raise ValueError("option must be over|under for total")
        return v


class ExpertItem(BaseModel):
    market: str        # "moneyline" | "spread"
    option: str        # "home" | "away"
    count: int = 0
    source: Optional[str] = None

    @validator("market")
    def _market_ok(cls, v):
        v = v.lower()
        if v not in {"moneyline", "spread"}:
            raise ValueError("expert.market must be moneyline|spread")
        return v

    @validator("option")
    def _option_ok(cls, v):
        v = v.lower()
        if v not in {"home", "away"}:
            raise ValueError("expert.option must be home|away")
        return v


class InjuryItem(BaseModel):
    team: str
    player: Optional[str] = None
    pos: Optional[str] = None
    status: Optional[str] = None
    impact_0to1: Optional[float] = 0.0
    note: Optional[str] = None


class GameInput(BaseModel):
    game_id: str
    league: str
    date: str
    start_time_local: Optional[str] = None
    home_team: str
    away_team: str

    projection: Projection
    market_lines: List[LineItem] = Field(default_factory=list)
    splits: List[SplitItem] = Field(default_factory=list)
    experts: List[ExpertItem] = Field(default_factory=list)
    injuries: List[InjuryItem] = Field(default_factory=list)


class BatchGames(BaseModel):
    games: List[GameInput]

