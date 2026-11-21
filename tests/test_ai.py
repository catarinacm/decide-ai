"""IA com o modelo mockado: chamada correta, guardrails, fallback por regras, cache e registro."""
import types

import anthropic
import httpx2
import pytest

from app.config import settings
from app.models.tables import EventRow, RecommendationRow
from app.services import ai_service

PHRASE = "Quero um lugar tranquilo, não muito caro, sou vegetariana"


# --------------------------------------------------------- Função A: regras

def test_fallback_interpreta_a_frase_do_docx():
    p = ai_service.parse_preferences_rules(PHRASE)
    assert p.ambiences == ["tranquilo"]
    assert p.dietary_restrictions == ["vegetariana"]
    assert p.max_budget is None  # "não muito caro" não vira número
    assert p.budget_hint


@pytest.mark.parametrize("text,field,expected", [
    ("adoro sushi e pizza", "cuisines", ["japonesa", "pizzaria"]),
    ("não gosto de sushi, prefiro hambúrguer", "cuisines", ["hamburgueria"]),
    ("sou celíaco e vegano", "dietary_restrictions", ["vegana", "sem_gluten"]),
    ("até 80 reais, no máximo 5 km", "max_budget", 80.0),
    ("até 80 reais, no máximo 5 km", "max_distance_km", 5.0),
    ("saio da Vila Madalena", "origin_neighborhood", "Vila Madalena"),
    ("lugar animado com música ao vivo", "ambiences", ["animado"]),
])
def test_fallback_casos(text, field, expected):
    assert getattr(ai_service.parse_preferences_rules(text), field) == expected


def test_parse_sem_chave_usa_fallback():
    r = ai_service.parse_preferences(PHRASE)
    assert r.source == "fallback" and r.error == "ia_desativada"


# --------------------------------------------------------- Função A: IA mockada

def test_parse_com_ia_e_guardrail_de_numeros(monkeypatch):
    def fake(system, user, schema, max_tokens):
        assert "Não invente" in system and schema["additionalProperties"] is False
        return {"cuisines": ["italiana", "inexistente"], "dietary_restrictions": ["vegetariana"],
                "ambiences": ["tranquilo"], "origin_neighborhood": "Atlântida", "max_distance_km": 7,
                "max_budget": 70, "budget_hint": "Prefere preço moderado.", "additional_preferences": ""}
    monkeypatch.setattr(ai_service, "call_model", fake)
    r = ai_service.parse_preferences(PHRASE)
    assert r.source == "ia"
    p = r.data
    assert p.cuisines == ["italiana"]           # valor fora da lista descartado
    assert p.origin_neighborhood is None        # bairro inventado descartado
    assert p.max_budget is None and p.max_distance_km is None  # números não escritos pela pessoa: descartados


def test_parse_ia_mantem_numero_escrito(monkeypatch):
    monkeypatch.setattr(ai_service, "call_model", lambda *a, **k: {
        "cuisines": [], "dietary_restrictions": [], "ambiences": [], "origin_neighborhood": None,
        "max_distance_km": None, "max_budget": 80, "budget_hint": "", "additional_preferences": ""})
    assert ai_service.parse_preferences("posso gastar até 80 reais").data.max_budget == 80


def test_parse_ia_falha_cai_no_fallback(monkeypatch):
    def boom(*a, **k):
        raise ai_service.AIUnavailable("timeout")
    monkeypatch.setattr(ai_service, "call_model", boom)
    r = ai_service.parse_preferences(PHRASE)
    assert r.source == "fallback" and r.error == "timeout" and r.data.dietary_restrictions == ["vegetariana"]


def test_endpoint_parse_registra_evento(flow, client, db, monkeypatch):
    flow.create()
    r = client.post("/ai/parse-preferences", json={"text": PHRASE}, headers=flow.H("Ana")).json()
    assert r["source"] == "fallback" and r["preferences"]["dietary_restrictions"] == ["vegetariana"]
    ev = db.query(EventRow).filter(EventRow.name == "ai_call").one()
    assert ev.properties["function"] == "interpretacao" and ev.properties["source"] == "fallback"
    assert client.post("/ai/parse-preferences", json={"text": PHRASE}).status_code == 401


# ---------------------------------------------------- chamada real à API (cliente falso)

class FakeClient:
    def __init__(self, behavior):
        self.behavior, self.calls = behavior, []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.behavior(**kwargs)


def _req():
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")


def _install(monkeypatch, behavior):
    fake = FakeClient(behavior)
    monkeypatch.setattr(ai_service, "_get_client", lambda: fake)
    return fake


def test_call_model_parametros(ai_on, monkeypatch):
    msg = types.SimpleNamespace(stop_reason="end_turn", content=[types.SimpleNamespace(type="text", text='{"a": 1}')])
    fake = _install(monkeypatch, lambda **k: msg)
    assert ai_service.call_model("sys", "user", {"type": "object"}, 100) == {"a": 1}
    kw = fake.calls[0]
    assert kw["model"] == "claude-haiku-5-5"
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    assert kw["system"] == "sys"


@pytest.mark.parametrize("exc,reason", [
    (lambda: anthropic.APITimeoutError(request=_req()), "timeout"),
    (lambda: anthropic.APIConnectionError(request=_req()), "conexao"),
])
def test_call_model_erros_de_rede(ai_on, monkeypatch, exc, reason):
    def raise_(**k):
        raise exc()
    _install(monkeypatch, raise_)
    with pytest.raises(ai_service.AIUnavailable, match=reason):
        ai_service.call_model("s", "u", {}, 10)


