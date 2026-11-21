"""Testes do motor de recomendação (filtros, score, penalização, desempate, sugestões)."""
import json
import random
from datetime import date
from pathlib import Path

import pytest

from app.services import matching as m
from app.services.matching import GroupContext, ParticipantPrefs, Restaurant

SAT = date(2026, 11, 28)  # sábado
MON = date(2026, 11, 30)  # segunda
ALL_WEEK = {d: ["11:00-23:59"] for d in m.WEEKDAYS}
ORIGIN = (-23.5670, -46.6930)  # centro de Pinheiros


def rest(id, *, price=60, cuisine="italiana", diets=("vegetariana",), cap=20, amb=("casual",),
         lat=ORIGIN[0], lng=ORIGIN[1], hours=None, rate=1.0, rating=4.5, name=None):
    return Restaurant(id=id, name=name or f"R-{id}", cuisine=cuisine, neighborhood="Pinheiros",
                      latitude=lat, longitude=lng, avg_price=price, dietary_options=frozenset(diets),
                      capacity=cap, ambiences=frozenset(amb), opening_hours=hours or ALL_WEEK,
                      availability_rate=rate, rating=rating)


def person(id, *, cuisines=(), diets=(), amb=(), maxd=10.0, budget=None, lat=ORIGIN[0], lng=ORIGIN[1]):
    return ParticipantPrefs(id=id, nickname=id.capitalize(), latitude=lat, longitude=lng, cuisines=tuple(cuisines),
                            dietary_restrictions=tuple(diets), ambiences=tuple(amb), max_distance_km=maxd,
                            max_budget=budget)


def group(budget=100, size=2, d=SAT, t="20:00"):
    return GroupContext(budget_per_person=budget, party_size=size, event_date=d, event_time=t)


def ids(result):
    return [r.restaurant.id for r in result.recommendations]


# ---------------------------------------------------------------- Etapa A

class TestFiltros:
    def test_preco_acima_do_orcamento_e_eliminado(self):
        res = m.run_match([rest("a", price=90), rest("b", price=120)], [person("ana")], group(budget=100))
        assert ids(res) == ["a"]
        assert res.eliminated_by["orcamento"] == 1

    def test_preco_igual_ao_orcamento_passa(self):
        assert ids(m.run_match([rest("a", price=100)], [person("ana")], group(budget=100))) == ["a"]

    def test_orcamento_individual_reduz_o_teto(self):
        ps = [person("ana"), person("bruno", budget=60)]
        res = m.run_match([rest("a", price=55), rest("b", price=80)], ps, group(budget=100))
        assert ids(res) == ["a"]
        assert res.effective_budget == 60 and res.budget_source == "Bruno"

    def test_orcamento_individual_maior_que_o_do_grupo_nao_amplia(self):
        res = m.run_match([rest("a", price=120)], [person("ana", budget=200)], group(budget=100))
        assert res.eligible_count == 0 and res.effective_budget == 100

    def test_restricao_de_qualquer_participante_e_obrigatoria(self):
        rs = [rest("a", diets=("vegetariana",)), rest("b", diets=("vegetariana", "sem_gluten"))]
        ps = [person("ana", diets=["vegetariana"]), person("davi", diets=["sem_gluten"])]
        res = m.run_match(rs, ps, group())
        assert ids(res) == ["b"]
        assert res.required_diets == ["sem_gluten", "vegetariana"]

    def test_vegana_exige_opcao_vegana(self):
        rs = [rest("a", diets=("vegetariana",)), rest("b", diets=("vegetariana", "vegana"))]
        assert ids(m.run_match(rs, [person("ana", diets=["vegana"])], group())) == ["b"]

    def test_capacidade_usa_o_maior_entre_party_size_e_participantes(self):
        rs = [rest("a", cap=3), rest("b", cap=6)]
        assert ids(m.run_match(rs, [person("ana"), person("bia")], group(size=5))) == ["b"]
        assert m.run_match(rs, [person("ana")], group(size=1)).group_size == 1

    def test_fechado_no_dia_e_eliminado(self):
        hours = {**ALL_WEEK, "seg": []}
        res = m.run_match([rest("a", hours=hours), rest("b")], [person("ana")], group(d=MON))
        assert ids(res) == ["b"] and res.eliminated_by["horario"] == 1

    def test_fechado_no_horario_e_eliminado(self):
        hours = {d: ["12:00-15:00"] for d in m.WEEKDAYS}
        assert m.run_match([rest("a", hours=hours)], [person("ana")], group(t="20:00")).eligible_count == 0
        assert m.run_match([rest("a", hours=hours)], [person("ana")], group(t="13:00")).eligible_count == 1

    def test_horario_de_fechamento_nao_conta_como_aberto(self):
        hours = {d: ["12:00-20:00"] for d in m.WEEKDAYS}
        assert m.run_match([rest("a", hours=hours)], [person("ana")], group(t="20:00")).eligible_count == 0

    def test_sem_mesa_disponivel_e_eliminado(self):
        assert m.run_match([rest("a", rate=0.0)], [person("ana")], group()).eligible_count == 0

    def test_disponibilidade_e_deterministica(self):
        r = rest("x", rate=0.5)
        first = [m.has_table(r, SAT, f"{h:02d}:00") for h in range(11, 24)]
        assert first == [m.has_table(r, SAT, f"{h:02d}:00") for h in range(11, 24)]
        assert True in first and False in first  # taxa de 50% gera dos dois

    def test_contagem_por_filtro_e_mensagem_de_conflito(self):
        rs = [rest("a", price=200), rest("b", diets=()), rest("c", cap=1)]
        res = m.run_match(rs, [person("ana", diets=["vegetariana"]), person("bia")], group(budget=100))
        assert res.eligible_count == 0 and res.recommendations == []
        assert res.eliminated_by == {"orcamento": 1, "restricoes": 1, "capacidade": 1, "horario": 0}
        assert "Nenhum dos 3 restaurantes" in res.conflict_message


