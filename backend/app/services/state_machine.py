"""Máquina de estados do encontro (docx, Etapa 2, seção 5).

coletando_preferencias -> match_disponivel -> votacao_aberta -> escolha_concluida -> reserva_simulada -> avaliado

Transições extras, todas explícitas:
- match_disponivel -> coletando_preferencias: entrou alguém que ainda não respondeu.
- coletando_preferencias -> votacao_aberta: só pelo botão do organizador "gerar com quem já respondeu" (D-002).
- votacao_aberta -> match_disponivel | coletando_preferencias: alguém mudou preferências ou o organizador
  mudou o encontro; o ranking e os votos da rodada são invalidados e abre-se uma nova rodada.
"""
from __future__ import annotations

from app.errors import AppError

TRANSITIONS: dict[str, set[str]] = {
    "coletando_preferencias": {"match_disponivel", "votacao_aberta"},
    "match_disponivel": {"coletando_preferencias", "votacao_aberta"},
    "votacao_aberta": {"coletando_preferencias", "match_disponivel", "escolha_concluida"},
    "escolha_concluida": {"reserva_simulada"},
    "reserva_simulada": {"avaliado"},
    "avaliado": set(),
}

LABELS = {
    "coletando_preferencias": "Coletando preferências",
    "match_disponivel": "Match disponível",
    "votacao_aberta": "Votação aberta",
    "escolha_concluida": "Escolha concluída",
    "reserva_simulada": "Reserva simulada",
    "avaliado": "Avaliado",
}

# Estados em que a decisão ainda pode mudar (entrar no grupo, mudar preferências, ajustar o encontro).
OPEN_STATES = {"coletando_preferencias", "match_disponivel", "votacao_aberta"}


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, set())


def transition(group, new: str) -> None:
    """Muda o status do grupo ou levanta 409 se a transição não for permitida."""
    if group.status == new:
        return
    if not can_transition(group.status, new):
        raise AppError(409, "transicao_invalida",
                       f"O encontro está em '{LABELS.get(group.status, group.status)}' e não pode ir para "
                       f"'{LABELS.get(new, new)}'.", {"from": group.status, "to": new})
    group.status = new


def require_status(group, *allowed: str, action: str) -> None:
    if group.status not in allowed:
        raise AppError(409, "etapa_invalida",
                       f"Não é possível {action} agora: o encontro está em '{LABELS.get(group.status, group.status)}'.",
                       {"status": group.status, "allowed": list(allowed)})
