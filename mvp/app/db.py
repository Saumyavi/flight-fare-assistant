from datetime import datetime, date, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session
from .config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    whatsapp_number: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=_utcnow)


class Watch(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    origin: str
    destination: str
    depart_from: date
    depart_to: date
    return_from: Optional[date] = None
    return_to: Optional[date] = None
    max_price: float
    currency: str = "INR"
    adults: int = 1
    active: bool = Field(default=True, index=True)
    last_alert_at: Optional[datetime] = None
    last_alert_price: Optional[float] = None
    last_polled_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)


class PriceSample(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    watch_id: int = Field(foreign_key="watch.id", index=True)
    price: float
    currency: str
    depart_date: date
    return_date: Optional[date] = None
    deeplink: Optional[str] = None
    raw_carrier: Optional[str] = None
    sampled_at: datetime = Field(default_factory=_utcnow)


engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
