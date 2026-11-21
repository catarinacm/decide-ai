"""Valida data/restaurants_seed.json. Sai com código 1 se encontrar qualquer problema.

Regras verificadas:
- todos os campos obrigatórios presentes e com o tipo certo;
- valores de culinária, opções alimentares e ambientes dentro dos permitidos;
- preço coerente com a faixa da culinária e dentro dos limites gerais;
- combinações válidas (vegana exige vegetariana; restaurante vegetariano não pode
  deixar de oferecer opção vegetariana; ambientes contraditórios);
- coordenadas a no máximo 1,5 km do centro do bairro declarado;
- horários no formato HH:MM-HH:MM e pelo menos um dia aberto;
- nomes e ids únicos, e nenhum nome igual a uma lista de estabelecimentos reais conhecidos;
- diversidade mínima da base (culinárias, bairros e faixas de preço).

Uso:  python data/validate_seed.py [caminho_do_seed]
"""
from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).parent

REQUIRED = {
    "id": str, "slug": str, "name": str, "cuisine": str, "description": str,
    "neighborhood": str, "city": str, "latitude": float, "longitude": float,
    "avg_price": int, "dietary_options": list, "capacity": int, "ambiences": list,
    "opening_hours": dict, "availability_rate": float, "rating": float,
    "rating_count": int, "accepts_reservation": bool, "is_fictional": bool,
}
OPTIONAL = {"simulated_benefit": (str, type(None))}

