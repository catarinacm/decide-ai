"""Rate limiting por IP (slowapi). Limites mais baixos nas rotas que chamam a IA."""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=["240/minute"], enabled=settings.rate_limit_enabled)

AI_LIMIT = "10/minute"
MATCH_LIMIT = "12/minute"
CREATE_LIMIT = "20/minute"
DEMO_LIMIT = "10/minute"
JOIN_LIMIT = "30/minute"
