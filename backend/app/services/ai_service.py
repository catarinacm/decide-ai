"""IA generativa do iFood Match (API da Anthropic), chamada só pelo backend.

Função A - interpretar texto livre de preferências em JSON estruturado (a pessoa confere antes de salvar).
Função B - explicar as recomendações que o algoritmo já escolheu.

Regras: a IA não decide orçamento, restrição alimentar nem disponibilidade. Toda resposta passa por validação;
se a API falhar, estourar o timeout, recusar ou devolver algo que não passe nos guardrails, o resultado vem
das regras (fallback), e o banco registra qual dos dois foi usado.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass

import anthropic

from app.config import settings
from app.reference import AMBIENCES, CUISINES, DIETS, NEIGHBORHOODS, cuisine_label, diet_label
from app.schemas import ParsedPreferences
from app.services.matching import Recommendation

log = logging.getLogger("ifood_match.ai")

PROMPT_VERSION = "v1"

# ----------------------------------------------------------------- prompts

PARSE_SYSTEM = f"""Você converte o texto livre de uma pessoa sobre onde quer comer em preferências estruturadas \
para o iFood Match, um protótipo que ajuda grupos de amigos a escolher restaurantes.

Regras:
- Use somente estes valores, exatamente como escritos.
  Culinárias: {", ".join(CUISINES)}.
  Restrições alimentares: {", ".join(DIETS)}.
  Ambientes: {", ".join(AMBIENCES)}.
  Bairros de saída: {", ".join(NEIGHBORHOODS)}.
- Só marque uma restrição alimentar se a pessoa disser que ela mesma tem essa restrição ou que alguém do grupo tem. \
"Gosto de salada" não é restrição.
- Se a pessoa disser que não quer uma culinária, não a inclua.
- max_budget e max_distance_km só podem ser preenchidos se a pessoa escrever um número (ex.: "até 80 reais", \
"no máximo 5 km"). Expressões como "barato" ou "não muito caro" vão em budget_hint, nunca viram número.
- origin_neighborhood só se a pessoa citar um dos bairros da lista como ponto de saída.
- additional_preferences: resuma em até 120 caracteres o que for relevante e não couber nos campos.
- Não invente nada que não esteja no texto. Na dúvida, deixe vazio."""

EXPLAIN_SYSTEM = """Você escreve, em português do Brasil, a explicação "Por que o iFood Match recomendou este \
restaurante?" para um grupo de amigos. O algoritmo já escolheu e ordenou os restaurantes; você só explica.

