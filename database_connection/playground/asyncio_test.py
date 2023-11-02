import aiohttp
import aiohttp.client_exceptions
import pynng
import json
import asyncio

async def api_worker(queue: asyncio.Queue):
    while True:
        data = await queue.get()
        print(f"Sending {data} to API")
        await asyncio.sleep(3)

async def test_worker(queue: asyncio.Queue):
    i = 0

    while True:
        print(f"Putting {i} in queue")
        await queue.put(f"Run: {i}")
        i += 1
        await asyncio.sleep(1)
        if i == 10:
            break

async def receive_pynng():
    try:
        sub_sock = pynng.Sub0()
        sub_sock.dial("ipc:///tmp/RAAI/lap_times.ipc")
        sub_sock.subscribe("")

        while True:
            message = await sub_sock.arecv()
            print(f"Received message: {message.decode()}")
    except pynng.exceptions.DialAddrError:
        print("Could not connect to the server, please check if the server is running")
        exit(1)

async def online_api_worker():
    url = "http://localhost:7071/api/drivers"
    params = {
        "sorted_by": "createdate"
    }
    while True:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params) as response:
                    print(await response.text())
            except aiohttp.client_exceptions.ClientConnectorError:
                print("Could not connect to the server, please check if the server is running")
                exit(1)
        await asyncio.sleep(3)

if __name__ == "__main__":
    queue = asyncio.Queue()
    
    loop = asyncio.get_event_loop()
    api_worker = loop.create_task(api_worker(queue))
    test_worker = loop.create_task(test_worker(queue))
    # pynng_worker = loop.create_task(receive_pynng())
    online_api_worker = loop.create_task(online_api_worker())
    loop.run_until_complete(asyncio.wait([api_worker, test_worker, online_api_worker]))

    loop.run_forever()
