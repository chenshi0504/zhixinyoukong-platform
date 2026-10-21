import os
from urllib.parse import urlparse

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import settings

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_WARN_DISABLED = False


def should_verify_cloud_ssl(base_url: str = "") -> bool:
    env_value = os.environ.get("CLOUD_API_VERIFY_SSL", "").strip().lower()
    if env_value:
        return env_value not in {"0", "false", "no", "off"}

    config_value = getattr(settings, "CLOUD_API_VERIFY_SSL", True)
    if not config_value:
        return False

    target_url = (base_url or settings.CLOUD_API_URL or "").strip()
    if not target_url:
        return bool(config_value)

    parsed = urlparse(target_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme.lower() == "https" and hostname in _LOCAL_HOSTS:
        return False
    return bool(config_value)


def create_cloud_session(retries: int = 0, backoff: float = 0.0, base_url: str = "") -> requests.Session:
    global _WARN_DISABLED

    session = requests.Session()
    if retries > 0:
        retry = Retry(
            total=retries,
            backoff_factor=backoff,
            status_forcelist=[502, 503, 504],
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

    verify = should_verify_cloud_ssl(base_url)
    session.verify = verify
    if not verify and not _WARN_DISABLED:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        _WARN_DISABLED = True
    return session
