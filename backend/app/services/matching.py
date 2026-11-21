"""Motor de recomendação do iFood Match.

Funções puras, sem banco nem IA, para poderem ser testadas isoladamente.

Etapa A - Filtros obrigatórios: orçamento, restrições alimentares, capacidade e
          funcionamento/disponibilidade. Se nada sobrar, explica o conflito e sugere
          ajustes concretos, sem relaxar nenhuma restrição em silêncio.
Etapa B - Score de compatibilidade por participante:
          S = 0,40·G + 0,25·P + 0,20·L + 0,15·A   (cada componente de 0 a 100)
          Score do grupo = média dos individuais - penalização por desigualdade.
Etapa C - A explicação em linguagem natural fica em ai_service.py e recebe só o que
          este módulo devolve.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.reference import ambience_label, cuisine_label, diet_label

WEIGHTS = {"G": 0.40, "P": 0.25, "L": 0.20, "A": 0.15}
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
WEEKDAY_LABELS = {"seg": "segunda", "ter": "terça", "qua": "quarta", "qui": "quinta",
                  "sex": "sexta", "sab": "sábado", "dom": "domingo"}

# Penalização (D-006): se o pior score individual ficar abaixo de 50,
# o score do grupo perde 0,5 ponto para cada ponto abaixo de 50.
PENALTY_THRESHOLD = 50.0
PENALTY_FACTOR = 0.5

# Valores neutros quando o participante não declarou preferência no componente.
NEUTRAL_G = 60.0
NEUTRAL_A = 60.0
DEFAULT_MAX_DISTANCE_KM = 10.0

FILTERS = ("orcamento", "restricoes", "capacidade", "horario")
FILTER_LABELS = {
    "orcamento": "preço acima do teto",
    "restricoes": "não atender a uma restrição alimentar obrigatória",
    "capacidade": "não comportar o grupo",
    "horario": "estar fechado ou sem mesa na data e horário",
}


# --------------------------------------------------------------------------- tipos

@dataclass(frozen=True)
class Restaurant:
    id: str
    name: str
    cuisine: str
    neighborhood: str
    latitude: float
    longitude: float
    avg_price: float
    dietary_options: frozenset[str]
    capacity: int
    ambiences: frozenset[str]
    opening_hours: dict
    availability_rate: float
    rating: float
    accepts_reservation: bool = True
    description: str = ""
    simulated_benefit: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Restaurant":
        return cls(
            id=str(d["id"]), name=d["name"], cuisine=d["cuisine"], neighborhood=d["neighborhood"],
            latitude=float(d["latitude"]), longitude=float(d["longitude"]),
            avg_price=float(d["avg_price"]), dietary_options=frozenset(d["dietary_options"]),
            capacity=int(d["capacity"]), ambiences=frozenset(d["ambiences"]),
            opening_hours=d["opening_hours"], availability_rate=float(d["availability_rate"]),
            rating=float(d["rating"]), accepts_reservation=bool(d.get("accepts_reservation", True)),
            description=d.get("description", ""), simulated_benefit=d.get("simulated_benefit"),
        )


@dataclass(frozen=True)
class ParticipantPrefs:
    id: str
    nickname: str
    latitude: float
    longitude: float
    origin_neighborhood: str = ""
    cuisines: tuple[str, ...] = ()
    dietary_restrictions: tuple[str, ...] = ()
    ambiences: tuple[str, ...] = ()
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM
    max_budget: float | None = None


@dataclass(frozen=True)
class GroupContext:
    budget_per_person: float
    party_size: int
    event_date: date
    event_time: str  # "HH:MM"


@dataclass
class ParticipantScore:
    participant_id: str
    nickname: str
    G: float
    P: float
    L: float
    A: float
    score: float
    distance_km: float
    budget: float


@dataclass
class Recommendation:
    restaurant: Restaurant
    rank: int
    score: float
    mean_score: float
    penalty: float
    breakdown: list[ParticipantScore]
    highlights: list[str]
    attention_point: str
    avg_distance_km: float


@dataclass
class MatchResult:
    recommendations: list[Recommendation]
    total_restaurants: int
    eligible_count: int
    eliminated_by: dict[str, int]
    effective_budget: float
    budget_source: str  # "grupo" ou o apelido de quem tem o menor orçamento
    group_size: int
    required_diets: list[str]
    suggestions: list[dict] = field(default_factory=list)
    conflict_message: str | None = None


# ------------------------------------------------------------------ utilitários

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def weekday_key(d: date) -> str:
    return WEEKDAYS[d.weekday()]


def is_open(r: Restaurant, d: date, hhmm: str) -> bool:
    t = _minutes(hhmm)
    for slot in r.opening_hours.get(weekday_key(d), []):
        start, end = slot.split("-")
        if _minutes(start) <= t < _minutes(end):
            return True
    return False


def has_table(r: Restaurant, d: date, hhmm: str) -> bool:
    """Disponibilidade simulada e determinística: o mesmo restaurante, data e hora
    sempre dão o mesmo resultado, proporcional ao availability_rate do restaurante."""
    key = f"{r.id}|{d.isoformat()}|{hhmm[:2]}".encode()
    roll = int(hashlib.sha256(key).hexdigest()[:8], 16) / 0xFFFFFFFF
    return roll < r.availability_rate


def is_available(r: Restaurant, d: date, hhmm: str) -> bool:
    return is_open(r, d, hhmm) and has_table(r, d, hhmm)


def effective_budget(group: GroupContext, participants: list[ParticipantPrefs]) -> tuple[float, str]:
    """Teto de preço: o menor entre o orçamento do grupo e os individuais (D-001)."""
    budget, source = float(group.budget_per_person), "grupo"
    for p in participants:
        if p.max_budget is not None and p.max_budget < budget:
            budget, source = float(p.max_budget), p.nickname
    return budget, source


def participant_budget(group: GroupContext, p: ParticipantPrefs) -> float:
    if p.max_budget is None:
        return float(group.budget_per_person)
    return float(min(group.budget_per_person, p.max_budget))


# ------------------------------------------------------- Etapa A: filtros

def failed_filters(r: Restaurant, *, budget: float, diets: set[str], group_size: int,
                   d: date, hhmm: str) -> list[str]:
    failed = []
    if r.avg_price > budget:
        failed.append("orcamento")
    if not diets <= r.dietary_options:
        failed.append("restricoes")
    if r.capacity < group_size:
        failed.append("capacidade")
    if not is_available(r, d, hhmm):
        failed.append("horario")
    return failed


# --------------------------------------------------------- Etapa B: score

def score_gastronomy(r: Restaurant, p: ParticipantPrefs) -> float:
    if not p.cuisines:
        return NEUTRAL_G
    return 100.0 if r.cuisine in p.cuisines else 25.0


def score_price(r: Restaurant, budget: float) -> float:
    """Custo-benefício: preço relativo ao orçamento da pessoa (80%) + avaliação (20%).
    Até 50% do orçamento vale 100; no limite do orçamento, 40."""
    ratio = r.avg_price / budget if budget > 0 else 1.0
    price_part = clamp(100 - (ratio - 0.5) * 120, 40, 100)
    rating_part = clamp((r.rating - 3.5) / 1.5 * 100)
    return 0.8 * price_part + 0.2 * rating_part


def score_location(distance_km: float, max_distance_km: float) -> float:
    """100 na porta, 40 no limite de distância da pessoa e 0 no dobro do limite."""
    maxd = max(max_distance_km, 0.5)
    if distance_km <= maxd:
        return 100 * (1 - 0.6 * distance_km / maxd)
    return clamp(40 * (1 - (distance_km - maxd) / maxd))


def score_ambience(r: Restaurant, p: ParticipantPrefs) -> float:
    if not p.ambiences:
        return NEUTRAL_A
    wanted = set(p.ambiences)
    base = 20 + 80 * len(wanted & r.ambiences) / len(wanted)
    # Conflito direto: quem quer silêncio num lugar animado (ou o contrário).
    if ("tranquilo" in wanted and "animado" in r.ambiences) or ("animado" in wanted and "tranquilo" in r.ambiences):
        base -= 30
    return clamp(base)


def score_participant(r: Restaurant, p: ParticipantPrefs, group: GroupContext) -> ParticipantScore:
    budget = participant_budget(group, p)
    dist = haversine_km(p.latitude, p.longitude, r.latitude, r.longitude)
    G = score_gastronomy(r, p)
    P = score_price(r, budget)
    L = score_location(dist, p.max_distance_km)
    A = score_ambience(r, p)
    S = WEIGHTS["G"] * G + WEIGHTS["P"] * P + WEIGHTS["L"] * L + WEIGHTS["A"] * A
    return ParticipantScore(p.id, p.nickname, round(G, 1), round(P, 1), round(L, 1), round(A, 1),
                            round(S, 1), round(dist, 1), budget)


def group_score(individual: list[float]) -> tuple[float, float, float]:
    """Devolve (score do grupo, média, penalização)."""
    mean = sum(individual) / len(individual)
    worst = min(individual)
    penalty = PENALTY_FACTOR * (PENALTY_THRESHOLD - worst) if worst < PENALTY_THRESHOLD else 0.0
    return round(clamp(mean - penalty), 1), round(mean, 1), round(penalty, 1)


def _fmt_km(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def attention_point(r: Restaurant, breakdown: list[ParticipantScore],
                    participants: dict[str, ParticipantPrefs]) -> str:
    """O principal ponto de atenção: o pior componente ponderado do participante menos atendido."""
    worst = min(breakdown, key=lambda b: b.score)
    p = participants[worst.participant_id]
    losses = {
        "L": WEIGHTS["L"] * (100 - worst.L),
        "G": WEIGHTS["G"] * (100 - worst.G),
        "P": WEIGHTS["P"] * (100 - worst.P),
        "A": WEIGHTS["A"] * (100 - worst.A),
    }
    comp = max(losses, key=losses.get)
    if comp == "L":
        if worst.distance_km > p.max_distance_km:
            return (f"Fica a {_fmt_km(worst.distance_km)} km de {p.nickname}, acima do limite de "
                    f"{_fmt_km(p.max_distance_km)} km que a pessoa informou.")
        return f"É o mais longe para {p.nickname}: {_fmt_km(worst.distance_km)} km de onde a pessoa sai."
    if comp == "G" and p.cuisines:
        return f"Culinária {cuisine_label(r.cuisine)} não está entre as favoritas de {p.nickname}."
    if comp == "P":
        pct = round(100 * r.avg_price / worst.budget)
        return f"O preço médio (R$ {r.avg_price:.0f}) usa {pct}% do orçamento de {p.nickname}."
    if comp == "A" and p.ambiences:
        return f"O ambiente ({', '.join(ambience_label(a) for a in sorted(r.ambiences))}) não é o que {p.nickname} prefere."
    return f"{p.nickname} é quem tem a menor compatibilidade com este lugar ({worst.score:.0f}/100)."


def highlights(r: Restaurant, breakdown: list[ParticipantScore], participants: dict[str, ParticipantPrefs],
               budget: float, diets: set[str]) -> list[str]:
    """Fatos positivos, todos tirados dos atributos cadastrados."""
    out = [f"Preço médio de R$ {r.avg_price:.0f} por pessoa, dentro do teto de R$ {budget:.0f}."]
    if diets:
        out.append("Atende às restrições informadas pelo grupo: "
                   + ", ".join(diet_label(d) for d in sorted(diets)) + ".")
    fans = [participants[b.participant_id].nickname for b in breakdown if b.G == 100]
    if fans:
        out.append(f"Culinária {cuisine_label(r.cuisine)} está entre as favoritas de {_join(fans)}.")
    amb_fans = [participants[b.participant_id].nickname for b in breakdown
                if participants[b.participant_id].ambiences and b.A >= 60]
    if amb_fans:
        out.append(f"Ambiente ({', '.join(ambience_label(a) for a in sorted(r.ambiences))}) combina com {_join(amb_fans)}.")
    near = [participants[b.participant_id].nickname for b in breakdown
            if b.distance_km <= participants[b.participant_id].max_distance_km]
    if len(near) == len(breakdown):
        out.append("Fica dentro da distância máxima de todos.")
    return out


def _join(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " e " + names[-1]


def rank(restaurants: list[Restaurant], participants: list[ParticipantPrefs], group: GroupContext,
         *, budget: float, diets: set[str], top_n: int = 3) -> list[Recommendation]:
    by_id = {p.id: p for p in participants}
    scored = []
    for r in restaurants:
        breakdown = [score_participant(r, p, group) for p in participants]
        score, mean, penalty = group_score([b.score for b in breakdown])
        scored.append((r, score, mean, penalty, breakdown))
    # Desempate determinístico: maior score, menor preço, maior avaliação, nome.
    scored.sort(key=lambda t: (-t[1], t[0].avg_price, -t[0].rating, t[0].name))
    out = []
    for i, (r, score, mean, penalty, breakdown) in enumerate(scored[:top_n], start=1):
        out.append(Recommendation(
            restaurant=r, rank=i, score=score, mean_score=mean, penalty=penalty, breakdown=breakdown,
            highlights=highlights(r, breakdown, by_id, budget, diets),
            attention_point=attention_point(r, breakdown, by_id),
            avg_distance_km=round(sum(b.distance_km for b in breakdown) / len(breakdown), 1),
        ))
    return out


# -------------------------------------------------- sugestões de ajuste

def _appear(n: int) -> str:
    return "surge 1 opção" if n == 1 else f"surgem {n} opções"


def _round_up(x: float, step: int = 5) -> int:
    return int(math.ceil(x / step) * step)


def suggestions(restaurants: list[Restaurant], participants: list[ParticipantPrefs], group: GroupContext,
                *, budget: float, budget_source: str, diets: set[str], group_size: int) -> list[dict]:
    """Ajustes concretos que fariam surgir opções. Cada sugestão relaxa um único critério
    e diz quantos restaurantes passariam a ser elegíveis."""
    d, t = group.event_date, group.event_time
    fails = {r.id: failed_filters(r, budget=budget, diets=diets, group_size=group_size, d=d, hhmm=t)
             for r in restaurants}
    out: list[dict] = []

    # 1. Orçamento
    only_budget = sorted((r for r in restaurants if fails[r.id] == ["orcamento"]), key=lambda r: r.avg_price)
    if only_budget:
        target = only_budget[min(2, len(only_budget) - 1)]
        new_budget = _round_up(target.avg_price)
        n = sum(1 for r in only_budget if r.avg_price <= new_budget)
        who = "o orçamento por pessoa" if budget_source == "grupo" else f"o limite de {budget_source}"
        out.append({"type": "orcamento", "value": new_budget, "count": n,
                    "message": f"Subindo {who} de R$ {budget:.0f} para R$ {new_budget}, {_appear(n)}."})

    # 2. Restrições: não sugerimos remover, só mostramos o peso de cada uma para o grupo confirmar.
    for diet in sorted(diets):
        rest = diets - {diet}
        n = sum(1 for r in restaurants
                if not failed_filters(r, budget=budget, diets=rest, group_size=group_size, d=d, hhmm=t))
        if n:
            owners = [p.nickname for p in participants if diet in p.dietary_restrictions]
            out.append({"type": "restricoes", "value": diet, "count": n,
                        "message": (f"A restrição '{diet_label(diet)}' ({_join(owners)}) é a que mais limita: "
                                    f"sem ela haveria {n} {'opção' if n == 1 else 'opções'}. Só altere se ela não for obrigatória.")})

    # 3. Capacidade
    only_cap = [r for r in restaurants if fails[r.id] == ["capacidade"]]
    if only_cap:
        best = max(r.capacity for r in only_cap)
        n = sum(1 for r in only_cap if r.capacity >= best)
        out.append({"type": "capacidade", "value": best, "count": n,
                    "message": f"Com grupos de até {best} pessoas, {_appear(n)}."})

    # 4. Horário no mesmo dia (de 30 em 30 min, do mais próximo para o mais distante)
    def eligible_at(day: date, hhmm: str) -> int:
        return sum(1 for r in restaurants
                   if not failed_filters(r, budget=budget, diets=diets, group_size=group_size, d=day, hhmm=hhmm))

    base = _minutes(t)
    times = sorted((m for m in range(11 * 60 + 30, 23 * 60 + 1, 30) if m != base), key=lambda m: (abs(m - base), m))
    for m in times:
        hhmm = f"{m // 60:02d}:{m % 60:02d}"
        n = eligible_at(d, hhmm)
        if n:
            out.append({"type": "horario", "value": hhmm, "count": n,
                        "message": f"No mesmo dia, às {hhmm}, {_appear(n)}."})
            break

    # 5. Outro dia, mesmo horário (próximos 7 dias)
    for k in range(1, 8):
        day = d + timedelta(days=k)
        n = eligible_at(day, t)
        if n:
            label = WEEKDAY_LABELS[weekday_key(day)]
            out.append({"type": "data", "value": day.isoformat(), "count": n,
                        "message": f"Em {day.strftime('%d/%m')} ({label}), às {t}, {_appear(n)}."})
            break

    out.sort(key=lambda s: -s["count"])
    return out


# ------------------------------------------------------------ orquestração

def run_match(restaurants: list[Restaurant], participants: list[ParticipantPrefs], group: GroupContext,
              *, top_n: int = 3) -> MatchResult:
    if not participants:
        raise ValueError("É preciso pelo menos um participante com preferências.")
    budget, source = effective_budget(group, participants)
    diets = {d for p in participants for d in p.dietary_restrictions}
    group_size = max(group.party_size, len(participants))

    eliminated = {f: 0 for f in FILTERS}
    eligible = []
    for r in restaurants:
        failed = failed_filters(r, budget=budget, diets=diets, group_size=group_size,
                                d=group.event_date, hhmm=group.event_time)
        for f in failed:
            eliminated[f] += 1
        if not failed:
            eligible.append(r)

    recs = rank(eligible, participants, group, budget=budget, diets=diets, top_n=top_n)
    result = MatchResult(
        recommendations=recs, total_restaurants=len(restaurants), eligible_count=len(eligible),
        eliminated_by=eliminated, effective_budget=budget, budget_source=source,
        group_size=group_size, required_diets=sorted(diets),
    )
    if len(eligible) < top_n:
        result.suggestions = suggestions(restaurants, participants, group, budget=budget,
                                         budget_source=source, diets=diets, group_size=group_size)
    if not eligible:
        parts = [f"{n} por {FILTER_LABELS[f]}" for f, n in eliminated.items() if n]
        result.conflict_message = (
            f"Nenhum dos {len(restaurants)} restaurantes atende a todos os critérios obrigatórios do grupo. "
            f"Eliminados: {'; '.join(parts)}. Um restaurante pode ter sido eliminado por mais de um motivo."
        )
    return result


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()