Regras obrigatórias:
- Use apenas os dados do JSON enviado. Não invente pratos, preços, distâncias, horários, avaliações ou qualquer fato.
- Cite somente restaurantes que estão no JSON. Não compare com nenhum outro lugar.
- Não afirme que um lugar é seguro para alergias, intolerâncias ou doença celíaca, nem que não há risco de \
contaminação. Você pode dizer que o restaurante tem opções cadastradas (ex.: "tem opções sem glúten").
- Não mude o ranking nem sugira outro restaurante.
- Para cada restaurante, escreva de 2 a 3 frases (no máximo 420 caracteres): por que combina com o grupo \
(orçamento, restrições atendidas, culinária ou ambiente que agradam a quem, distância) e, por último, o principal \
ponto de atenção, usando o campo attention_point.
- Use os apelidos dos participantes quando ajudar. Tom simpático e direto, sem emojis e sem exageros."""

PARSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cuisines", "dietary_restrictions", "ambiences", "origin_neighborhood", "max_distance_km",
                 "max_budget", "budget_hint", "additional_preferences"],
    "properties": {
        "cuisines": {"type": "array", "items": {"type": "string", "enum": list(CUISINES)}},
        "dietary_restrictions": {"type": "array", "items": {"type": "string", "enum": list(DIETS)}},
        "ambiences": {"type": "array", "items": {"type": "string", "enum": list(AMBIENCES)}},
        "origin_neighborhood": {"anyOf": [{"type": "string", "enum": list(NEIGHBORHOODS)}, {"type": "null"}]},
        "max_distance_km": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "max_budget": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "budget_hint": {"type": "string"},
        "additional_preferences": {"type": "string"},
    },
}

EXPLAIN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["explanations"],
    "properties": {
        "explanations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["restaurant_id", "explanation"],
                "properties": {"restaurant_id": {"type": "string"}, "explanation": {"type": "string"}},
            },
        }
    },
}

# Frases que afirmariam segurança alimentar ou garantia; se aparecerem, a explicação é descartada.
FORBIDDEN = re.compile(
    r"(segur[oa]s? para|sem (nenhum )?risco|garant|100\s*%|totalmente livre|livre de (gl[uú]ten|lactose|contamina)"
    r"|n[aã]o cont[eé]m|à prova de|apto para cel[ií]acos|pode comer sem preocupa)", re.IGNORECASE)


class AIUnavailable(Exception):
    pass


@dataclass
class AIResult:
    data: object
    source: str  # 'ia' ou 'fallback'
    error: str | None = None
    latency_ms: int = 0


# ------------------------------------------------------------- chamada à API

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Sem retries automáticos: o timeout é curto e o fallback é melhor que fazer a pessoa esperar.
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=settings.ai_timeout_seconds,
                                      max_retries=0)
    return _client


def call_model(system: str, user: str, schema: dict, max_tokens: int) -> dict:
    """Uma chamada com saída em JSON garantida pelo schema. Levanta AIUnavailable em qualquer falha."""
    if not settings.ai_enabled:
        raise AIUnavailable("ia_desativada")
    try:
        resp = _get_client().messages.create(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.APITimeoutError as e:
        raise AIUnavailable("timeout") from e
    except anthropic.RateLimitError as e:
        raise AIUnavailable("rate_limit") from e
    except anthropic.APIStatusError as e:
        raise AIUnavailable(f"http_{e.status_code}") from e
    except anthropic.APIConnectionError as e:
        raise AIUnavailable("conexao") from e
    if resp.stop_reason == "refusal":
        raise AIUnavailable("recusa")
    if resp.stop_reason == "max_tokens":
        raise AIUnavailable("resposta_truncada")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        raise AIUnavailable("sem_texto")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise AIUnavailable("json_invalido") from e


# ------------------------------------------- Função A: interpretar preferências

def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


CUISINE_KEYWORDS = {
    "japonesa": ["japon", "sushi", "lamen", "ramen", "temaki", "izakaya", "omakase"],
    "italiana": ["italian", "massa", "risoto", "lasanha", "cantina", "trattoria"],
    "pizzaria": ["pizza"],
    "hamburgueria": ["hamburg", "burger", "lanche", "smash"],
    "brasileira": ["brasileir", "feijoada", "mineir", "comida caseira", "prato feito", "boteco"],
    "nordestina": ["nordest", "baiao", "tapioca", "carne de sol", "cuscuz"],
    "chinesa": ["chines", "yakissoba", "dim sum"],
    "coreana": ["corean", "kimchi", "bibimbap"],
    "tailandesa": ["tailand", "thai", "pad thai"],
    "indiana": ["indian", "curry"],
    "arabe": ["arabe", "esfiha", "falafel", "kafta", "libanes"],
    "mexicana": ["mexican", "taco", "burrito", "nachos"],
    "peruana": ["peruan", "ceviche"],
    "francesa": ["frances"],
    "portuguesa": ["portugues", "bacalhau"],
    "carnes": ["churrasc", "carne", "parrilla", "steak"],
    "frutos_do_mar": ["frutos do mar", "peixe", "camarao", "ostra"],
    "vegetariana": ["restaurante vegetarian", "restaurante vegan", "comida vegana", "comida vegetariana"],
    "cafe_bistro": ["cafe", "cafeteria", "bistro", "brunch"],
}
DIET_KEYWORDS = {
    "vegana": ["vegan"],
    "vegetariana": ["vegetarian", "nao como carne", "nao come carne"],
    "sem_gluten": ["gluten", "celiac"],
    "sem_lactose": ["lactose", "sem leite"],
}
AMBIENCE_KEYWORDS = {
    "tranquilo": ["tranquil", "calm", "silencios", "sossegad", "sem musica alta", "conversar", "quieto"],
    "animado": ["animad", "agitad", "balada", "festa", "musica ao vivo", "barulhent"],
    "casual": ["casual", "descontraid", "simples", "informal"],
    "romantico": ["romantic", "a dois", "date"],
    "ao_ar_livre": ["ao ar livre", "varanda", "terraco", "area externa", "quintal", "calcada"],
}
NEGATIONS = re.compile(r"(nao|odeio|detesto|sem|nada de|menos)\s+(\w+\s+){0,2}$")


def _found(text: str, keywords: list[str]) -> bool:
    for kw in keywords:
        for m in re.finditer(re.escape(kw), text):
            if not NEGATIONS.search(text[max(0, m.start() - 25):m.start()]):
                return True
    return False


def parse_preferences_rules(text: str) -> ParsedPreferences:
    """Fallback por palavras-chave, determinístico. Mesmas regras da IA: números só se escritos."""
    t = _norm(text)
    diets = [d for d, kws in DIET_KEYWORDS.items() if any(kw in t for kw in kws)]
    if "sem gluten" not in t and "gluten" in t and re.search(r"(com|adoro|gosto de) gluten", t):
        diets = [d for d in diets if d != "sem_gluten"]
    cuisines = [c for c, kws in CUISINE_KEYWORDS.items() if _found(t, kws)]
    ambiences = [a for a, kws in AMBIENCE_KEYWORDS.items() if any(kw in t for kw in kws)]
    if "tranquilo" in ambiences and "animado" in ambiences:
        ambiences.remove("animado")
    km = re.search(r"(\d{1,2})\s*km", t)
    money = re.search(r"(?:r\$\s*(\d{2,4})|(\d{2,4})\s*(?:reais|conto|pila))", t)
    hood = next((h for h in NEIGHBORHOODS if _norm(h) in t), None)
    hint = ""
    if re.search(r"barat|nao muito car|economic|em conta|orcamento curto|apertad", t):
        hint = "Prefere opções mais em conta."
    return ParsedPreferences(
        cuisines=cuisines, dietary_restrictions=diets, ambiences=ambiences, origin_neighborhood=hood,
        max_distance_km=float(km.group(1)) if km else None,
        max_budget=float(money.group(1) or money.group(2)) if money else None,
        budget_hint=hint, additional_preferences=text.strip()[:120],
    )


def _numbers_in(text: str) -> set[float]:
    return {float(n) for n in re.findall(r"\d+(?:[.,]\d+)?", text.replace(",", "."))}


def parse_preferences(text: str) -> AIResult:
    t0 = time.perf_counter()
    try:
        raw = call_model(PARSE_SYSTEM, f"Texto da pessoa:\n<<<\n{text}\n>>>", PARSE_SCHEMA, max_tokens=1500)
        parsed = ParsedPreferences.model_validate(raw)
        # Guardrail: a IA não decide orçamento nem distância. Número só vale se estiver escrito no texto.
        written = _numbers_in(text)
        if parsed.max_budget is not None and parsed.max_budget not in written:
            parsed.max_budget = None
        if parsed.max_distance_km is not None and parsed.max_distance_km not in written:
            parsed.max_distance_km = None
        return AIResult(parsed, "ia", latency_ms=int((time.perf_counter() - t0) * 1000))
    except (AIUnavailable, ValueError) as e:
        reason = str(e) if isinstance(e, AIUnavailable) else "validacao"
        log.info("parse_preferences em fallback: %s", reason)
        return AIResult(parse_preferences_rules(text), "fallback", error=reason,
                        latency_ms=int((time.perf_counter() - t0) * 1000))


# -------------------------------------------- Função B: explicar recomendações

def template_explanation(rec: Recommendation) -> str:
    """Explicação por regras, a partir dos mesmos dados enviados à IA."""
    r = rec.restaurant
    pos = {1: "a opção mais compatível", 2: "a segunda opção mais compatível", 3: "a terceira opção"}[rec.rank]
    parts = [f"{r.name} é {pos} com o grupo, com compatibilidade de {rec.score:.0f} de 100."]
    parts += rec.highlights[:3]
    parts.append(f"Ponto de atenção: {rec.attention_point}")
    return " ".join(parts)


def _explain_payload(recs: list[Recommendation], context: dict) -> dict:
    return {
        "grupo": context,
        "restaurantes": [{
            "restaurant_id": rec.restaurant.id,
            "posicao": rec.rank,
            "nome": rec.restaurant.name,
            "culinaria": cuisine_label(rec.restaurant.cuisine),
            "bairro": rec.restaurant.neighborhood,
            "preco_medio_por_pessoa": round(float(rec.restaurant.avg_price)),
            "opcoes_alimentares_cadastradas": [diet_label(d) for d in sorted(rec.restaurant.dietary_options)],
            "ambientes": sorted(rec.restaurant.ambiences),
            "avaliacao_ficticia": rec.restaurant.rating,
            "score_do_grupo": rec.score,
            "pontos_fortes": rec.highlights,
            "attention_point": rec.attention_point,
            "por_participante": [{"apelido": b.nickname, "score": b.score, "distancia_km": b.distance_km}
                                 for b in rec.breakdown],
        } for rec in recs],
    }


def validate_explanations(raw: dict, recs: list[Recommendation], catalog_names: list[str],
                          allowed_numbers: set[float]) -> dict[str, str]:
    """Guardrails da Função B. Devolve só as explicações aprovadas, por restaurant_id."""
    sent = {rec.restaurant.id: rec for rec in recs}
    sent_names = {_norm(rec.restaurant.name) for rec in recs}
    other_names = [n for n in (_norm(x) for x in catalog_names) if n not in sent_names]
    approved: dict[str, str] = {}
    for item in raw.get("explanations", []):
        rid, text = str(item.get("restaurant_id", "")), " ".join(str(item.get("explanation", "")).split())
        if rid not in sent or rid in approved:
            continue  # restaurante que não foi enviado: descartado
        if not (40 <= len(text) <= 700) or FORBIDDEN.search(text):
            continue
        nt = _norm(text)
        if any(n in nt for n in other_names):
            continue  # citou restaurante que não está entre os enviados
        if _norm(sent[rid].restaurant.name) not in nt:
            continue  # a explicação precisa ser sobre o próprio restaurante
        prices = {float(p.replace(".", "").replace(",", ".")) for p in re.findall(r"R\$\s*([\d.,]+)", text)}
        if not prices <= allowed_numbers:
            continue  # preço que não está nos dados enviados
        approved[rid] = text
    return approved


_cache: OrderedDict[str, dict[str, str]] = OrderedDict()
_CACHE_MAX = 256


def explain_recommendations(recs: list[Recommendation], context: dict,
                            catalog_names: list[str]) -> tuple[dict[str, tuple[str, str]], AIResult]:
    """Devolve {restaurant_id: (explicação, 'ia' | 'fallback')} e o resultado da chamada para registro."""
    if not recs:
        return {}, AIResult({}, "fallback", error="sem_recomendacoes")
    payload = _explain_payload(recs, context)
    key = hashlib.sha256((PROMPT_VERSION + json.dumps(payload, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
    t0 = time.perf_counter()
    error = None
    if key in _cache:
        approved, cached = _cache[key], True
    else:
        cached = False
        try:
            raw = call_model(EXPLAIN_SYSTEM, json.dumps(payload, ensure_ascii=False), EXPLAIN_SCHEMA, max_tokens=3000)
            allowed = {float(round(float(r.restaurant.avg_price))) for r in recs}
            allowed |= {float(b.budget) for r in recs for b in r.breakdown}
            allowed.add(float(context.get("teto_de_preco", 0)))
            approved = validate_explanations(raw, recs, catalog_names, allowed)
            if len(approved) < len(recs):
                error = f"guardrail_rejeitou_{len(recs) - len(approved)}"
            if approved:
                _cache[key] = approved
                if len(_cache) > _CACHE_MAX:
                    _cache.popitem(last=False)
        except AIUnavailable as e:
            approved, error = {}, str(e)
    out = {}
    for rec in recs:
        rid = rec.restaurant.id
        out[rid] = (approved[rid], "ia") if rid in approved else (template_explanation(rec), "fallback")
    source = "ia" if approved else "fallback"
    return out, AIResult({"cached": cached}, source, error=error,
                         latency_ms=int((time.perf_counter() - t0) * 1000))
