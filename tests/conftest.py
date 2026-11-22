import os
import sys
from pathlib import Path

# Ambiente de teste, definido antes de importar o app: banco em memória, IA desligada, sem rate limit.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["ADMIN_TOKEN"] = "chave-de-teste"
os.environ["FRONTEND_URL"] = "https://decide-ai.vercel.app"
os.environ["CORS_ORIGINS"] = "http://localhost:5173,https://decide-ai.vercel.app"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "data"))

import pytest  # noqa: E402


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.database import Base, SessionLocal, engine
    from app.main import app
    from app.services import ai_service
    from app.services.match_service import reset_catalog_cache, seed_restaurants

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_restaurants(db)
    reset_catalog_cache()
    ai_service._cache.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    from app.database import SessionLocal
    with SessionLocal() as s:
        yield s


ADMIN = {"X-Admin-Token": "chave-de-teste"}


class Flow:
    """Atalhos para montar grupos nos testes."""

    def __init__(self, client):
        self.c = client
        self.tokens: dict[str, str] = {}
        self.ids: dict[str, str] = {}
        self.group_id = None
        self.code = None
        self.org = None

    def H(self, nick):
        return {"X-Participant-Token": self.tokens[nick]}

    @property
    def O(self):
        return {"X-Organizer-Token": self.org}

    def create(self, organizer="Ana", **overrides):
        from datetime import date, timedelta
        d = date.today() + timedelta(days=((5 - date.today().weekday()) % 7) or 7)
        body = {"name": "Teste", "event_date": d.isoformat(), "event_time": "20:00", "budget_per_person": 100,
                "party_size": 3, "neighborhood": "Pinheiros", "organizer_nickname": organizer, **overrides}
        r = self.c.post("/groups", json=body)
        assert r.status_code == 201, r.text
        data = r.json()
        self.group_id, self.code, self.org = data["group"]["id"], data["group"]["invite_code"], data["organizer_token"]
        self.tokens[organizer], self.ids[organizer] = data["identity"]["token"], data["identity"]["participant_id"]
        return data

    def join(self, nick, **kw):
        r = self.c.post("/groups/join", json={"invite_code": self.code, "nickname": nick, **kw})
        assert r.status_code == 201, r.text
        ident = r.json()["identity"]
        self.tokens[nick], self.ids[nick] = ident["token"], ident["participant_id"]
        return ident

    def prefs(self, nick, expect=200, **kw):
        body = {"cuisines": [], "dietary_restrictions": [], "ambiences": [], "origin_neighborhood": "Pinheiros",
                "max_distance_km": 10, **kw}
        r = self.c.put(f"/participants/{self.ids[nick]}/preferences", json=body, headers=self.H(nick))
        assert r.status_code == expect, r.text
        return r.json()

    def group(self, nick=None):
        nick = nick or next(iter(self.tokens))
        r = self.c.get(f"/groups/{self.group_id}", headers=self.H(nick))
        assert r.status_code == 200, r.text
        return r.json()

    def match(self, nick=None, expect=200, force=False, organizer=False):
        nick = nick or next(iter(self.tokens))
        headers = {**self.H(nick), **(self.O if organizer else {})}
        r = self.c.post(f"/groups/{self.group_id}/match", json={"force": force}, headers=headers)
        assert r.status_code == expect, r.text
        return r.json()

    def vote(self, nick, rec_id, expect=200):
        r = self.c.post(f"/groups/{self.group_id}/votes", json={"recommendation_id": rec_id}, headers=self.H(nick))
        assert r.status_code == expect, r.text
        return r.json()

    def close(self, expect=200):
        r = self.c.post(f"/groups/{self.group_id}/close-voting", headers=self.O)
        assert r.status_code == expect, r.text
        return r.json()

    def ready(self, names=("Ana", "Bia", "Caio")):
        """Grupo de 3 com preferências simples, pronto para o Match."""
        self.create(organizer=names[0], party_size=len(names))
        for n in names[1:]:
            self.join(n)
        for n in names:
            self.prefs(n)
        return self


@pytest.fixture
def flow(client):
    return Flow(client)
