from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import cases, catalog, conversation, errors, fulfillment, handoff, identity, payments, reports, trade
from app.config import settings
from app.db import get_db

app = FastAPI(
    title="Bolmava API",
    version="0.1.0",
    description="Milestone 1 backend. Fictional organizations and simulated money only. Contract: SPEC.md.",
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
errors.install(app)
if settings.auth_mode == "local":
    app.include_router(identity.local_router)
app.include_router(identity.router)
app.include_router(catalog.router)
app.include_router(trade.router)
app.include_router(conversation.router)
app.include_router(payments.router)
app.include_router(fulfillment.router)
app.include_router(cases.router)
app.include_router(handoff.router)
app.include_router(reports.router)


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
