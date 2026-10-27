import json
import time
from base64 import urlsafe_b64decode
from collections.abc import Awaitable, Callable
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, NamedTuple

from asmrmanager.logger import logger

DEFAULT_API_URL = "https://api.asmr-200.com/api/"


class AuthenticationError(RuntimeError):
    pass


class LoginCache(NamedTuple):
    token: str
    recommender_uuid: str
    expire_time: int
    username: str


class LoginAuth:
    def __init__(
        self, name: str, password: str, base_url: str, cache_dir: Path
    ) -> None:
        self.name = name
        self.password = password
        self.base_url = base_url
        cache_key = sha256(f"{base_url}\0{name}".encode()).hexdigest()
        self.cache_path = cache_dir / "auth" / f"{cache_key}.json"
        self.legacy_cache_path = cache_dir / "login_cache.json"
        self.headers = {
            "User-Agent": "ASMRManager (https://github.com/slqy123/ASMRManager)",
        }
        self.recommender_uuid = ""

    def _read_cache(self, path: Path) -> LoginCache | None:
        try:
            with path.open(encoding="utf-8") as file:
                cache = LoginCache(**json.load(file))
        except FileNotFoundError:
            return None
        except (OSError, TypeError, ValueError):
            logger.warning("Failed to load login cache: %s", path)
            return None
        if (
            cache.username == self.name
            and isinstance(cache.token, str)
            and cache.token
            and isinstance(cache.recommender_uuid, str)
            and cache.recommender_uuid
            and isinstance(cache.expire_time, int)
            and cache.expire_time > time.time() + 60
        ):
            return cache
        return None

    def _load_cache(self) -> LoginCache | None:
        cache = self._read_cache(self.cache_path)
        if cache is None and self.base_url == DEFAULT_API_URL:
            cache = self._read_cache(self.legacy_cache_path)
            if cache is not None:
                self._save_cache(cache)
        return cache

    def _save_cache(self, cache: LoginCache) -> None:
        temporary_path = None
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.cache_path.parent,
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(cache._asdict(), file)
            temporary_path.replace(self.cache_path)
        except OSError:
            logger.warning("Failed to save login cache: %s", self.cache_path)
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)

    def _parse_login_response(self, response: Any) -> LoginCache:
        try:
            token = response["token"]
            recommender_uuid = response["user"]["recommenderUuid"]
            if not (
                isinstance(token, str)
                and isinstance(recommender_uuid, str)
                and recommender_uuid
            ):
                raise ValueError
            parts = token.split(".")
            if len(parts) != 3:
                raise ValueError
            payload = parts[1]
            expire_time = json.loads(
                urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            )["exp"]
            if not (
                isinstance(expire_time, int) and expire_time > time.time()
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise AuthenticationError("Invalid login response.") from None
        return LoginCache(token, recommender_uuid, expire_time, self.name)

    async def login(
        self, request: Callable[[dict[str, str]], Awaitable[Any]]
    ) -> None:
        self.headers.pop("Authorization", None)
        self.recommender_uuid = ""
        cache = self._load_cache()
        if cache is None:
            logger.info("Requesting new login token.")
            response = await request(
                {"name": self.name, "password": self.password}
            )
            cache = self._parse_login_response(response)
            self._save_cache(cache)
        else:
            logger.debug("Using cached login token.")
        self.headers["Authorization"] = f"Bearer {cache.token}"
        self.recommender_uuid = cache.recommender_uuid
