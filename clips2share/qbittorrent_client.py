from requests import Session
from urllib.parse import urlparse

_session = None
_base_url = None

def configure(api_url: str):
    global _base_url, _session
    parsed = urlparse(api_url)
    if not parsed.scheme or not parsed.hostname or not parsed.username or not parsed.password:
        raise ValueError(f"Invalid qbittorrent_url format: {api_url}. Expected format: http://user:pass@host:port")

    _base_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    username = parsed.username
    password = parsed.password
    _session = Session()

    login_resp = _session.post(f"{_base_url}/api/v2/auth/login", data={
        "username": username,
        "password": password
    })

    login_resp.raise_for_status()

    if login_resp.text.strip() != "Ok.":
        raise RuntimeError(f"Can't connect to qBittorrent: {login_resp.text.strip()}")

    print("qBittorrent API login successful.")

# Category must now have a path
# Use category paths in Manual Mode should be turned off
def send_torrent(torrent_bytes, name, category, savepath):
    if not _session or not _base_url:
        raise RuntimeError("qBittorrent client is not configured.")

    response = _session.post(f"{_base_url}/api/v2/torrents/add", files={
        "torrents": (name, torrent_bytes)
    }, data={
        "savepath": savepath,
        "category": category,
        "autoTMM": "false"
    })

    response.raise_for_status()
    return response
