"""O seed real passa no validador, e cada tipo de erro é de fato detectado."""
import copy
import json
from pathlib import Path

import pytest

from validate_seed import validate

DATA = Path(__file__).resolve().parents[1] / "data"
REF = json.loads((DATA / "reference.json").read_text(encoding="utf-8"))
SEED = json.loads((DATA / "restaurants_seed.json").read_text(encoding="utf-8"))


def errors_after(mutate):
    seed = copy.deepcopy(SEED)
    mutate(seed)
    return validate(seed, REF)


def test_seed_real_e_valido():
    assert validate(SEED, REF) == []


def test_seed_e_reproduzivel():
    from generate_seed import build
    assert build() == SEED


def test_preco_incoerente_com_culinaria():
    def m(s):
        r = next(x for x in s if x["cuisine"] == "francesa")
        r["avg_price"] = 40
    assert any("incoerente com francesa" in e for e in errors_after(m))


@pytest.mark.parametrize("campo", ["name", "avg_price", "opening_hours", "latitude"])
def test_campo_faltando(campo):
    assert any("campos faltando" in e and campo in e for e in errors_after(lambda s: s[0].pop(campo)))


def test_vegana_sem_vegetariana():
    def m(s):
        s[0]["dietary_options"] = ["vegana"]
    assert any("vegana sem vegetariana" in e for e in errors_after(m))


def test_nome_duplicado_ignora_acento_e_caixa():
    def m(s):
        s[1]["name"] = s[0]["name"].upper()
    assert any("nome duplicado" in e for e in errors_after(m))


def test_nome_de_estabelecimento_real():
    def m(s):
        s[0]["name"] = "Cantina Fasano"
    assert any("estabelecimento real" in e for e in errors_after(m))


def test_ambientes_contraditorios():
    def m(s):
        s[0]["ambiences"] = ["tranquilo", "animado"]
    assert any("contraditórios" in e for e in errors_after(m))


def test_coordenada_fora_do_bairro():
    def m(s):
        s[0]["latitude"] += 0.05
    assert any("km do centro" in e for e in errors_after(m))


def test_horario_invalido():
    def m(s):
        s[0]["opening_hours"]["sab"] = ["25:00-23:00"]
    assert any("horário inválido" in e for e in errors_after(m))


def test_beneficio_precisa_ser_simulado():
    def m(s):
        s[0]["simulated_benefit"] = "10% de desconto"
    assert any("simulado" in e for e in errors_after(m))
