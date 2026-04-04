from slowapi import Limiter
from auth import rate_limit_key_func

# We use the custom JWT-based key_func defined in auth.py
limiter = Limiter(key_func=rate_limit_key_func)
