"""Compatibility exports; shared rate limiting lives in app.core.rate_limit."""

from app.core.rate_limit import LOGIN_PER_ACCOUNT as LOGIN_PER_ACCOUNT
from app.core.rate_limit import LOGIN_PER_IP as LOGIN_PER_IP
from app.core.rate_limit import MAX_KEYS as MAX_KEYS
from app.core.rate_limit import REGISTER_ISSUE_PER_SUBJECT as REGISTER_ISSUE_PER_SUBJECT
from app.core.rate_limit import REGISTER_PER_IP as REGISTER_PER_IP
from app.core.rate_limit import REGISTER_PER_SUBJECT as REGISTER_PER_SUBJECT
from app.core.rate_limit import WINDOW_SECONDS as WINDOW_SECONDS
from app.core.rate_limit import Limit as Limit
from app.core.rate_limit import RateLimiter as RateLimiter
from app.core.rate_limit import limiter as limiter
