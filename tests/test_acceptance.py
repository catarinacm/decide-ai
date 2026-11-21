"""Teste ponta a ponta da API: os 8 critérios de aceite do docx, sem intervenção."""
from scripts.acceptance import run_acceptance


def test_oito_criterios_de_aceite(client):
    results = run_acceptance(client)
    assert [r["criterion"] for r in results] == list(range(1, 9))
    failed = [f"{r['criterion']}. {r['title']}: {r['detail']}" for r in results if not r["ok"]]
    assert not failed, "\n".join(failed)


def test_dados_sobrevivem_a_reinicio_do_app(client):
    """Critério 8 também depois de reiniciar o servidor: um TestClient novo lê o mesmo banco."""
    from fastapi.testclient import TestClient
    from app.main import app

    results = run_acceptance(client)
    assert all(r["ok"] for r in results)
    with TestClient(app) as fresh:
        m = fresh.get("/metrics").json()
        assert m["main_metric"]["numerator"] == 1
