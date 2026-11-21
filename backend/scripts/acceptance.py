"""Roteiro dos 8 critérios de aceite do docx (Etapa 2, seção 6), contra qualquer cliente HTTP.

Roda no pytest (com o TestClient do FastAPI) e contra produção:
    python backend/scripts/acceptance.py https://<sua-api>.onrender.com
"""
from __future__ import annotations

import sys
import time
from datetime import date, timedelta

PEOPLE = [
    # (apelido, preferências) - o primeiro é quem organiza
    ("Lia", {"cuisines": ["italiana", "vegetariana"], "dietary_restrictions": ["vegetariana"],
             "ambiences": ["tranquilo"], "origin_neighborhood": "Pinheiros", "max_distance_km": 8}),
    ("Theo", {"cuisines": ["brasileira", "pizzaria"], "dietary_restrictions": ["sem_gluten"],
              "ambiences": ["casual", "ao_ar_livre"], "origin_neighborhood": "Vila Madalena", "max_distance_km": 10,
              "max_budget": 80}),
    ("Nina", {"cuisines": ["japonesa", "mexicana"], "dietary_restrictions": [], "ambiences": ["animado"],
              "origin_neighborhood": "Liberdade", "max_distance_km": 12}),
    ("Rafa", {"cuisines": ["hamburgueria", "brasileira"], "dietary_restrictions": [], "ambiences": ["casual"],
              "origin_neighborhood": "Perdizes", "max_distance_km": 10}),
]


def next_saturday(today: date | None = None) -> date:
    today = today or date.today()
    return today + timedelta(days=((5 - today.weekday()) % 7) or 7)


class Check:
    def __init__(self):
        self.results: list[dict] = []

    def record(self, n: int, title: str, ok: bool, detail: str):
        self.results.append({"criterion": n, "title": title, "ok": bool(ok), "detail": detail})
        return ok


