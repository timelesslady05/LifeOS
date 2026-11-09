from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


load_dotenv(Path(__file__).with_name(".env"))

APP_ENV = os.getenv("APP_ENV", "development")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY and APP_ENV == "production":
    raise RuntimeError("SECRET_KEY must be configured in production.")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(48)
    print("LifeOS generated a temporary development secret; all sessions expire on restart.")

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 30
REFRESH_COOKIE = "lifeos_refresh"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "strict").lower()
if COOKIE_SAMESITE not in {"strict", "lax", "none"}:
    raise RuntimeError("COOKIE_SAMESITE must be strict, lax, or none.")
FRONTEND_ORIGINS = {
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5500,http://127.0.0.1:5500",
    ).split(",")
    if origin.strip()
}

database_url = os.getenv("DATABASE_URL", "sqlite:///./lifeos.db")
if APP_ENV == "production":
    if len(SECRET_KEY) < 32 or SECRET_KEY == "replace-with-a-long-random-secret":
        raise RuntimeError("SECRET_KEY must contain at least 32 characters in production.")
    if not COOKIE_SECURE:
        raise RuntimeError("Set COOKIE_SECURE=true in production.")
    if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
        raise RuntimeError("SameSite=None cookies require COOKIE_SECURE=true.")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("Configure PostgreSQL with DATABASE_URL in production.")
    if any(not origin.startswith("https://") for origin in FRONTEND_ORIGINS):
        raise RuntimeError("Production frontend origins must use HTTPS.")
engine_options: dict[str, Any] = {"pool_pre_ping": True}
if database_url.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(60))
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class LifeData(Base):
    __tablename__ = "life_data"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RegisterRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=60)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Name must contain at least 2 characters.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class LifeDataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: dict[str, Any]

    @field_validator("data")
    @classmethod
    def validate_life_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        collections = {
            "tasks", "habits", "goals", "events", "notes", "transactions", "wellness"
        }
        expected = collections | {"budgets"}
        if set(value) != expected:
            raise ValueError("Workspace data has an unexpected shape.")
        for collection in collections:
            items = value[collection]
            if not isinstance(items, list) or len(items) > 500:
                raise ValueError(f"{collection} must be a list of at most 500 items.")
            if any(not isinstance(item, dict) for item in items):
                raise ValueError(f"Every {collection} item must be an object.")
        budgets = value["budgets"]
        if not isinstance(budgets, dict) or len(budgets) > 30:
            raise ValueError("Budgets must be an object with at most 30 categories.")
        if any(
            not isinstance(category, str)
            or not isinstance(amount, (int, float))
            or isinstance(amount, bool)
            or amount < 0
            for category, amount in budgets.items()
        ):
            raise ValueError("Budget categories must have non-negative numeric amounts.")
        return value


password_hasher = PasswordHash.recommended()
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))
bearer_scheme = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="LifeOS API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(FRONTEND_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-LifeOS-Request"],
)


@app.middleware("http")
async def protect_api_requests(request: Request, call_next: Any) -> Response:
    if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.headers.get("origin") not in FRONTEND_ORIGINS:
            return JSONResponse(status_code=403, content={"detail": "Request origin is not allowed."})
        if request.url.path in {"/api/auth/refresh", "/api/auth/logout"} and request.headers.get("x-lifeos-request") != "1":
            return JSONResponse(status_code=403, content={"detail": "A valid LifeOS request header is required."})
        if int(request.headers.get("content-length", "0")) > 1_000_000:
            return JSONResponse(status_code=413, content={"detail": "Request body is too large."})
    return await call_next(request)


def get_db():
    with SessionLocal() as db:
        yield db


def user_response(user: User) -> dict[str, str]:
    return {"id": user.id, "email": user.email, "display_name": user.display_name}


