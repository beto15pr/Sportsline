# app.py
import io
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError
from typing import Dict, Any

from schemas import BatchGames
from analyzer import analyze_games, tables_to_csv

app = FastAPI(title="SportsLine Analyzer API", version="1.0.0")


@app.get("/")
def root():
    return {
        "service": "sportsline-analyzer",
        "status": "ok",
        "docs": "/docs",
        "endpoints": {
            "analyze": "POST /sportsline/analyze  -> JSON tables + CSV text",
            "analyze_csv_moneyline": "POST /sportsline/analyze/csv/moneyline  -> CSV text",
            "analyze_csv_spread": "POST /sportsline/analyze/csv/spread  -> CSV text",
            "health": "GET /health"
        }
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/sportsline/analyze")
def analyze(payload: Dict[str, Any]):
    """
    Accepts JSON: {"games": [ <GameInput>, ... ]}
    Returns: moneyline_table, spread_table, and CSV strings
    """
    try:
        batch = BatchGames(**payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    try:
        ml_table, ats_table = analyze_games(batch.games)
        ml_csv, ats_csv = tables_to_csv(ml_table, ats_table)
        return {
            "moneyline_table": ml_table,
            "spread_table": ats_table,
            "csv": {
                "moneyline": ml_csv,
                "spread": ats_csv
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analysis error: {e}")


@app.post("/sportsline/analyze/csv/moneyline", response_class=PlainTextResponse)
def analyze_csv_moneyline(payload: Dict[str, Any]):
    """Returns Moneyline report as CSV text."""
    try:
        batch = BatchGames(**payload)
        ml_table, ats_table = analyze_games(batch.games)
        ml_csv, _ = tables_to_csv(ml_table, ats_table)
        return PlainTextResponse(content=ml_csv, media_type="text/csv")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analysis error: {e}")


@app.post("/sportsline/analyze/csv/spread", response_class=PlainTextResponse)
def analyze_csv_spread(payload: Dict[str, Any]):
    """Returns Spread report as CSV text."""
    try:
        batch = BatchGames(**payload)
        ml_table, ats_table = analyze_games(batch.games)
        _, ats_csv = tables_to_csv(ml_table, ats_table)
        return PlainTextResponse(content=ats_csv, media_type="text/csv")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analysis error: {e}")

