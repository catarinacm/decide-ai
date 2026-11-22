"""Tabelas do decide.ai (as 8 do docx + events). Espelham backend/migrations/001_schema.sql."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer,
                        Numeric, String, Text, UniqueConstraint, Uuid, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

GROUP_STATUSES = ("coletando_preferencias", "match_disponivel", "votacao_aberta",
                  "escolha_concluida", "reserva_simulada", "avaliado")


def _status_check() -> str:
    return "status IN (" + ", ".join(f"'{s}'" for s in GROUP_STATUSES) + ")"


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now(),
                                                 onupdate=utcnow, nullable=False)


class RestaurantRow(Timestamps, Base):
    __tablename__ = "restaurants"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    cuisine_type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    neighborhood: Mapped[str] = mapped_column(String(60), nullable=False)
    city: Mapped[str] = mapped_column(String(60), nullable=False, default="São Paulo")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    avg_price: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    dietary_options: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    ambiences: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    opening_hours: Mapped[dict] = mapped_column(JSONType, nullable=False)
    availability_rate: Mapped[float] = mapped_column(Float, nullable=False)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    simulated_benefit: Mapped[str | None] = mapped_column(Text)
    accepts_reservation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_fictional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (
        CheckConstraint("avg_price > 0", name="ck_restaurants_price"),
        CheckConstraint("capacity >= 2", name="ck_restaurants_capacity"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_restaurants_rating"),
        CheckConstraint("availability_rate > 0 AND availability_rate <= 1", name="ck_restaurants_availability"),
        CheckConstraint("is_fictional = true", name="ck_restaurants_fictional"),
    )


class GroupRow(Timestamps, Base):
    __tablename__ = "groups"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    invite_code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    occasion: Mapped[str | None] = mapped_column(String(40))
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[str] = mapped_column(String(5), nullable=False)
    budget_per_person: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    neighborhood: Mapped[str] = mapped_column(String(60), nullable=False)
    city: Mapped[str] = mapped_column(String(60), nullable=False, default="São Paulo")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="coletando_preferencias")
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vote_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    organizer_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    match_summary: Mapped[dict | None] = mapped_column(JSONType)
    winner_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    participants: Mapped[list["ParticipantRow"]] = relationship(
        back_populates="group", order_by="ParticipantRow.joined_at", cascade="all, delete-orphan")
    __table_args__ = (
        CheckConstraint(_status_check(), name="ck_groups_status"),
        CheckConstraint("budget_per_person > 0", name="ck_groups_budget"),
        CheckConstraint("party_size BETWEEN 2 AND 20", name="ck_groups_party_size"),
        CheckConstraint("current_round >= 0", name="ck_groups_round"),
    )


class ParticipantRow(Timestamps, Base):
    __tablename__ = "participants"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    nickname: Mapped[str] = mapped_column(String(30), nullable=False)
    nickname_key: Mapped[str] = mapped_column(String(30), nullable=False)  # apelido normalizado, único por grupo
    location: Mapped[str | None] = mapped_column(String(60))  # bairro de saída
    is_organizer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False)

    group: Mapped[GroupRow] = relationship(back_populates="participants")
    preferences: Mapped["PreferenceRow | None"] = relationship(back_populates="participant", uselist=False,
                                                               cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("group_id", "nickname_key", name="uq_participants_nickname"),)


class PreferenceRow(Timestamps, Base):
    __tablename__ = "preferences"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"),
                                                      unique=True, nullable=False)
    cuisines: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    dietary_restrictions: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    ambience: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    max_distance: Mapped[float] = mapped_column(Float, nullable=False, default=10)
    max_budget: Mapped[float | None] = mapped_column(Numeric(8, 2))
    additional_preferences: Mapped[str | None] = mapped_column(Text)
    free_text: Mapped[str | None] = mapped_column(Text)
    parsed_by: Mapped[str | None] = mapped_column(String(10))  # 'ia', 'fallback' ou nulo (preenchido à mão)

    participant: Mapped[ParticipantRow] = relationship(back_populates="preferences")
    __table_args__ = (
        CheckConstraint("max_distance > 0 AND max_distance <= 60", name="ck_preferences_distance"),
        CheckConstraint("max_budget IS NULL OR max_budget > 0", name="ck_preferences_budget"),
    )


class RecommendationRow(Timestamps, Base):
    __tablename__ = "recommendations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    mean_score: Mapped[float] = mapped_column(Float, nullable=False)
    penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    breakdown: Mapped[list] = mapped_column(JSONType, nullable=False)
    highlights: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    attention_point: Mapped[str] = mapped_column(Text, nullable=False)
    avg_distance_km: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reason_source: Mapped[str] = mapped_column(String(10), nullable=False)  # 'ia' ou 'fallback'
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    restaurant: Mapped[RestaurantRow] = relationship()
    __table_args__ = (
        UniqueConstraint("group_id", "round_number", "rank", name="uq_recommendations_rank"),
        UniqueConstraint("group_id", "round_number", "restaurant_id", name="uq_recommendations_restaurant"),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_recommendations_score"),
        CheckConstraint("rank BETWEEN 1 AND 3", name="ck_recommendations_rank"),
        CheckConstraint("reason_source IN ('ia', 'fallback')", name="ck_recommendations_source"),
    )


class VoteRow(Timestamps, Base):
    __tablename__ = "votes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), nullable=False)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"),
                                                         nullable=False)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Um voto ativo por participante por rodada: votar de novo atualiza esta linha.
    __table_args__ = (UniqueConstraint("participant_id", "round_number", name="uq_votes_participant_round"),)


class ReservationRow(Timestamps, Base):
    __tablename__ = "reservations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("restaurants.id"), nullable=False)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recommendations.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="confirmada")
    booking_time: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmation_code: Mapped[str] = mapped_column(String(20), nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    restaurant: Mapped[RestaurantRow] = relationship()
    __table_args__ = (
        CheckConstraint("is_simulated = true", name="ck_reservations_simulated"),
        CheckConstraint("status IN ('confirmada', 'cancelada')", name="ck_reservations_status"),
        # No máximo uma reserva concluída por grupo.
        Index("uq_reservations_one_confirmed", "group_id", unique=True,
              sqlite_where=text("status = 'confirmada'"), postgresql_where=text("status = 'confirmada'")),
    )


class ReviewRow(Timestamps, Base):
    __tablename__ = "reviews"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False)
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reviews_rating"),
        UniqueConstraint("reservation_id", "participant_id", name="uq_reviews_participant"),
    )


class EventRow(Base):
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    participant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("participants.id", ondelete="SET NULL"))
    properties: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False)
    __table_args__ = (Index("ix_events_name_group", "name", "group_id"),)
