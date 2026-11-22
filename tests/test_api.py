"""Regras de negócio, máquina de estados, autorização e formato da API."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.tables import GroupRow, ReservationRow, VoteRow
from app.services import state_machine as sm
from app.services.auth import INVITE_ALPHABET, new_invite_code


# ----------------------------------------------------------- criação e convite

def test_criar_encontro_gera_convite_e_tokens(flow):
    data = flow.create()
    g = data["group"]
    assert len(g["invite_code"]) == 8 and set(g["invite_code"]) <= set(INVITE_ALPHABET)
    assert g["invite_url"] == f"https://decide-ai-pi.vercel.app/entrar/{g['invite_code']}"
    assert g["status"] == "coletando_preferencias"
    assert data["organizer_token"] != data["identity"]["token"]
    assert len(data["organizer_token"]) >= 40


def test_codigos_de_convite_sao_aleatorios():
    codes = {new_invite_code() for _ in range(2000)}
    assert len(codes) == 2000


def test_erro_padronizado_em_validacao(client):
    r = client.post("/groups", json={"name": "x", "event_date": "2020-01-01", "event_time": "25:00",
                                     "budget_per_person": 5, "party_size": 1, "neighborhood": "Atlântida",
                                     "organizer_nickname": "A"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "dados_invalidos"
    fields = {d["field"] for d in err["details"]}
    assert {"name", "event_date", "event_time", "budget_per_person", "party_size", "neighborhood",
            "organizer_nickname"} <= fields


@pytest.mark.parametrize("nick", ["ana@email.com", "11987654321", "A"])
def test_apelido_nao_pode_ser_dado_pessoal(flow, nick):
    flow.create()
    r = flow.c.post("/groups/join", json={"invite_code": flow.code, "nickname": nick})
    assert r.status_code == 422


def test_entrar_com_codigo(flow):
    flow.create()
    preview = flow.c.get(f"/groups/by-code/{flow.code.lower()}").json()
    assert preview["accepting_participants"] and "participants" not in preview
    ident = flow.join("Bia")
    assert ident["is_simulated"] is False
    assert flow.c.post("/groups/join", json={"invite_code": flow.code, "nickname": "bia"}).status_code == 409
    assert flow.c.post("/groups/join", json={"invite_code": "ZZZZZZZZ", "nickname": "Caio"}).status_code == 404


def test_participante_simulado(flow):
    flow.create()
    ident = flow.join("Simulado 1", is_simulated=True)
    assert ident["is_simulated"] is True
    assert any(p["is_simulated"] for p in flow.group()["participants"])


# --------------------------------------------------------------- autorização

def test_ver_grupo_exige_token_do_proprio_grupo(flow, client):
    flow.create()
    assert client.get(f"/groups/{flow.group_id}").status_code == 401
    other = type(flow)(client)
    other.create(organizer="Zeca")
    r = client.get(f"/groups/{flow.group_id}", headers=other.H("Zeca"))
    assert r.status_code == 401
    assert client.get(f"/groups/{flow.group_id}", headers={"X-Organizer-Token": other.org}).status_code == 401
    assert client.get(f"/groups/{flow.group_id}", headers=flow.O).status_code == 200
    assert client.get(f"/groups/{uuid.uuid4()}", headers=flow.H("Ana")).status_code == 404


def test_participante_so_altera_as_proprias_preferencias(flow):
    flow.create()
    flow.join("Bia")
    body = {"origin_neighborhood": "Pinheiros"}
    r = flow.c.put(f"/participants/{flow.ids['Bia']}/preferences", json=body, headers=flow.H("Ana"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "sem_permissao"
    r = flow.c.put(f"/participants/{flow.ids['Bia']}/preferences", json=body)
    assert r.status_code == 401


def test_acoes_de_organizador(flow):
    flow.ready()
    m = flow.match()
    rid = m["recommendations"][0]["recommendation_id"]
    flow.vote("Bia", rid)
    r = flow.c.post(f"/groups/{flow.group_id}/close-voting", headers=flow.H("Bia"))
    assert r.status_code == 403
    flow.close()
    r = flow.c.post(f"/groups/{flow.group_id}/reservations", headers=flow.H("Bia"))
    assert r.status_code == 403


def test_valores_fora_da_lista_sao_rejeitados(flow):
    flow.create()
    r = flow.c.put(f"/participants/{flow.ids['Ana']}/preferences", headers=flow.H("Ana"),
                   json={"cuisines": ["marciana"], "origin_neighborhood": "Pinheiros"})
    assert r.status_code == 422


# ------------------------------------------------------------- regras do Match

def test_match_indisponivel_com_participante_sem_preferencias(flow):
    flow.create(party_size=3)
    flow.join("Bia")
    flow.join("Caio")
    flow.prefs("Ana")
    flow.prefs("Bia")
    err = flow.match(expect=409)["error"]
    assert err["code"] == "grupo_incompleto" and err["details"]["missing"] == ["Caio"]
    g = flow.group()
    assert g["status"] == "coletando_preferencias" and g["can_force_match"] and not g["can_generate_match"]


def test_match_indisponivel_enquanto_nao_entraram_todos(flow):
    flow.create(party_size=4)
    flow.join("Bia")
    flow.prefs("Ana")
    flow.prefs("Bia")
    err = flow.match(expect=409)["error"]
    assert "Entraram 2 de 4" in err["message"]


def test_gerar_com_quem_ja_respondeu(flow):
    flow.create(party_size=4)
    flow.join("Bia")
    flow.join("Caio")
    flow.prefs("Ana")
    assert flow.match("Ana", expect=409, force=True, organizer=True)["error"]["code"] == "poucas_respostas"
    flow.prefs("Bia")
    assert flow.match("Bia", expect=403, force=True)["error"]["code"] == "sem_permissao"
    m = flow.match("Ana", force=True, organizer=True)
    assert m["summary"]["forced"] is True
    assert m["summary"]["participants_missing"] == ["Caio"]
    assert m["summary"]["participants_included"] == ["Ana", "Bia"]
    assert flow.group()["status"] == "votacao_aberta"


def test_match_respeita_orcamento_e_restricoes(flow):
    flow.create(party_size=3, budget_per_person=90)
    flow.join("Bia")
    flow.join("Caio")
    flow.prefs("Ana", dietary_restrictions=["vegana"])
    flow.prefs("Bia", dietary_restrictions=["sem_gluten"], max_budget=70)
    flow.prefs("Caio", cuisines=["japonesa"])
    assert flow.group()["status"] == "match_disponivel"
    m = flow.match()
    assert m["summary"]["effective_budget"] == 70 and m["summary"]["budget_source"] == "Bia"
    assert m["recommendations"]
    for r in m["recommendations"]:
        assert r["restaurant"]["avg_price"] <= 70
        assert {"vegana", "sem_gluten"} <= set(r["restaurant"]["dietary_options"])
        assert len(r["breakdown"]) == 3 and r["explanation"] and r["attention_point"]


def test_nenhum_elegivel_mostra_motivo_e_sugestoes(flow):
    flow.create(party_size=2, budget_per_person=30)
    flow.join("Bia")
    flow.prefs("Ana", dietary_restrictions=["vegana", "sem_gluten"])
    flow.prefs("Bia")
    m = flow.match()
    s = m["summary"]
    assert m["recommendations"] == [] and s["eligible_count"] == 0
    assert s["eliminated_by"]["orcamento"] > 0 and "Nenhum dos 50" in s["conflict_message"]
    budget = next(x for x in s["suggestions"] if x["type"] == "orcamento")
    assert budget["value"] > 30 and budget["count"] >= 1
    assert flow.group()["status"] == "match_disponivel"  # continua podendo ajustar
    # O organizador aplica a sugestão
    r = flow.c.patch(f"/groups/{flow.group_id}", json={"budget_per_person": budget["value"]}, headers=flow.O)
    assert r.status_code == 200
    m = flow.match()
    assert len(m["recommendations"]) >= 1 and m["round_number"] == 2


# ----------------------------------------------------- votação e invalidação

def test_votar_de_novo_atualiza_sem_duplicar(flow, db):
    flow.ready()
    recs = flow.match()["recommendations"]
    flow.vote("Bia", recs[0]["recommendation_id"])
    res = flow.vote("Bia", recs[1]["recommendation_id"])
    assert res["total_votes"] == 1 and res["my_vote"] == recs[1]["recommendation_id"]
    assert db.query(VoteRow).count() == 1


def test_um_voto_ativo_por_participante_por_rodada_no_banco(flow, db):
    flow.ready()
    rec = flow.match()["recommendations"][0]
    flow.vote("Bia", rec["recommendation_id"])
    v = db.query(VoteRow).one()
    db.add(VoteRow(participant_id=v.participant_id, recommendation_id=v.recommendation_id, group_id=v.group_id,
                   round_number=v.round_number))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_mudar_preferencia_depois_do_match_invalida_ranking_e_votos(flow):
    flow.ready()
    old = flow.match()["recommendations"]
    flow.vote("Bia", old[0]["recommendation_id"])
    out = flow.prefs("Caio", dietary_restrictions=["vegana"])
    assert out["round_invalidated"] is True and out["group_status"] == "match_disponivel"
    g = flow.group()
    assert g["status"] == "match_disponivel" and g["counts"]["voted"] == 0
    assert flow.c.get(f"/groups/{flow.group_id}/recommendations", headers=flow.H("Ana")).json()["recommendations"] == []
    # Voto em recomendação antiga é recusado
    assert flow.vote("Bia", old[0]["recommendation_id"], expect=409)["error"]["code"] in ("etapa_invalida",
                                                                                          "rodada_invalidada")
    new = flow.match()
    assert new["round_number"] == 2
    assert all("vegana" in r["restaurant"]["dietary_options"] for r in new["recommendations"])
    assert flow.vote("Bia", old[0]["recommendation_id"], expect=409)["error"]["code"] == "rodada_invalidada"


def test_mudar_so_o_texto_livre_nao_invalida(flow):
    flow.ready()
    flow.match()
    out = flow.prefs("Caio", free_text="na verdade tanto faz")
    assert out["round_invalidated"] is False and flow.group()["status"] == "votacao_aberta"


def test_novo_participante_durante_a_votacao_abre_nova_rodada_ao_responder(flow):
    flow.ready()
    flow.match()
    flow.join("Duda")
    assert flow.group()["status"] == "votacao_aberta"
    out = flow.prefs("Duda")
    assert out["round_invalidated"] is True and out["group_status"] == "match_disponivel"


def test_empate_vence_maior_score(flow):
    flow.ready(("Ana", "Bia", "Caio", "Duda"))
    recs = flow.match()["recommendations"]
    a, b = recs[0], recs[1]
    assert a["score"] >= b["score"]
    flow.vote("Ana", b["recommendation_id"])
    flow.vote("Bia", b["recommendation_id"])
    flow.vote("Caio", a["recommendation_id"])
    flow.vote("Duda", a["recommendation_id"])
    out = flow.close()
    assert out["winner_recommendation_id"] == a["recommendation_id"]
    assert "Empate" in out["decision_note"] and "maior score coletivo" in out["decision_note"]


def test_mais_votos_vence_mesmo_com_score_menor(flow):
    flow.ready()
    recs = flow.match()["recommendations"]
    third = recs[2]["recommendation_id"]
    for n in ("Ana", "Bia"):
        flow.vote(n, third)
    flow.vote("Caio", recs[0]["recommendation_id"])
    assert flow.close()["winner_recommendation_id"] == third


def test_sem_votos_vence_maior_score(flow):
    flow.ready()
    recs = flow.match()["recommendations"]
    out = flow.close()
    assert out["winner_recommendation_id"] == recs[0]["recommendation_id"]
    assert "Ninguém votou" in out["decision_note"]


def test_prazo_da_votacao_encerra_sozinho(flow, db):
    flow.ready()
    flow.match()
    g = db.get(GroupRow, uuid.UUID(flow.group_id))
    g.vote_deadline = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert flow.group()["status"] == "escolha_concluida"


def test_nao_vota_antes_do_match(flow):
    flow.ready()
    err = flow.vote("Ana", str(uuid.uuid4()), expect=409)["error"]
    assert err["code"] == "etapa_invalida"


# ------------------------------------------------------- reserva e retorno

def test_reserva_so_depois_da_escolha(flow, db):
    flow.ready()
    flow.match()
    r = flow.c.post(f"/groups/{flow.group_id}/reservations", headers=flow.O)
    assert r.status_code == 409
    flow.close()
    r = flow.c.post(f"/groups/{flow.group_id}/reservations", headers=flow.O)
    assert r.status_code == 201
    res = r.json()
    assert res["is_simulated"] is True and res["label"] == "Reserva simulada"
    assert res["confirmation_code"].startswith("SIM-")
    assert db.get(ReservationRow, uuid.UUID(res["id"])).is_simulated is True
    assert flow.c.post(f"/groups/{flow.group_id}/reservations", headers=flow.O).status_code == 409
    assert flow.group()["status"] == "reserva_simulada"


def test_banco_recusa_reserva_nao_simulada_e_segunda_reserva(flow, db):
    flow.ready()
    flow.match()
    flow.close()
    res_id = flow.c.post(f"/groups/{flow.group_id}/reservations", headers=flow.O).json()["id"]
    res = db.get(ReservationRow, uuid.UUID(res_id))
    dup = ReservationRow(group_id=res.group_id, restaurant_id=res.restaurant_id, recommendation_id=res.recommendation_id,
                         status="confirmada", booking_time=res.booking_time, party_size=3, confirmation_code="SIM-X",
                         is_simulated=True)
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    res = db.get(ReservationRow, uuid.UUID(res_id))
    res.is_simulated = False
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_avaliacao(flow, client):
    flow.ready()
    flow.match()
    flow.close()
    res = client.post(f"/groups/{flow.group_id}/reservations", headers=flow.O).json()
    url = f"/reservations/{res['id']}/reviews"
    assert client.post(url, json={"rating": 6}, headers=flow.H("Bia")).status_code == 422
    out = client.post(url, json={"rating": 4, "comment": "Bom"}, headers=flow.H("Bia")).json()
    assert out["my_review"] == {"rating": 4, "comment": "Bom"}
    client.post(url, json={"rating": 5}, headers=flow.H("Bia"))
    assert flow.group("Bia")["reservation"]["reviews"] == {"count": 1, "average": 5.0}
    assert flow.group()["status"] == "avaliado"
    other = type(flow)(client)
    other.create(organizer="Zeca")
    assert client.post(url, json={"rating": 1}, headers=other.H("Zeca")).status_code == 403


def test_preferencias_travadas_depois_da_escolha(flow):
    flow.ready()
    flow.match()
    flow.close()
    assert flow.prefs("Bia", expect=409)["error"]["code"] == "encontro_fechado"
    r = flow.c.post("/groups/join", json={"invite_code": flow.code, "nickname": "Tardio"})
    assert r.status_code == 409


def test_recarregar_recupera_tudo(flow):
    flow.ready()
    rec = flow.match()["recommendations"][0]
    flow.vote("Bia", rec["recommendation_id"])
    g = flow.group("Bia")
    assert g["me"]["vote_recommendation_id"] == rec["recommendation_id"]
    assert g["me"]["preferences"]["origin_neighborhood"] == "Pinheiros"
    assert g["match_summary"]["round_number"] == 1
    again = flow.c.get(f"/groups/{flow.group_id}/recommendations", headers=flow.H("Bia")).json()
    assert again["recommendations"][0]["explanation"] == rec["explanation"]  # explicação vem do banco, não é refeita


# ---------------------------------------------------------- máquina de estados

def test_transicoes_permitidas_e_proibidas():
    class G:
        status = "coletando_preferencias"
    g = G()
    for nxt in ["match_disponivel", "votacao_aberta", "escolha_concluida", "reserva_simulada", "avaliado"]:
        sm.transition(g, nxt)
    assert g.status == "avaliado"
    for bad_from, bad_to in [("coletando_preferencias", "escolha_concluida"), ("match_disponivel", "reserva_simulada"),
                             ("escolha_concluida", "votacao_aberta"), ("avaliado", "coletando_preferencias"),
                             ("reserva_simulada", "escolha_concluida")]:
        g.status = bad_from
        with pytest.raises(sm.AppError) as e:
            sm.transition(g, bad_to)
        assert e.value.status == 409 and e.value.code == "transicao_invalida"


def test_status_no_banco_tem_restricao(db):
    from app.models.tables import GroupRow
    from datetime import date
    db.add(GroupRow(invite_code="ABCDEFGH", name="x", event_date=date.today(), event_time="20:00",
                    budget_per_person=50, party_size=2, neighborhood="Pinheiros", organizer_token_hash="x" * 64,
                    status="inventado"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ------------------------------------------------------------ demo e métricas

def test_demonstracao(client):
    d = client.post("/demo").json()
    assert d["group"]["is_demo"] and d["group"]["status"] == "match_disponivel"
    assert [i["nickname"] for i in d["identities"]] == ["Ana", "Bruno", "Carla", "Davi"]
    ana = {"X-Participant-Token": d["identities"][0]["token"]}
    m = client.post(f"/groups/{d['group']['id']}/match", headers=ana).json()
    assert len(m["recommendations"]) == 3
    assert m["summary"]["budget_source"] == "Bruno"


def test_metricas_do_funil(flow, client):
    client.post("/demo")
    flow.ready()
    flow.match()
    client.get(f"/groups/{flow.group_id}/recommendations", headers=flow.H("Bia"))
    flow.close()
    client.post(f"/groups/{flow.group_id}/reservations", headers=flow.O)
    other = type(flow)(client)
    other.create(organizer="Zeca")

    from conftest import ADMIN
    assert client.get("/metrics").status_code == 403
    assert client.get("/metrics", headers={"X-Admin-Token": "errada"}).status_code == 403
    m = client.get("/metrics", headers=ADMIN).json()
    steps = {s["step"]: s["groups"] for s in m["funnel"]}
    assert steps == {"group_created": 2, "preferences_completed": 1, "recommendations_viewed": 1,
                     "choice_completed": 1, "reservation_simulated": 1}
    assert m["main_metric"]["value_pct"] == 50.0
    assert m["avg_minutes_to_decision"] is not None
    assert "Não são conversões reais" in m["notice"]
    assert client.get("/metrics?include_demo=true", headers=ADMIN).json()["funnel"][0]["groups"] == 3


def test_health_e_meta(client):
    assert client.get("/health").json()["database"] == "ok"
    meta = client.get("/meta").json()
    assert {"cuisines", "dietary_options", "ambiences", "neighborhoods", "occasions"} <= set(meta)


def test_cors_restrito(client):
    ok = client.options("/groups", headers={"Origin": "https://decide-ai-pi.vercel.app",
                                            "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "https://decide-ai-pi.vercel.app"
    bad = client.options("/groups", headers={"Origin": "https://site-malicioso.com",
                                             "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_rate_limit_na_rota_de_ia(flow, client):
    from app.limiter import limiter
    flow.create()
    limiter.enabled = True
    limiter.reset()
    try:
        codes = [client.post("/ai/parse-preferences", json={"text": "quero sushi"}, headers=flow.H("Ana")).status_code
                 for _ in range(11)]
    finally:
        limiter.enabled = False
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_cors_recusa_outros_projetos_da_vercel(client):
    """Só o domínio de produção e as previews desta conta; 'decide-ai.vercel.app' é de outra pessoa."""
    for origin, allowed in [("https://decide-ai-pi.vercel.app", True),
                            ("https://decide-kpbe5ph98-catarinacm.vercel.app", True),
                            ("https://decide-ai.vercel.app", False),
                            ("https://decide-ai-qualquer.vercel.app", False)]:
        r = client.options("/groups", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        assert (r.headers.get("access-control-allow-origin") == origin) is allowed, origin
