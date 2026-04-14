import asyncio
from typing import List, Tuple, AsyncGenerator, Optional
import aiohttp
import re


class AsyncStationPlayer:
    def __init__(self, stations: List[Tuple[str, str]]):
        self.stations = stations
        self.index = 0
        self.direction = 1
        self.event = asyncio.Event()
        self.session = aiohttp.ClientSession()

    async def fetch_small_content(self, url: str, max_bytes: int = 1024, timeout: int = 5) -> str:
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                resp.raise_for_status()
                data = b""
                async for chunk in resp.content.iter_chunked(256):
                    data += chunk
                    if len(data) > max_bytes:
                        break
                return data.decode("utf-8", errors="ignore")
        except Exception as e:
            return f"[ERROR] {e}"

    async def resolve_playlist(self, url: str, depth: int = 0) -> Optional[str]:
        """Resolve .pls or .m3u playlists recursively to find final stream URL"""
        if depth > 2:
            return None  # prevent infinite loops

        content = await self.fetch_small_content(url)
        if content.startswith("[ERROR]"):
            return None

        content = content.strip().lower()

        # Try to extract URL from .pls
        if url.endswith(".pls") or "file1=" in content:
            match = re.search(r"file1\s*=\s*(http[^\s]+)", content)
            if match:
                return await self.resolve_playlist(match.group(1), depth + 1)

        # Try to extract from .m3u
        elif url.endswith(".m3u") or url.endswith(".m3u8") or "#extm3u" in content:
            lines = [
                line.strip()
                for line in content.splitlines()
                if line.strip() and not line.startswith("#")
            ]
            if lines:
                return await self.resolve_playlist(lines[0], depth + 1)

        # If it's not a playlist or we've reached the final stream
        if any(ext in url for ext in [".mp3", ".aac", ".ogg", ".opus"]):
            return url

        return None

    async def validate(self, url: str) -> Optional[str]:
        final_url = await self.resolve_playlist(url)
        if final_url:
            return final_url
        return None

    def next(self):
        self.direction = 1
        self.event.set()

    def prev(self):
        self.direction = -1
        self.event.set()

    async def playable_stations(self) -> AsyncGenerator[Tuple[str, str], None]:
        while True:
            name, url = self.stations[self.index]

            resolved_url = await self.validate(url)
            if resolved_url:
                yield (name, resolved_url)
                await self.event.wait()
                self.event.clear()
                self.index = (self.index + self.direction) % len(self.stations)
            else:
                print(f"❌ Skipping invalid or unresolvable station: {name} ({url})")
                self.index = (self.index + self.direction) % len(self.stations)

    async def close(self):
        await self.session.close()
