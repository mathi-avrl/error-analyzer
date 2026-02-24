import jwt
import requests
import datetime
import logging
import orjson

JWKS_URL = 'https://studio.avrlgeneration.com/jwt/certs/jwks.json'
_memory_cache = {}

def verify_token_with_jwks(token: str) -> tuple[bool, any]:
    try:
        jwks_keys = get_public_keys()
        header = jwt.get_unverified_header(token)

        status, payload = False, None
        if "kid" not in header:
            for key in jwks_keys:
                status, payload = decode_token(token, key)

                if not status:
                    continue
                break
        else:
            kid = header.get("kid")
            key = next((k for k in jwks_keys if k["kid"] == kid), None)

            if not key:
                return False, "No matching key found in JWKS"

            status, payload = decode_token(token, key)


        return status, payload
    except jwt.ExpiredSignatureError:
        return False, "Token has expired"
    except jwt.InvalidTokenError:
        return False, "Invalid token"
    except Exception as e:
        logging.error(f"Error verifying token with JWKS: {e}")
        return False, "Failed to verify token"

def get_public_keys() -> list[dict]:
    global _memory_cache
    public_keys = []
    current_time_in_utc = datetime.datetime.now(datetime.UTC)

    # 1. Check Memory Cache
    if _memory_cache and (current_time_in_utc - _memory_cache.get("cached_at", datetime.datetime.min.replace(tzinfo=datetime.UTC))).days < 1:
        return _memory_cache.get("keys", [])

    # 2. Fetch from JWKS URL directly
    try:
        response_jwks = requests.get(JWKS_URL, timeout=30)

        if response_jwks.status_code != 200:
            logging.error(f"Failed to fetch JWKS keys from {JWKS_URL}: {response_jwks.status_code}")
            return public_keys

        try:
            response_jwks_data = orjson.loads(response_jwks.text)
        except Exception as e:
            logging.error(f"Failed to parse JWKS response from {JWKS_URL} as JSON: {e}")
            return public_keys

        if 'keys' not in response_jwks_data:
            logging.error(f"No keys found in JWKS response from {JWKS_URL}")
            return public_keys

        public_keys = response_jwks_data.get("keys")

        if not isinstance(public_keys, list) or len(public_keys) == 0:
            logging.error(f"Invalid keys format in JWKS response from {JWKS_URL} "f"(should have been a list of keys) & keys returned had length={len(public_keys)}")
            return public_keys
        
        _memory_cache = {
            "keys": public_keys,
            "cached_at": current_time_in_utc
        }

    except Exception as e:
        logging.exception(f"Error while fetching JWKS keys: {e}", exc_info=True)
        return []

    return public_keys

def decode_token(token, key):
    try:
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
        payload = jwt.decode(token, public_key, algorithms=["RS256"])
        if payload.get("expires_at") < int(datetime.datetime.now(datetime.timezone.utc).timestamp()):
            raise jwt.ExpiredSignatureError
        return True, payload
    except jwt.InvalidTokenError:
        return False, "Invalid token"
