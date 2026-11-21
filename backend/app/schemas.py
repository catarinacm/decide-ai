"""Validação de entrada com Pydantic. Todos os valores categóricos são checados contra data/reference.json."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.reference import AMBIENCES, CUISINES, DIETS, NEIGHBORHOODS, OCCASIONS

SP_TZ = timezone(timedelta(hours=-3))
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
NICK = re.compile(r"^[\wÀ-ÿ .'-]{2,30}$")


def today_sp() -> date:
    return datetime.now(SP_TZ).date()


def _check_subset(values: list[str], allowed: dict, what: str) -> list[str]:
    out = []
    for v in values:
        if v not in allowed:
            raise ValueError(f"{what} inválido: '{v}'. Permitidos: {', '.join(allowed)}")
        if v not in out:
            out.append(v)
    return out


def clean_nickname(v: str) -> str:
    v = " ".join(v.split())
    if not NICK.match(v):
        raise ValueError("Use um apelido de 2 a 30 letras ou números.")
    # Privacidade: o apelido não pode ser e-mail nem telefone.
    if "@" in v or sum(c.isdigit() for c in v) >= 6:
        raise ValueError("Use um apelido, não e-mail nem telefone.")
    return v


def validate_event_date(v: date | None) -> date | None:
    if v is None:
        return None
    if v < today_sp():
        raise ValueError("A data do encontro não pode estar no passado.")
    if v > today_sp() + timedelta(days=365):
        raise ValueError("Escolha uma data dentro dos próximos 12 meses.")
    return v


def validate_time(v: str | None) -> str | None:
    if v is not None and not HHMM.match(v):
        raise ValueError("Horário no formato HH:MM.")
    return v


def validate_deadline(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=SP_TZ)
    if v <= datetime.now(timezone.utc):
        raise ValueError("O prazo da votação precisa estar no futuro.")
    return v


class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    event_date: date
    event_time: str
    budget_per_person: float = Field(ge=20, le=1000)
    party_size: int = Field(ge=2, le=20)
    neighborhood: str
    city: Literal["São Paulo"] = "São Paulo"
    occasion: str | None = None
    vote_deadline: datetime | None = None
    organizer_nickname: str

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("event_date")
    @classmethod
    def _date(cls, v):
        return validate_event_date(v)

    @field_validator("event_time")
    @classmethod
    def _time(cls, v):
        return validate_time(v)

    @field_validator("neighborhood")
    @classmethod
    def _hood(cls, v: str) -> str:
        if v not in NEIGHBORHOODS:
            raise ValueError("Bairro fora da lista atendida pelo protótipo.")
        return v

    @field_validator("occasion")
    @classmethod
    def _occasion(cls, v: str | None) -> str | None:
        if v and v not in OCCASIONS:
            raise ValueError("Ocasião inválida.")
        return v or None

    @field_validator("organizer_nickname")
    @classmethod
    def _nick(cls, v: str) -> str:
        return clean_nickname(v)

    @field_validator("vote_deadline")
    @classmethod
    def _deadline(cls, v):
        return validate_deadline(v)


class GroupUpdate(BaseModel):
    """Ajustes do organizador (ex.: aplicar uma sugestão do Match). Invalida a rodada atual."""
    budget_per_person: float | None = Field(default=None, ge=20, le=1000)
    event_date: date | None = None
    event_time: str | None = None
    party_size: int | None = Field(default=None, ge=2, le=20)
    vote_deadline: datetime | None = None

    @field_validator("event_date")
    @classmethod
    def _date(cls, v):
        return validate_event_date(v)

    @field_validator("event_time")
    @classmethod
    def _time(cls, v):
        return validate_time(v)

    @field_validator("vote_deadline")
    @classmethod
    def _deadline(cls, v):
        return validate_deadline(v)


class JoinIn(BaseModel):
    invite_code: str = Field(min_length=6, max_length=12)
    nickname: str
    is_simulated: bool = False

    @field_validator("invite_code")
    @classmethod
    def _code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("nickname")
    @classmethod
    def _nick(cls, v: str) -> str:
        return clean_nickname(v)


class PreferencesIn(BaseModel):
    cuisines: list[str] = Field(default_factory=list, max_length=8)
    dietary_restrictions: list[str] = Field(default_factory=list, max_length=4)
    ambiences: list[str] = Field(default_factory=list, max_length=5)
    origin_neighborhood: str
    max_distance_km: float = Field(default=10, ge=1, le=60)
    max_budget: float | None = Field(default=None, ge=20, le=1000)
    additional_preferences: str | None = Field(default=None, max_length=300)
    free_text: str | None = Field(default=None, max_length=500)
    parsed_by: Literal["ia", "fallback"] | None = None

    @field_validator("cuisines")
    @classmethod
    def _c(cls, v):
        return _check_subset(v, CUISINES, "Culinária")

    @field_validator("dietary_restrictions")
    @classmethod
    def _d(cls, v):
        return _check_subset(v, DIETS, "Restrição")

    @field_validator("ambiences")
    @classmethod
    def _a(cls, v):
        return _check_subset(v, AMBIENCES, "Ambiente")

    @field_validator("origin_neighborhood")
    @classmethod
    def _o(cls, v):
        if v not in NEIGHBORHOODS:
            raise ValueError("Bairro de saída fora da lista do protótipo.")
        return v


class MatchIn(BaseModel):
    force: bool = False


class VoteIn(BaseModel):
    recommendation_id: uuid.UUID


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class ParseIn(BaseModel):
    text: str = Field(min_length=3, max_length=500)


class ParsedPreferences(BaseModel):
    """Saída da Função A (IA ou regras). A interface mostra para a pessoa conferir antes de salvar."""
    cuisines: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    ambiences: list[str] = Field(default_factory=list)
    origin_neighborhood: str | None = None
    max_distance_km: float | None = None
    max_budget: float | None = None
    budget_hint: str = ""
    additional_preferences: str = ""

    @model_validator(mode="after")
    def _sanitize(self):
        # Descarta silenciosamente o que não está na lista permitida: o formulário é a fonte da regra.
        self.cuisines = [c for c in dict.fromkeys(self.cuisines) if c in CUISINES][:8]
        self.dietary_restrictions = [d for d in dict.fromkeys(self.dietary_restrictions) if d in DIETS]
        self.ambiences = [a for a in dict.fromkeys(self.ambiences) if a in AMBIENCES]
        if self.origin_neighborhood not in NEIGHBORHOODS:
            self.origin_neighborhood = None
        if self.max_distance_km is not None and not (1 <= self.max_distance_km <= 60):
            self.max_distance_km = None
        if self.max_budget is not None and not (20 <= self.max_budget <= 1000):
            self.max_budget = None
        self.budget_hint = self.budget_hint[:200]
        self.additional_preferences = self.additional_preferences[:300]
        return self
