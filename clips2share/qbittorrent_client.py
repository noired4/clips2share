from requests import Session
from urllib.parse import urlparse

class QBittorrentClient:
    def __init__(self, api_url: str):
        parsed = urlparse(api_url)
        if not parsed.scheme or not parsed.hostname or not parsed.username or not parsed.password:
            raise ValueError(f"Invalid qbittorrent_url format: {api_url}. Expected format: http://user:pass@host:port")

        self.base_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        self.session = Session()

        login_resp = self.session.post(f"{self.base_url}/api/v2/auth/login", data={
            "username": parsed.username,
            "password": parsed.password
        })
        login_resp.raise_for_status()

        if login_resp.text.strip() != "Ok.":
            raise RuntimeError(f"Can't connect to qBittorrent: {login_resp.text.strip()}")

        print("qBittorrent API login successful.")

    def send_torrent(self, torrent_bytes, name, category, savepath):
        response = self.session.post(f"{self.base_url}/api/v2/torrents/add", files={
            "torrents": (name, torrent_bytes)
        }, data={
            "savepath": savepath,
            "category": category,
            "autoTMM": "false"
        })

        response.raise_for_status()
        return response
    