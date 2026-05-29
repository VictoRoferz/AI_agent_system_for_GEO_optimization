"""Health, model list, and option-enumeration endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app.analysis.schemas import AnalysisMode, TargetEngine
from app.config import get_settings
from app.core.models import MODEL_REGISTRY

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/models")
async def list_models() -> dict:
    s = get_settings()
    # Report which providers actually have a key configured, so the UI can hint.
    configured = {
        "anthropic": bool(s.anthropic_api_key),
        "openai": bool(s.openai_api_key),
        "gemini": bool(s.gemini_api_key),
        "openrouter": bool(s.openrouter_api_key),
    }
    return {
        "default": s.default_model,
        "models": [
            {
                "key": m.key,
                "label": m.label,
                "provider": m.provider,
                "configured": configured.get(m.provider, False),
            }
            for m in MODEL_REGISTRY.values()
        ],
    }


@router.get("/options")
async def list_options() -> dict:
    """Modes and target engines available to the New Analysis form."""
    mode_labels = {
        AnalysisMode.GEO_FACTORS: "GEO factors + knowledge base",
        AnalysisMode.SIMULATION: "Simulation (role-play the engine)",
        AnalysisMode.LIVE: "Live query (real engines)",
        AnalysisMode.PEEC: "Peec AI data",
    }
    engine_labels = {
        TargetEngine.CHATGPT: "ChatGPT",
        TargetEngine.AI_OVERVIEWS: "Google AI Overviews",
        TargetEngine.PERPLEXITY: "Perplexity",
        TargetEngine.GEMINI: "Gemini",
    }
    return {
        "modes": [{"key": m.value, "label": mode_labels[m]} for m in AnalysisMode],
        "target_engines": [{"key": e.value, "label": engine_labels[e]} for e in TargetEngine],
    }