# ---------------------------------------------------------------- Etapa B

class TestScore:
    def test_gastronomia(self):
        r = rest("a", cuisine="japonesa")
        assert m.score_gastronomy(r, person("x", cuisines=["japonesa"])) == 100
        assert m.score_gastronomy(r, person("x", cuisines=["italiana"])) == 25
        assert m.score_gastronomy(r, person("x")) == m.NEUTRAL_G

    def test_preco_mais_barato_pontua_mais(self):
        cheap, pricey = rest("a", price=40), rest("b", price=100)
        assert m.score_price(cheap, 100) > m.score_price(pricey, 100)
        assert 0 <= m.score_price(pricey, 100) <= 100

    def test_localizacao_respeita_distancia_maxima(self):
        assert m.score_location(0, 10) == 100
        assert m.score_location(10, 10) == pytest.approx(40)
        assert m.score_location(15, 10) == pytest.approx(20)
        assert m.score_location(20, 10) == 0
        assert m.score_location(5, 10) > m.score_location(5, 5)

    def test_ambiente_com_conflito_tranquilo_animado(self):
        calm = person("x", amb=["tranquilo"])
        assert m.score_ambience(rest("a", amb=("tranquilo",)), calm) == 100
        assert m.score_ambience(rest("a", amb=("casual",)), calm) == 20
        assert m.score_ambience(rest("a", amb=("animado",)), calm) == 0
        assert m.score_ambience(rest("a"), person("x")) == m.NEUTRAL_A

    def test_formula_ponderada(self):
        s = m.score_participant(rest("a", cuisine="japonesa"), person("x", cuisines=["japonesa"]), group())
        expected = 0.40 * s.G + 0.25 * s.P + 0.20 * s.L + 0.15 * s.A
        assert s.score == pytest.approx(expected, abs=0.1)
        assert all(0 <= v <= 100 for v in (s.G, s.P, s.L, s.A))

    def test_haversine(self):
        # Pinheiros -> Liberdade: aproximadamente 6 km em linha reta
        assert 5.5 < m.haversine_km(-23.5670, -46.6930, -23.5580, -46.6350) < 6.5
        assert m.haversine_km(*ORIGIN, *ORIGIN) == 0

    def test_detalhamento_por_participante(self):
        ps = [person("ana"), person("bia"), person("caio")]
        rec = m.run_match([rest("a")], ps, group(size=3)).recommendations[0]
        assert [b.nickname for b in rec.breakdown] == ["Ana", "Bia", "Caio"]
        assert {"G", "P", "L", "A", "score", "distance_km"} <= set(vars(rec.breakdown[0]))