@pytest.mark.parametrize("stop,reason", [("refusal", "recusa"), ("max_tokens", "resposta_truncada")])
def test_call_model_recusa_e_truncamento(ai_on, monkeypatch, stop, reason):
    msg = types.SimpleNamespace(stop_reason=stop, content=[types.SimpleNamespace(type="text", text="{")])
    _install(monkeypatch, lambda **k: msg)
    with pytest.raises(ai_service.AIUnavailable, match=reason):
        ai_service.call_model("s", "u", {}, 10)


# ---------------------------------------------------- Função B: explicações

def _ready_group(flow):
    flow.ready()
    return flow


def _explanations_for(payload_json):
    import json
    data = json.loads(payload_json)
    return data["restaurantes"]


def _good_text(r):
    return (f"{r['nome']} combina com o grupo: preço médio de R$ {r['preco_medio_por_pessoa']} por pessoa e "
            f"culinária {r['culinaria']}. Ponto de atenção: {r['attention_point']}")


def test_explicacao_da_ia_e_gravada_com_fonte(flow, db, monkeypatch):
    calls = []

    def fake(system, user, schema, max_tokens):
        calls.append(user)
        assert "Não afirme que um lugar é seguro" in system
        return {"explanations": [{"restaurant_id": r["restaurant_id"], "explanation": _good_text(r)}
                                 for r in _explanations_for(user)]}
    monkeypatch.setattr(ai_service, "call_model", fake)
    recs = _ready_group(flow).match()["recommendations"]
    assert {r["explanation_source"] for r in recs} == {"ia"}
    assert all(r["restaurant"]["name"] in r["explanation"] for r in recs)
    rows = db.query(RecommendationRow).all()
    assert {r.reason_source for r in rows} == {"ia"}
    ev = db.query(EventRow).filter(EventRow.name == "ai_call").one()
    assert ev.properties["source"] == "ia"
    assert len(calls) == 1  # uma chamada para as 3 explicações


@pytest.mark.parametrize("corrupt", [
    "cita_outro_restaurante", "seguranca_alimentar", "preco_inventado", "id_desconhecido", "curta_demais",
])
def test_guardrails_descartam_explicacao_ruim(flow, monkeypatch, corrupt):
    def fake(system, user, schema, max_tokens):
        rs = _explanations_for(user)
        items = [{"restaurant_id": r["restaurant_id"], "explanation": _good_text(r)} for r in rs]
        bad = items[0]
        if corrupt == "cita_outro_restaurante":
            bad["explanation"] += " Melhor que o Omakase Kumo Azul." if "Omakase" not in rs[0]["nome"] else " Melhor que a Pizzaria Lua de Tijolo."
        elif corrupt == "seguranca_alimentar":
            bad["explanation"] += " É totalmente seguro para celíacos."
        elif corrupt == "preco_inventado":
            bad["explanation"] = bad["explanation"].replace(f"R$ {rs[0]['preco_medio_por_pessoa']}", "R$ 19")
        elif corrupt == "id_desconhecido":
            bad["restaurant_id"] = "00000000-0000-0000-0000-000000000000"
        elif corrupt == "curta_demais":
            bad["explanation"] = "Ok."
        return {"explanations": items}
    monkeypatch.setattr(ai_service, "call_model", fake)
    recs = _ready_group(flow).match()["recommendations"]
    assert recs[0]["explanation_source"] == "fallback"
    assert "Ponto de atenção" in recs[0]["explanation"]
    assert [r["explanation_source"] for r in recs[1:]] == ["ia", "ia"]


def test_falha_da_ia_gera_explicacao_por_regras(flow, monkeypatch):
    def boom(*a, **k):
        raise ai_service.AIUnavailable("http_529")
    monkeypatch.setattr(ai_service, "call_model", boom)
    recs = _ready_group(flow).match()["recommendations"]
    assert {r["explanation_source"] for r in recs} == {"fallback"}
    for r in recs:
        assert r["restaurant"]["name"] in r["explanation"] and r["attention_point"] in r["explanation"]


def test_cache_da_explicacao(flow, client, monkeypatch):
    n = {"calls": 0}

    def fake(system, user, schema, max_tokens):
        n["calls"] += 1
        return {"explanations": [{"restaurant_id": r["restaurant_id"], "explanation": _good_text(r)}
                                 for r in _explanations_for(user)]}
    monkeypatch.setattr(ai_service, "call_model", fake)
    _ready_group(flow).match()
    # Mudança e volta: a nova rodada tem exatamente os mesmos dados, então a explicação vem do cache.
    flow.prefs("Caio", max_distance_km=11)
    flow.prefs("Caio", max_distance_km=10)
    recs = flow.match()["recommendations"]
    assert n["calls"] == 1 and recs[0]["explanation_source"] == "ia"
    for _ in range(3):
        client.get(f"/groups/{flow.group_id}/recommendations", headers=flow.H("Ana"))
    assert n["calls"] == 1  # consultar o ranking nunca chama a IA


def test_prompt_nao_recebe_restaurantes_inelegiveis(flow, monkeypatch):
    seen = {}

    def fake(system, user, schema, max_tokens):
        seen["payload"] = user
        raise ai_service.AIUnavailable("x")
    monkeypatch.setattr(ai_service, "call_model", fake)
    flow.create(party_size=2, budget_per_person=60)
    flow.join("Bia")
    flow.prefs("Ana", dietary_restrictions=["vegana"])
    flow.prefs("Bia")
    recs = flow.match()["recommendations"]
    sent = _explanations_for(seen["payload"])
    assert [r["nome"] for r in sent] == [r["restaurant"]["name"] for r in recs]
    assert "Omakase Kumo Azul" not in seen["payload"]  # R$ 240, não elegível
