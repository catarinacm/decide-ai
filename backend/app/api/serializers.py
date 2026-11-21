"""Formato das respostas. O frontend nunca precisa conhecer o algoritmo, só estes campos."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models.tables import GroupRow, RecommendationRow, ReservationRow, RestaurantRow, ReviewRow
from app.reference import AMBIENCES, CUISINES, DIETS, OCCASIONS
from app.services import decision_service as ds
from app.services.auth import Caller
from app.services.match_service import MIN_FOR_FORCED_MATCH, missing_preferences, with_preferences
from app.services.state_machine import LABELS, OPEN_STATES

DIETARY_DISCLAIMER = ("As opções alimentares vêm do cadastro fictício do restaurante. Em caso de alergia ou "
                      "intolerância, confirme sempre com o restaurante.")


def iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def restaurant_out(r: RestaurantRow) -> dict:
    return {
        "id": str(r.id), "name": r.name, "cuisine": r.cuisine_type, "cuisine_label": CUISINES.get(r.cuisine_type),
        "description": r.description, "neighborhood": r.neighborhood, "avg_price": float(r.avg_price),
        "dietary_options": r.dietary_options, "dietary_labels": [DIETS[d] for d in r.dietary_options],
        "ambiences": r.ambiences, "ambience_labels": [AMBIENCES[a] for a in r.ambiences],
        "rating": r.rating, "rating_count": r.rating_count, "capacity": r.capacity,
        "simulated_benefit": r.simulated_benefit, "accepts_reservation": r.accepts_reservation,
        "is_fictional": r.is_fictional,
    }


def recommendation_out(rec: RecommendationRow, votes: int | None = None, voters: list[str] | None = None) -> dict:
    out = {
        "recommendation_id": str(rec.id), "round_number": rec.round_number, "rank": rec.rank,
        "score": rec.score, "mean_score": rec.mean_score, "penalty": rec.penalty,
        "avg_distance_km": rec.avg_distance_km, "explanation": rec.reason, "explanation_source": rec.reason_source,
        "attention_point": rec.attention_point, "highlights": rec.highlights, "breakdown": rec.breakdown,
        "is_active": rec.is_active, "restaurant": restaurant_out(rec.restaurant),
    }
    if votes is not None:
        out["votes"], out["voters"] = votes, voters or []
    return out


def preferences_out(p) -> dict | None:
    pref = p.preferences
    if pref is None:
        return None
    return {"cuisines": pref.cuisines, "dietary_restrictions": pref.dietary_restrictions, "ambiences": pref.ambience,
            "origin_neighborhood": p.location, "max_distance_km": pref.max_distance,
            "max_budget": float(pref.max_budget) if pref.max_budget is not None else None,
            "additional_preferences": pref.additional_preferences, "free_text": pref.free_text,
            "parsed_by": pref.parsed_by, "updated_at": iso(pref.updated_at)}


def reservation_out(db: Session, res: ReservationRow, me_id=None) -> dict:
    reviews = db.query(ReviewRow).filter(ReviewRow.reservation_id == res.id).all()
    mine = next((r for r in reviews if me_id and r.participant_id == me_id), None)
    return {
        "id": str(res.id), "status": res.status, "is_simulated": res.is_simulated,
        "label": "Reserva simulada", "confirmation_code": res.confirmation_code,
        "booking_time": res.booking_time.isoformat(), "party_size": res.party_size,
        "restaurant": restaurant_out(res.restaurant), "created_at": iso(res.created_at),
        "reviews": {"count": len(reviews),
                    "average": round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None},
        "my_review": {"rating": mine.rating, "comment": mine.comment} if mine else None,
    }


def group_out(db: Session, caller: Caller) -> dict:
    g: GroupRow = caller.group
    votes = {v.participant_id: v.recommendation_id for v in ds.round_votes(db, g)} if g.current_round else {}
    me = caller.participant
    answered, missing = with_preferences(g), missing_preferences(g)
    winner = db.get(RecommendationRow, g.winner_recommendation_id) if g.winner_recommendation_id else None
    res = ds.confirmed_reservation(db, g)
    return {
        "id": str(g.id), "name": g.name, "occasion": g.occasion, "occasion_label": OCCASIONS.get(g.occasion or ""),
        "event_date": g.event_date.isoformat(), "event_time": g.event_time,
        "budget_per_person": float(g.budget_per_person), "party_size": g.party_size,
        "neighborhood": g.neighborhood, "city": g.city, "status": g.status, "status_label": LABELS[g.status],
        "current_round": g.current_round, "vote_deadline": iso(g.vote_deadline), "is_demo": g.is_demo,
        "invite_code": g.invite_code, "invite_url": f"{settings.frontend_url}/entrar/{g.invite_code}",
        "created_at": iso(g.created_at), "decided_at": iso(g.decided_at),
        "participants": [{
            "id": str(p.id), "nickname": p.nickname, "is_organizer": p.is_organizer, "is_simulated": p.is_simulated,
            "has_preferences": p.preferences is not None, "has_voted": p.id in votes, "location": p.location,
        } for p in g.participants],
        "counts": {"joined": len(g.participants), "answered": len(answered), "party_size": g.party_size,
                   "voted": len(votes)},
        "missing": [p.nickname for p in missing],
        "can_generate_match": g.status == "match_disponivel",
        "can_force_match": g.status == "coletando_preferencias" and len(answered) >= MIN_FOR_FORCED_MATCH,
        "accepting_changes": g.status in OPEN_STATES,
        "match_summary": g.match_summary,
        "decision_note": g.decision_note,
        "winner": recommendation_out(winner) if winner else None,
        "reservation": reservation_out(db, res, me.id if me else None) if res else None,
        "is_organizer": caller.is_organizer,
        "me": None if me is None else {
            "participant_id": str(me.id), "nickname": me.nickname, "is_organizer": me.is_organizer,
            "preferences": preferences_out(me), "vote_recommendation_id": str(votes[me.id]) if me.id in votes else None,
        },
        "dietary_disclaimer": DIETARY_DISCLAIMER,
    }