class TestPenalizacao:
    def test_sem_penalizacao_quando_todos_acima_de_50(self):
        assert m.group_score([80, 60, 50]) == (63.3, 63.3, 0.0)

    def test_penaliza_meio_ponto_por_ponto_abaixo_de_50(self):
        score, mean, penalty = m.group_score([90, 90, 30])
        assert mean == 70 and penalty == 10 and score == 60

    def test_penalizacao_troca_o_vencedor(self):
        """Um lugar ótimo para dois e péssimo para um perde para um lugar equilibrado."""
        far = (-23.40, -46.50)  # Caio mora a cerca de 27 km dos outros três
        mid = ((ORIGIN[0] + far[0]) / 2, (ORIGIN[1] + far[1]) / 2)
        # Ótimo para Ana, Bia e Duda (culinária, ambiente, na porta) e ruim para Caio (longe, ambiente oposto).
        polarizing = rest("polar", cuisine="japonesa", amb=("animado",))
        # Razoável para todos: culinária que todos aceitam, no meio do caminho.
        balanced = rest("equil", cuisine="brasileira", amb=("casual",), lat=mid[0], lng=mid[1])
        fans = dict(cuisines=["japonesa", "brasileira"], amb=["animado"], maxd=15)
        ps = [person("ana", **fans), person("bia", **fans), person("duda", **fans),
              person("caio", cuisines=["brasileira"], amb=["tranquilo"], maxd=15, lat=far[0], lng=far[1])]
        res = m.run_match([polarizing, balanced], ps, group(size=4))
        by_id = {r.restaurant.id: r for r in res.recommendations}
        assert by_id["polar"].mean_score > by_id["equil"].mean_score  # pela média, ganharia
        assert by_id["polar"].penalty > 0 and by_id["equil"].penalty == 0
        assert ids(res)[0] == "equil"  # com a penalização, perde


class TestRanking:
    def test_top3_ordenado_por_score(self):
        ps = [person("ana", cuisines=["japonesa"])]
        rs = [rest("a", cuisine="italiana"), rest("b", cuisine="japonesa"), rest("c", cuisine="japonesa", price=90),
              rest("d", cuisine="mexicana", price=95)]
        res = m.run_match(rs, ps, group())
        assert len(res.recommendations) == 3
        assert ids(res)[:2] == ["b", "c"]
        assert [r.rank for r in res.recommendations] == [1, 2, 3]
        scores = [r.score for r in res.recommendations]
        assert scores == sorted(scores, reverse=True)

    def test_empate_no_score_vence_o_mais_barato(self):
        # Mesmo preço relativo dentro da faixa de 100 pontos (até 50% do orçamento) => mesmo score.
        rs = [rest("caro", price=50, name="A"), rest("barato", price=40, name="B")]
        res = m.run_match(rs, [person("ana")], group(budget=100))
        assert res.recommendations[0].score == res.recommendations[1].score
        assert ids(res) == ["barato", "caro"]

    def test_ponto_de_atencao_cita_distancia(self):
        ps = [person("ana"), person("caio", maxd=5, lat=-23.50, lng=-46.62)]
        rec = m.run_match([rest("a")], ps, group()).recommendations[0]
        assert "Caio" in rec.attention_point and "km" in rec.attention_point

    def test_destaques_usam_so_atributos_cadastrados(self):
        rec = m.run_match([rest("a", price=70)], [person("ana", diets=["vegetariana"], cuisines=["italiana"])],
                          group()).recommendations[0]
        text = " ".join(rec.highlights)
        assert "R$ 70" in text and "vegetariana" in text and "italiana" in text


class TestSugestoes:
    def test_sugere_orcamento_concreto(self):
        rs = [rest("a", price=110), rest("b", price=118), rest("c", price=125), rest("d", price=200)]
        res = m.run_match(rs, [person("ana")], group(budget=100))
        s = next(x for x in res.suggestions if x["type"] == "orcamento")
        assert s["value"] == 125 and s["count"] == 3
        assert s["message"] == "Subindo o orçamento por pessoa de R$ 100 para R$ 125, surgem 3 opções."

    def test_sugestao_de_orcamento_cita_quem_limita(self):
        res = m.run_match([rest("a", price=80)], [person("ana"), person("bruno", budget=60)], group(budget=100))
        s = next(x for x in res.suggestions if x["type"] == "orcamento")
        assert "limite de Bruno" in s["message"] and s["value"] == 80

    def test_sugere_horario_alternativo(self):
        hours = {d: ["12:00-15:00"] for d in m.WEEKDAYS}
        res = m.run_match([rest("a", hours=hours)], [person("ana")], group(t="20:00"))
        s = next(x for x in res.suggestions if x["type"] == "horario")
        assert s["value"] == "14:30" and s["count"] == 1

    def test_sugere_outro_dia(self):
        hours = {**{d: [] for d in m.WEEKDAYS}, "dom": ["11:00-23:00"]}
        res = m.run_match([rest("a", hours=hours)], [person("ana")], group(d=SAT))
        s = next(x for x in res.suggestions if x["type"] == "data")
        assert s["value"] == "2026-11-29"

    def test_restricao_nunca_e_relaxada_em_silencio(self):
        res = m.run_match([rest("a", diets=())], [person("ana", diets=["sem_gluten"])], group())
        assert res.eligible_count == 0
        s = next(x for x in res.suggestions if x["type"] == "restricoes")
        assert "Só altere se ela não for obrigatória" in s["message"]

    def test_sem_sugestoes_quando_ha_3_ou_mais(self):
        res = m.run_match([rest(str(i)) for i in range(4)], [person("ana")], group())
        assert res.suggestions == [] and res.conflict_message is None

    def test_exige_participante(self):
        with pytest.raises(ValueError):
            m.run_match([rest("a")], [], group())