def token_response(user: User, session_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    access_token = jwt.encode(
        {
            "sub": user.id,
            "sid": session_id,
            "iat": now,
            "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
        },
        SECRET_KEY,
        algorithm="HS256",
    )
    return {"access_token": access_token, "token_type": "bearer", "user": user_response(user)}


def set_refresh_cookie(response: Response, session_id: str, secret: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=f"{session_id}.{secret}",
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/api/auth",
    )


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User, response: Response) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(48)
    db.add(
        UserSession(
            id=session_id,
            user_id=user.id,
            refresh_hash=hash_secret(secret),
            expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        )
    )
    db.commit()
    set_refresh_cookie(response, session_id, secret)
    return token_response(user, session_id)


def parse_refresh_cookie(request: Request) -> tuple[str, str]:
    value = request.cookies.get(REFRESH_COOKIE, "")
    session_id, separator, secret = value.partition(".")
    if not separator or not secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.")
    return session_id, secret


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        session_id = payload.get("sid")
        if not isinstance(user_id, str) or not isinstance(session_id, str):
            raise InvalidTokenError("Missing subject or session.")
    except InvalidTokenError as error:
        raise HTTPException(status_code=401, detail="Your session expired. Sign in again.") from error
    session = db.get(UserSession, session_id)
    user = db.get(User, user_id)
    if (
        session is None
        or session.user_id != user_id
        or session.revoked
        or session.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc)
        or user is None
    ):
        raise HTTPException(status_code=401, detail="Your session expired. Sign in again.")
    return user


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "lifeos-api"}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = User(
        email=str(payload.email),
        display_name=payload.display_name,
        password_hash=password_hasher.hash(payload.password),
    )
    db.add(user)
    try:
        db.flush()
        result = create_session(db, user, response)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with that email already exists.") from error
    return result


@app.post("/api/auth/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.scalar(select(User).where(User.email == str(payload.email)))
    if user is None:
        password_hasher.verify(payload.password, dummy_password_hash)
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    if not password_hasher.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return create_session(db, user, response)


@app.post("/api/auth/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, Any]:
    session_id, secret = parse_refresh_cookie(request)
    session = db.scalar(select(UserSession).where(UserSession.id == session_id).with_for_update())
    now = datetime.now(timezone.utc)
    if session is None or session.revoked or session.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=401, detail="Your session expired. Sign in again.")
    if not secrets.compare_digest(session.refresh_hash, hash_secret(secret)):
        session.revoked = True
        db.commit()
        raise HTTPException(status_code=401, detail="Your session expired. Sign in again.")
    user = db.get(User, session.user_id)
    if user is None:
        session.revoked = True
        db.commit()
        raise HTTPException(status_code=401, detail="Your session expired. Sign in again.")
    replacement = secrets.token_urlsafe(48)
    session.refresh_hash = hash_secret(replacement)
    session.expires_at = now + timedelta(days=REFRESH_TOKEN_DAYS)
    db.commit()
    set_refresh_cookie(response, session.id, replacement)
    return token_response(user, session.id)


@app.post("/api/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    try:
        session_id, _ = parse_refresh_cookie(request)
    except HTTPException:
        session_id = ""
    try:
        _, secret = parse_refresh_cookie(request)
    except HTTPException:
        secret = ""
    session = db.get(UserSession, session_id) if session_id else None
    if session is not None and secrets.compare_digest(session.refresh_hash, hash_secret(secret)):
        session.revoked = True
        db.commit()
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/auth", secure=COOKIE_SECURE, httponly=True, samesite=COOKIE_SAMESITE)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@app.get("/api/auth/me")
def who_am_i(user: User = Depends(current_user)) -> dict[str, str]:
    return user_response(user)


@app.get("/api/data")
def read_life_data(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    record = db.get(LifeData, user.id)
    if record is None:
        return {"data": None}
    return {"data": record.data}


@app.put("/api/data")
def write_life_data(
    payload: LifeDataRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    record = db.get(LifeData, user.id)
    if record is None:
        record = LifeData(user_id=user.id, data=payload.data)
        db.add(record)
    else:
        record.data = payload.data
    record.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "saved"}
