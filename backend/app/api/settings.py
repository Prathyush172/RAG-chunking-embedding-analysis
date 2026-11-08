import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.index import FaissIndexManager
from app.db.models import SettingModel
from app.db.session import get_db
from app.schemas import SettingsSchema, SettingsUpdateSchema

router = APIRouter(prefix="/settings", tags=["settings"])

DEFAULT_SETTINGS = {
    "llm_judge_provider": "mock",
    "llm_judge_model": "mock-judge",
    "openai_api_key": "",
    "gemini_api_key": "",
    "ollama_base_url": "http://localhost:11434",
}


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return key[:3] + "..." + key[-4:]


@router.get("", response_model=SettingsSchema)
def get_settings(db: Session = Depends(get_db)) -> SettingsSchema:
    settings = dict(DEFAULT_SETTINGS)
    rows = db.query(SettingModel).all()
    for r in rows:
        settings[r.key] = r.value

    return SettingsSchema(
        llm_judge_provider=settings.get("llm_judge_provider", "mock"),
        llm_judge_model=settings.get("llm_judge_model", "mock-judge"),
        openai_api_key_masked=_mask_key(settings.get("openai_api_key")),
        gemini_api_key_masked=_mask_key(settings.get("gemini_api_key")),
        ollama_base_url=settings.get("ollama_base_url", "http://localhost:11434"),
    )


@router.put("", response_model=SettingsSchema)
def update_settings(payload: SettingsUpdateSchema, db: Session = Depends(get_db)) -> SettingsSchema:
    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        if v is not None:
            existing = db.query(SettingModel).filter(SettingModel.key == k).first()
            if existing:
                existing.value = str(v)
            else:
                db.add(SettingModel(key=k, value=str(v)))
    db.commit()
    return get_settings(db)


@router.post("/clear-cache")
def clear_caches() -> dict[str, str]:
    mgr = FaissIndexManager()
    mgr.clear_cache()
    return {"message": "Embedding and FAISS index disk cache cleared successfully"}