# ----------------------------------------------- propriedades com o seed real

SEED = json.loads((Path(__file__).resolve().parents[1] / "data" / "restaurants_seed.json").read_text(encoding="utf-8"))
REAL = [Restaurant.from_dict(r) for r in SEED]
REF = json.loads((Path(__file__).resolve().parents[1] / "data" / "reference.json").read_text(encoding="utf-8"))


def test_nenhuma_recomendacao_viola_filtros_obrigatorios():
    """Em 300 grupos aleatórios, todo restaurante recomendado respeita orçamento,
    restrições, capacidade e horário."""
    rng = random.Random(7)
    hoods = list(REF["neighborhoods"].items())
    for _ in range(300):
        ps = []
        for i in range(rng.randint(2, 6)):
            _, c = rng.choice(hoods)
            ps.append(person(f"p{i}", cuisines=rng.sample(list(REF["cuisines"]), rng.randint(0, 3)),
                             diets=rng.sample(list(REF["dietary_options"]), rng.choice([0, 0, 1, 2])),
                             amb=rng.sample(list(REF["ambiences"]), rng.randint(0, 2)),
                             budget=rng.choice([None, None, 50, 70, 90]), lat=c["lat"], lng=c["lng"],
                             maxd=rng.choice([3, 8, 15])))
        g = group(budget=rng.choice([40, 60, 100, 150, 250]), size=len(ps),
                  d=date(2026, 12, rng.randint(1, 28)), t=rng.choice(["12:30", "13:00", "19:30", "20:00", "21:30"]))
        res = m.run_match(REAL, ps, g)
        diets = {d for p in ps for d in p.dietary_restrictions}
        for rec in res.recommendations:
            r = rec.restaurant
            assert r.avg_price <= res.effective_budget
            assert diets <= r.dietary_options
            assert r.capacity >= len(ps)
            assert m.is_available(r, g.event_date, g.event_time)
            assert 0 <= rec.score <= 100
        assert len(res.recommendations) == min(3, res.eligible_count)


def test_cenario_da_demonstracao_tem_opcoes():
    """O grupo de demonstração (vegetariana, orçamento apertado, alguém longe, sem glúten)
    precisa ter pelo menos 3 opções num sábado à noite."""
    hoods = REF["neighborhoods"]
    ps = [
        person("ana", cuisines=["italiana", "japonesa"], diets=["vegetariana"], amb=["tranquilo", "casual"], maxd=8,
               lat=hoods["Pinheiros"]["lat"], lng=hoods["Pinheiros"]["lng"]),
        person("bruno", cuisines=["brasileira", "hamburgueria"], amb=["casual"], budget=60, maxd=10,
               lat=hoods["Vila Mariana"]["lat"], lng=hoods["Vila Mariana"]["lng"]),
        person("carla", cuisines=["japonesa", "mexicana"], amb=["animado"], maxd=12,
               lat=hoods["Santana"]["lat"], lng=hoods["Santana"]["lng"]),
        person("davi", cuisines=["brasileira", "pizzaria"], diets=["sem_gluten"], amb=["ao_ar_livre"], maxd=10,
               lat=hoods["Butantã"]["lat"], lng=hoods["Butantã"]["lng"]),
    ]
    for saturday in [date(2026, 11, 28), date(2026, 12, 5), date(2026, 12, 12), date(2027, 1, 9)]:
        res = m.run_match(REAL, ps, group(budget=100, size=4, d=saturday, t="20:00"))
        assert res.eligible_count >= 3, saturday
