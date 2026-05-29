"""Analysis modes (single-select per run).

Each mode gathers *evidence* in its own way, then the shared synthesis step turns that
evidence (plus page signals + goals + KB) into one AnalysisResult.
"""
from __future__ import annotations

from app.analysis.schemas import AnalysisMode
from app.modes.base import ModeContext, ModeOutput
from app.modes.geo_factors import run as run_geo_factors
from app.modes.live_query import run as run_live
from app.modes.peec import run as run_peec
from app.modes.simulation import run as run_simulation

MODE_HANDLERS = {
    AnalysisMode.GEO_FACTORS: run_geo_factors,
    AnalysisMode.SIMULATION: run_simulation,
    AnalysisMode.LIVE: run_live,
    AnalysisMode.PEEC: run_peec,
}

__all__ = ["MODE_HANDLERS", "ModeContext", "ModeOutput"]
