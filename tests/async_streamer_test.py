import asyncio
from streaming.async_streamer import AsyncStationPlayer

async def encoder_controller(player: AsyncStationPlayer):
    async for name, url in player.playable_stations():
        print(f"🎵 Now playing: {name} ({url})")

        # Simulate next track after a delay
        await asyncio.sleep(5)
        player.next()


# stations = [
#     ("Jazz FM", "http://example.com/good1.m3u"),
#     ("Broken Stream", "http://example.com/bad.pls"),
#     ("Rock Radio", "http://example.com/good2.m3u8"),
# ]

stations =  [
        ("ERROR station", "http://www.streamvortex.com:11300/stream.m3u.error"),
        ("WZIP", "http://www.streamvortex.com:11300/stream.m3u"),
        ("WKSU Public Radio", "http://stream.wksu.org/wksu1.mp3.128.m3u"),
        ("WCPN Public Radio", "http://audio1.ideastream.org/wcpn128.mp3.m3u")
]

async def main():
    player = AsyncStationPlayer(stations)
    try:
        await encoder_controller(player)
    finally:
        await player.close()

asyncio.run(main())
