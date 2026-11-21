"""Votação, desempate, reserva simulada e avaliação."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError, not_found
from app.models.tables import (GroupRow, ParticipantRow, RecommendationRow, ReservationRow, ReviewRow, VoteRow,
                               utcnow)
from app.services.events import log_event
from app.services.state_machine import require_status, transition


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def active_recommendations(db: Session, group: GroupRow) -> list[RecommendationRow]:
    return list(db.scalars(select(RecommendationRow).where(
        RecommendationRow.group_id == group.id, RecommendationRow.round_number == group.current_round,
        RecommendationRow.is_active.is_(True)).order_by(RecommendationRow.rank)).all())


def round_votes(db: Session, group: GroupRow) -> list[VoteRow]:
    """Votos válidos da rodada atual. Votos em recomendações invalidadas deixam de contar."""
    return list(db.scalars(
        select(VoteRow).join(RecommendationRow, VoteRow.recommendation_id == RecommendationRow.id)
        .where(VoteRow.group_id == group.id, VoteRow.round_number == group.current_round,
               RecommendationRow.is_active.is_(True))).all())


# ------------------------------------------------------------------- votos

def cast_vote(db: Session, group: GroupRow, participant: ParticipantRow, recommendation_id) -> VoteRow:
    maybe_auto_close(db, group)
    require_status(group, "votacao_aberta", action="votar")
    rec = db.get(RecommendationRow, recommendation_id)
    if rec is None or rec.group_id != group.id:
        raise not_found("Recomendação")
    if not rec.is_active or rec.round_number != group.current_round:
        raise AppError(409, "rodada_invalidada", "Esta recomendação é de uma rodada anterior. Veja o ranking atual.")
    vote = db.scalar(select(VoteRow).where(VoteRow.participant_id == participant.id,
                                           VoteRow.round_number == group.current_round))
    if vote is None:
        vote = VoteRow(participant_id=participant.id, recommendation_id=rec.id, group_id=group.id,
                       round_number=group.current_round)
        db.add(vote)
        log_event(db, "vote_cast", group, participant.id, round_number=group.current_round, updated=False)
    elif vote.recommendation_id != rec.id:
        vote.recommendation_id = rec.id  # votar de novo atualiza, não duplica
        vote.updated_at = utcnow()
        log_event(db, "vote_cast", group, participant.id, round_number=group.current_round, updated=True)
    db.flush()
    return vote


def tally(db: Session, group: GroupRow) -> list[dict]:
    recs = active_recommendations(db, group)
    votes = round_votes(db, group)
    names = {p.id: p.nickname for p in group.participants}
    out = []
    for rec in recs:
        voters = [names.get(v.participant_id, "?") for v in votes if v.recommendation_id == rec.id]
        out.append({"recommendation": rec, "votes": len(voters), "voters": voters})
    return out


def pick_winner(rows: list[dict]) -> tuple[dict, str]:
    """Mais votos vence. Empate: maior score coletivo; depois, melhor posição no ranking."""
    ranked = sorted(rows, key=lambda t: (-t["votes"], -t["recommendation"].score, t["recommendation"].rank))
    win = ranked[0]
    w = win["recommendation"]
    total = sum(t["votes"] for t in rows)
    if total == 0:
        return win, (f"Ninguém votou; venceu {w.restaurant.name}, a opção com maior score coletivo "
                     f"({w.score:.0f}/100).")
    tied = [t for t in ranked if t["votes"] == win["votes"]]
    if len(tied) > 1:
        others = ", ".join(f"{t['recommendation'].restaurant.name} ({t['recommendation'].score:.0f})" for t in tied[1:])
        return win, (f"Empate com {win['votes']} voto(s) cada. Pelo critério de desempate, venceu "
                     f"{w.restaurant.name}, com o maior score coletivo ({w.score:.0f}/100) contra {others}.")
    return win, f"{w.restaurant.name} venceu com {win['votes']} de {total} voto(s)."


def close_voting(db: Session, group: GroupRow, *, reason: str) -> RecommendationRow:
    require_status(group, "votacao_aberta", action="encerrar a votação")
    rows = tally(db, group)
    if not rows:
        raise AppError(409, "sem_recomendacoes", "Não há recomendações ativas para encerrar.")
    win, note = pick_winner(rows)
    group.winner_recommendation_id = win["recommendation"].id
    group.decision_note = note
    group.decided_at = utcnow()
    transition(group, "escolha_concluida")
    seconds = (as_utc(group.decided_at) - as_utc(group.created_at)).total_seconds()
    log_event(db, "choice_completed", group, round_number=group.current_round, reason=reason,
              seconds_to_decision=round(seconds), votes=sum(t["votes"] for t in rows),
              tie="Empate" in note)
    db.flush()
    return win["recommendation"]


def maybe_auto_close(db: Session, group: GroupRow) -> bool:
    """Encerra a votação se o prazo opcional já passou (D-003)."""
    if group.status == "votacao_aberta" and group.vote_deadline and as_utc(group.vote_deadline) <= utcnow():
        close_voting(db, group, reason="prazo")
        return True
    return False


# ------------------------------------------------------------------ reserva

def create_reservation(db: Session, group: GroupRow) -> ReservationRow:
    require_status(group, "escolha_concluida", action="reservar (a escolha precisa estar concluída)")
    rec = db.get(RecommendationRow, group.winner_recommendation_id)
    booking = datetime.combine(group.event_date, datetime.strptime(group.event_time, "%H:%M").time())
    res = ReservationRow(group_id=group.id, restaurant_id=rec.restaurant_id, recommendation_id=rec.id,
                         status="confirmada", booking_time=booking,
                         party_size=max(group.party_size, len(group.participants)),
                         confirmation_code="SIM-" + secrets.token_hex(3).upper(), is_simulated=True)
    db.add(res)
    transition(group, "reserva_simulada")
    db.flush()
    log_event(db, "reservation_simulated", group, reservation_id=str(res.id), is_simulated=True)
    return res


def confirmed_reservation(db: Session, group: GroupRow) -> ReservationRow | None:
    return db.scalar(select(ReservationRow).where(ReservationRow.group_id == group.id,
                                                  ReservationRow.status == "confirmada"))


def add_review(db: Session, reservation: ReservationRow, participant: ParticipantRow, rating: int,
               comment: str | None) -> ReviewRow:
    group = db.get(GroupRow, reservation.group_id)
    if participant.group_id != group.id:
        raise AppError(403, "sem_permissao", "Só participantes deste encontro podem avaliá-lo.")
    require_status(group, "reserva_simulada", "avaliado", action="avaliar")
    review = db.scalar(select(ReviewRow).where(ReviewRow.reservation_id == reservation.id,
                                               ReviewRow.participant_id == participant.id))
    if review is None:
        review = ReviewRow(reservation_id=reservation.id, participant_id=participant.id, rating=rating, comment=comment)
        db.add(review)
    else:
        review.rating, review.comment = rating, comment
    if group.status == "reserva_simulada":
        transition(group, "avaliado")
    log_event(db, "review_submitted", group, participant.id, rating=rating)
    db.flush()
    return review