def _ok(resp, *codes):
    if resp.status_code not in (codes or (200, 201)):
        raise AssertionError(f"{resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def run_acceptance(client, prefix: str = "") -> list[dict]:
    c = Check()
    H = lambda tok: {"X-Participant-Token": tok}  # noqa: E731

    # 1. Criar um encontro e receber um link compartilhável
    body = {"name": "Aceite automático", "event_date": next_saturday().isoformat(), "event_time": "20:00",
            "budget_per_person": 100, "party_size": 4, "neighborhood": "Pinheiros", "occasion": "jantar_amigos",
            "organizer_nickname": PEOPLE[0][0]}
    created = _ok(client.post(f"{prefix}/groups", json=body), 201)
    g, org_token = created["group"], created["organizer_token"]
    gid, code = g["id"], g["invite_code"]
    tokens = {PEOPLE[0][0]: created["identity"]["token"]}
    ids = {PEOPLE[0][0]: created["identity"]["participant_id"]}
    c.record(1, "Criar encontro e receber link compartilhável",
             len(code) == 8 and g["invite_url"].endswith(f"/entrar/{code}"),
             f"código {code}, link {g['invite_url']}")

    # 2. Entrar com pelo menos três participantes fictícios
    for nick, _ in PEOPLE[1:]:
        j = _ok(client.post(f"{prefix}/groups/join", json={"invite_code": code, "nickname": nick}), 201)
        tokens[nick], ids[nick] = j["identity"]["token"], j["identity"]["participant_id"]
    g = _ok(client.get(f"{prefix}/groups/{gid}", headers=H(tokens["Lia"])))
    c.record(2, "Entrar com pelo menos três participantes",
             g["counts"]["joined"] == 4, f"{g['counts']['joined']} participantes: "
             + ", ".join(p["nickname"] for p in g["participants"]))

    # 3. Preencher preferências diferentes
    blocked = client.post(f"{prefix}/groups/{gid}/match", headers=H(tokens["Lia"]))
    for nick, prefs in PEOPLE:
        _ok(client.put(f"{prefix}/participants/{ids[nick]}/preferences", json=prefs, headers=H(tokens[nick])))
    g = _ok(client.get(f"{prefix}/groups/{gid}", headers=H(tokens["Lia"])))
    c.record(3, "Preencher preferências diferentes",
             g["counts"]["answered"] == 4 and g["status"] == "match_disponivel" and blocked.status_code == 409,
             f"4 perfis salvos; antes disso o Match estava bloqueado ({blocked.status_code}); status agora: "
             f"{g['status_label']}")

    # 4. Gerar recomendações coerentes com as restrições
    t0 = time.perf_counter()
    m = _ok(client.post(f"{prefix}/groups/{gid}/match", headers=H(tokens["Lia"])))
    elapsed = time.perf_counter() - t0
    recs = m["recommendations"]
    required = {d for _, p in PEOPLE for d in p["dietary_restrictions"]}
    ceiling = min([100] + [p.get("max_budget") or 100 for _, p in PEOPLE])
    coherent = bool(recs) and all(required <= set(r["restaurant"]["dietary_options"])
                                  and r["restaurant"]["avg_price"] <= ceiling for r in recs)
    c.record(4, "Gerar recomendações coerentes com as restrições", coherent and len(recs) == 3,
             f"top 3 em {elapsed:.1f}s: " + "; ".join(
                 f"{r['restaurant']['name']} (R$ {r['restaurant']['avg_price']:.0f}, "
                 f"{', '.join(r['restaurant']['dietary_labels'])}, score {r['score']:.0f})" for r in recs)
             + f". Exigido: {', '.join(sorted(required))}; teto R$ {ceiling}.")

    # 5. Visualizar as justificativas de IA
    viewed = _ok(client.get(f"{prefix}/groups/{gid}/recommendations", headers=H(tokens["Nina"])))
    explained = all(len(r["explanation"]) > 40 and r["attention_point"] for r in viewed["recommendations"])
    sources = {r["explanation_source"] for r in viewed["recommendations"]}
    c.record(5, "Visualizar as justificativas de IA", explained,
             f"fonte: {', '.join(sorted(sources))}. Ex.: \"{viewed['recommendations'][0]['explanation'][:220]}\"")

    # 6. Votar e identificar o restaurante vencedor (com empate 2 x 2, decidido pelo score)
    r1, r2 = recs[0]["recommendation_id"], recs[1]["recommendation_id"]
    plan = {"Lia": r2, "Theo": r1, "Nina": r1, "Rafa": r2}
    for nick, rid in plan.items():
        _ok(client.post(f"{prefix}/groups/{gid}/votes", json={"recommendation_id": rid}, headers=H(tokens[nick])))
    # Lia muda o voto: deve atualizar, não duplicar
    res = _ok(client.post(f"{prefix}/groups/{gid}/votes", json={"recommendation_id": r1}, headers=H(tokens["Lia"])))
    res = _ok(client.post(f"{prefix}/groups/{gid}/votes", json={"recommendation_id": r2}, headers=H(tokens["Lia"])))
    closed = _ok(client.post(f"{prefix}/groups/{gid}/close-voting", headers={"X-Organizer-Token": org_token}))
    c.record(6, "Votar e identificar o restaurante vencedor",
             res["total_votes"] == 4 and closed["winner_recommendation_id"] == r1,
             f"{res['total_votes']} votos (Lia mudou o voto 2 vezes sem duplicar). {closed['decision_note']}")

    # 7. Confirmar uma reserva claramente identificada como simulada
    reservation = _ok(client.post(f"{prefix}/groups/{gid}/reservations", headers={"X-Organizer-Token": org_token}), 201)
    again = client.post(f"{prefix}/groups/{gid}/reservations", headers={"X-Organizer-Token": org_token})
    c.record(7, "Confirmar reserva identificada como simulada",
             reservation["is_simulated"] is True and reservation["label"] == "Reserva simulada"
             and again.status_code == 409,
             f"{reservation['label']} {reservation['confirmation_code']} em {reservation['restaurant']['name']}, "
             f"{reservation['booking_time']}, is_simulated={reservation['is_simulated']}; "
             f"segunda reserva recusada ({again.status_code})")
    _ok(client.post(f"{prefix}/reservations/{reservation['id']}/reviews",
                    json={"rating": 5, "comment": "Todo mundo saiu feliz."}, headers=H(tokens["Theo"])), 201)

    # 8. Reabrir o encontro e encontrar as informações persistidas
    g = _ok(client.get(f"{prefix}/groups/{gid}", headers=H(tokens["Theo"])))
    persisted = (g["status"] == "avaliado" and g["winner"]["recommendation_id"] == r1
                 and g["reservation"]["is_simulated"] and g["me"]["preferences"]["dietary_restrictions"] == ["sem_gluten"]
                 and g["me"]["vote_recommendation_id"] == r1 and g["reservation"]["my_review"]["rating"] == 5)
    c.record(8, "Reabrir o encontro e encontrar as informações persistidas", persisted,
             f"status {g['status_label']}; vencedor {g['winner']['restaurant']['name']}; reserva "
             f"{g['reservation']['confirmation_code']}; preferências, voto e avaliação de Theo recuperados")
    c.group_id = gid  # type: ignore[attr-defined]
    return c.results


def print_report(results: list[dict]) -> None:
    for r in results:
        print(f"[{'OK ' if r['ok'] else 'FALHOU'}] {r['criterion']}. {r['title']}\n      {r['detail']}")
    print(f"\n{sum(r['ok'] for r in results)}/{len(results)} critérios atendidos")


if __name__ == "__main__":
    import httpx

    sys.stdout.reconfigure(encoding="utf-8")
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
    with httpx.Client(base_url=base, timeout=90) as http:
        print("Acordando a API:", http.get("/health").json())
        results = run_acceptance(http)
    print_report(results)
    sys.exit(0 if all(r["ok"] for r in results) else 1)
