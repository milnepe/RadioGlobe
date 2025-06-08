import asyncio
from apositional_encoders import Positional_Encoders


async def print_encoder_values(encoder: Positional_Encoders):
    while True:
        lat, lon = encoder.get_readings()
        print(f"Latitude: {lat}, Longitude: {lon}")
        await asyncio.sleep(1)

async def main():
    encoder = Positional_Encoders()
    # Start the encoder loop and the printing task
    await asyncio.gather(
        encoder.run(),
        print_encoder_values(encoder)
    )

if __name__ == "__main__":
    asyncio.run(main())