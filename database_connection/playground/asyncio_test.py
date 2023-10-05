import aiohttp
import aiohttp.client_exceptions
import pynng
import json
import asyncio

async def api_worker(queue: asyncio.Queue):
    while True:
        data = await queue.get()
        print(f"Sending {data} to API")
        await asyncio.sleep(1)

async def test_worker(queue: asyncio.Queue):
    i = 0

    while True:
        await queue.put(f"Run: {i}")
        i += 1
        await asyncio.sleep(1)

if __name__ == "__main__":
    queue = asyncio.Queue()
    
    loop = asyncio.get_event_loop()
    api_worker = loop.create_task(api_worker(queue))
    test_worker = loop.create_task(test_worker(queue))
    loop.run_until_complete(asyncio.wait([api_worker, test_worker]))

    loop.run_forever()
