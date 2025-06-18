import time
import requests

from typing import Iterator, Iterable, Tuple

def is_m3u_playlist(content):
    return "#EXTM3U" in content or content.strip().lower().endswith('.mp3') or 'http' in content

def fetch_url_head(url, max_bytes=1024, timeout=5):
    try:
        with requests.get(url, timeout=timeout, stream=True) as r:
            r.raise_for_status()
            data = b""
            for chunk in r.iter_content(chunk_size=256):
                data += chunk
                if len(data) > max_bytes:
                    break
            return data.decode('utf-8', errors='ignore')
    except Exception as e:
        return f"[ERROR] {e}"

def fetch_and_print_playlists(data):
    for location, info in data.items():
        print(f"\nLocation: {location}")
        for entry in info.get("urls", []):
            name = entry.get("name")
            url = entry.get("url")
            print(f"\nChecking '{name}' - {url}")
            content = fetch_url_head(url)
            if content.startswith("[ERROR]"):
                print(content)
            elif is_m3u_playlist(content):
                print(f"Playlist content for '{name}':\n{content.strip()}")
            else:
                print(f"'{name}' does not appear to be a playlist.")

def fetch_and_clean_stations(data: Iterable[dict]) -> Iterator[Tuple[str, str]]:
    for entry in data:
        name = entry.get("name")
        url = entry.get("url")
        content = fetch_url_head(url)
        if content.startswith("[ERROR]"):
            continue
        elif is_m3u_playlist(content):
            # print("is_m3u_playlist...")
            yield (name, content.strip())
        else:
            # Placeholder
            pass


# Example input
data = {
    "Akron,US-OH": {
        "coords": {"n": 41.0798, "e": -81.5219},
        "urls": [
            {
                "name": "WZIP",
                "url": "http://www.streamvortex.com:11300/stream.m3u"
            },
            {
                "name": "WKSU Public Radio",
                "url": "http://stream.wksu.org/wksu1.mp3.128.m3u"
            },
            {
                "name": "WCPN Public Radio",
                "url": "http://audio1.ideastream.org/wcpn128.mp3.m3u"
            }
        ]
    }
}

stations =  [
    {
        "name": "ERROR station",
        "url": "http://www.streamvortex.com:11300/stream.m3u.error"
    },
    {
        "name": "WZIP",
        "url": "http://www.streamvortex.com:11300/stream.m3u"
    },
    {
        "name": "WKSU Public Radio",
        "url": "http://stream.wksu.org/wksu1.mp3.128.m3u"
    },
    {
        "name": "WCPN Public Radio",
        "url": "http://audio1.ideastream.org/wcpn128.mp3.m3u"
    }
]

fetch_and_print_playlists(data)

clean_stations = fetch_and_clean_stations(stations)
# next = next(clean_station)
for station in clean_stations:
    start_t = time.monotonic()
    print(f"{station} {time.monotonic() - start_t}") 
