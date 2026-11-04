import json
import os
import hashlib
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import firebase_admin
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from timezone_utils import get_timezone

load_dotenv()

COLLECTION_NAME = "subscribers"
PENDING_COLLECTION_NAME = "pending_subscriptions"
CONFIRMATION_TTL_HOURS = 24
SCHEDULER_ENABLED = os.getenv("ENABLE_SCHEDULER", "true").lower() not in {
    "0",
    "false",
    "no",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler_thread = None
    stop_event = Event()

    if SCHEDULER_ENABLED:
        from scheduler import run_scheduler

        scheduler_thread = Thread(
            target=run_scheduler,
            args=(stop_event,),
            name="newsletter-scheduler",
            daemon=True,
        )
        scheduler_thread.start()

    try:
        yield
    finally:
        if scheduler_thread is not None:
            stop_event.set()
            scheduler_thread.join(timeout=10)


app = FastAPI(
    title="Tech Daily Newsletter API",
    description="Register for scheduled technology-news email briefings.",
    version="1.0.0",
    lifespan=lifespan,
)

_rate_limit_state: dict[str, tuple[float, int]] = {}


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    client_host = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start, count = _rate_limit_state.get(client_host, (now, 0))
    if now - window_start >= 60:
        window_start, count = now, 0
    count += 1
    _rate_limit_state[client_host] = (window_start, count)
    if len(_rate_limit_state) > 10_000:
        _rate_limit_state.clear()
    if count > 30:
        return JSONResponse(
            {"detail": "Too many requests. Please try again later."},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": "60"},
        )

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    return response


def _configured_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "")
    frontend_url = os.getenv("FRONTEND_URL", "")

    def normalize_origin(value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.netloc or parsed.path not in {"", "/"}:
            raise RuntimeError(
                "CORS origins must be complete origins such as "
                "'https://example.com', without a path."
            )
        return f"{parsed.scheme}://{parsed.netloc}"

    origins = []
    for configured_origin in configured.split(","):
        if configured_origin.strip():
            origin = normalize_origin(configured_origin)
            if origin not in origins:
                origins.append(origin)

    # FRONTEND_URL is already required for confirmation links and provides a
    # reliable CORS fallback when ALLOWED_ORIGINS was not added separately.
    if frontend_url.strip():
        frontend_origin = normalize_origin(frontend_url)
        if frontend_origin not in origins:
            origins.append(frontend_origin)

    return origins


allowed_origins = _configured_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


def initialize_firestore():
    if firebase_admin._apps:
        return firestore.client()

    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON is missing from your environment/.env file."
        )

    try:
        service_account_info = json.loads(service_account_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON must contain valid JSON."
        ) from exc

    cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(cred)
    return firestore.client()


db = None


def get_firestore():
    global db
    if db is None:
        db = initialize_firestore()
    return db


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    frequency: Literal["daily", "weekly"]
    time_of_day: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="Asia/Kolkata", min_length=1, max_length=64)
    day_of_week: Literal[
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday"
    ] = "monday"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            get_timezone(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                "Use a valid IANA timezone, for example 'Asia/Kolkata'."
            ) from exc
        return value


@app.get("/")
def root():
    return {"message": "Tech Daily Newsletter API", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/register", status_code=status.HTTP_202_ACCEPTED)
def register_subscriber(payload: RegistrationRequest):
    email = str(payload.email).lower()
    database = get_firestore()
    subscriber_ref = database.collection(COLLECTION_NAME).document(email)

    subscriber_data = {
        "name": payload.name,
        "email": email,
        "frequency": payload.frequency,
        "time_of_day": payload.time_of_day,
        "timezone": payload.timezone,
        "day_of_week": payload.day_of_week if payload.frequency == "weekly" else None,
        "active": False,
        "updated_at": datetime.now(timezone.utc),
    }

    try:
        existing = subscriber_ref.get()
        if existing.exists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email is already subscribed.",
            )
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        pending_ref = database.collection(PENDING_COLLECTION_NAME).document()
        pending_ref.set({
            **subscriber_data,
            "token_hash": token_hash,
            "expires_at": datetime.now(timezone.utc) + timedelta(
                hours=CONFIRMATION_TTL_HOURS
            ),
        })
        from send_email import send_confirmation_email

        send_confirmation_email(email, token)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not save your subscription right now. Please try again later.",
        ) from exc

    return {
        "message": "Check your inbox to confirm your subscription.",
    }


@app.get("/api/confirm")
def confirm_subscriber(
    token: str = Query(min_length=20, max_length=128),
):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    database = get_firestore()
    pending_query = database.collection(PENDING_COLLECTION_NAME).where(
        filter=FieldFilter("token_hash", "==", token_hash)
    ).limit(1)
    pending_documents = list(pending_query.stream())
    if not pending_documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This confirmation link is invalid or has expired.",
        )

    pending_document = pending_documents[0]
    pending = pending_document.to_dict() or {}
    expires_at = pending.get("expires_at")
    if not isinstance(expires_at, datetime) or expires_at < datetime.now(timezone.utc):
        pending_document.reference.delete()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This confirmation link is invalid or has expired.",
        )

    email = str(pending["email"]).lower()
    subscriber_data = {
        key: value for key, value in pending.items()
        if key not in {"token_hash", "expires_at"}
    }
    subscriber_data.update({
        "email": email,
        "active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    database.collection(COLLECTION_NAME).document(email).set(subscriber_data)
    pending_document.reference.delete()
    return {"message": "Subscription confirmed. Your first briefing is scheduled."}