# Nomes de estabelecimentos e redes reais conhecidos em São Paulo. A base não pode
# usar nenhum deles, nem conter um deles como parte do nome.
REAL_NAMES_BLOCKLIST = [
    "fasano", "d.o.m", "dom restaurante", "mocoto", "figueira rubaiyat", "rubaiyat", "mani",
    "jiquitaia", "braz", "famiglia mancini", "madero", "outback", "coco bambu", "fogo de chao",
    "terraco italia", "bar da dona onca", "a casa do porco", "casa do porco", "tordesilhas",
    "jun sakamoto", "kinoshita", "aizome", "spot", "consulado mineiro", "bar do mane",
    "bacio di latte", "starbucks", "mcdonald", "burger king", "habibs", "china in box",
    "pizza hut", "dominos", "subway", "spoleto", "giraffas", "ragazzo", "america",
    "frevo", "veloso", "skye", "evvai", "maito", "notiluca", "corrutela", "metzi",
]

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9. ]", " ", s).split())


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def validate(restaurants: list[dict], ref: dict) -> list[str]:
    errors: list[str] = []
    cuisines, diets, ambs = ref["cuisines"], set(ref["dietary_options"]), set(ref["ambiences"])
    hoods, days = ref["neighborhoods"], ref["weekdays"]
    bounds = ref["price_bounds"]
    seen_names: dict[str, str] = {}
    seen_ids: set[str] = set()

    for idx, r in enumerate(restaurants):
        tag = f"[{idx}] {r.get('name', '<sem nome>')}"

        # Campos e tipos
        missing = [k for k in REQUIRED if k not in r or r[k] is None or r[k] == ""]
        if missing:
            errors.append(f"{tag}: campos faltando: {', '.join(missing)}")
            continue
        for k, t in REQUIRED.items():
            ok = isinstance(r[k], t) and not (t is int and isinstance(r[k], bool))
            if t is float and isinstance(r[k], int) and not isinstance(r[k], bool):
                ok = True
            if not ok:
                errors.append(f"{tag}: campo '{k}' deveria ser {t.__name__}")
        for k, t in OPTIONAL.items():
            if k in r and not isinstance(r[k], t):
                errors.append(f"{tag}: campo '{k}' com tipo inválido")
        unknown = set(r) - set(REQUIRED) - set(OPTIONAL)
        if unknown:
            errors.append(f"{tag}: campos desconhecidos: {', '.join(sorted(unknown))}")

        # Unicidade
        n = norm(r["name"])
        if n in seen_names:
            errors.append(f"{tag}: nome duplicado (igual a '{seen_names[n]}')")
        seen_names[n] = r["name"]
        if r["id"] in seen_ids:
            errors.append(f"{tag}: id duplicado")
        seen_ids.add(r["id"])

        # Nome não pode lembrar estabelecimento real
        for real in REAL_NAMES_BLOCKLIST:
            if re.search(rf"(^| ){re.escape(real)}( |$)", n):
                errors.append(f"{tag}: nome contém '{real}', que é um estabelecimento real")

        # Culinária e preço
        c = cuisines.get(r["cuisine"])
        if c is None:
            errors.append(f"{tag}: culinária inválida '{r['cuisine']}'")
        else:
            if not (c["price_min"] <= r["avg_price"] <= c["price_max"]):
                errors.append(
                    f"{tag}: preço R$ {r['avg_price']} incoerente com {r['cuisine']} "
                    f"(faixa R$ {c['price_min']}-{c['price_max']})"
                )
        if not (bounds["min"] <= r["avg_price"] <= bounds["max"]):
            errors.append(f"{tag}: preço fora dos limites gerais R$ {bounds['min']}-{bounds['max']}")

        # Opções alimentares
        d = set(r["dietary_options"])
        if d - diets:
            errors.append(f"{tag}: opção alimentar inválida: {', '.join(sorted(d - diets))}")
        if len(d) != len(r["dietary_options"]):
            errors.append(f"{tag}: opção alimentar repetida")
        if "vegana" in d and "vegetariana" not in d:
            errors.append(f"{tag}: combinação inválida: vegana sem vegetariana")
        if r["cuisine"] == "vegetariana" and "vegetariana" not in d:
            errors.append(f"{tag}: culinária vegetariana sem opção vegetariana")

        # Ambientes
        a = set(r["ambiences"])
        if not a:
            errors.append(f"{tag}: sem ambiente")
        if a - ambs:
            errors.append(f"{tag}: ambiente inválido: {', '.join(sorted(a - ambs))}")
        for x, y in ref["incompatible_ambiences"]:
            if x in a and y in a:
                errors.append(f"{tag}: ambientes contraditórios: {x} e {y}")

        # Capacidade, avaliação, disponibilidade
        if r["capacity"] < 2:
            errors.append(f"{tag}: capacidade menor que 2")
        if not (1.0 <= r["rating"] <= 5.0):
            errors.append(f"{tag}: avaliação fora de 1-5")
        if not (0.0 < r["availability_rate"] <= 1.0):
            errors.append(f"{tag}: availability_rate fora de (0, 1]")
        if r["is_fictional"] is not True:
            errors.append(f"{tag}: is_fictional precisa ser true")
        if r["simulated_benefit"] and "simulado" not in r["simulated_benefit"].lower():
            errors.append(f"{tag}: benefício precisa estar marcado como simulado")

        # Localização
        h = hoods.get(r["neighborhood"])
        if h is None:
            errors.append(f"{tag}: bairro desconhecido '{r['neighborhood']}'")
        else:
            dist = haversine_km(r["latitude"], r["longitude"], h["lat"], h["lng"])
            if dist > 1.5:
                errors.append(f"{tag}: coordenada a {dist:.1f} km do centro de {r['neighborhood']}")

        # Horários
        oh = r["opening_hours"]
        if set(oh) != set(days):
            errors.append(f"{tag}: horários precisam ter exatamente os dias {days}")
        else:
            open_days = 0
            for day, slots in oh.items():
                for s in slots:
                    if not HHMM.match(s):
                        errors.append(f"{tag}: horário inválido '{s}' em {day}")
                    elif s[:5] >= s[6:]:
                        errors.append(f"{tag}: horário {s} em {day} termina antes de começar")
                open_days += bool(slots)
            if open_days == 0:
                errors.append(f"{tag}: nunca abre")

    # Diversidade da base
    if len(restaurants) != 50:
        errors.append(f"base deveria ter 50 restaurantes, tem {len(restaurants)}")
    prices = [r.get("avg_price", 0) for r in restaurants]
    if prices and (min(prices) > 45 or max(prices) < 200):
        errors.append("base sem diversidade de preço (precisa ir de até R$ 45 a pelo menos R$ 200)")
    if len({r.get("cuisine") for r in restaurants}) < 12:
        errors.append("base com menos de 12 culinárias")
    if len({r.get("neighborhood") for r in restaurants}) < 10:
        errors.append("base com menos de 10 bairros")
    return errors


def main(path: str | None = None) -> int:
    ref = json.loads((HERE / "reference.json").read_text(encoding="utf-8"))
    seed_path = Path(path) if path else HERE / "restaurants_seed.json"
    restaurants = json.loads(seed_path.read_text(encoding="utf-8"))
    errors = validate(restaurants, ref)
    if errors:
        print(f"{len(errors)} problema(s) no seed:")
        for e in errors:
            print(" -", e)
        return 1
    prices = sorted(r["avg_price"] for r in restaurants)
    print(
        f"OK: {len(restaurants)} restaurantes, {len({r['cuisine'] for r in restaurants})} culinárias, "
        f"{len({r['neighborhood'] for r in restaurants})} bairros, preços de R$ {prices[0]} a R$ {prices[-1]}"
    )
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
