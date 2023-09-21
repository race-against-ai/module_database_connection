import asyncio

class TestClass:
    def __init__(self):
        self.__internet_available = False
        self.lock = asyncio.Lock()

    async def async_task(self):
        while True:
            async with self.lock:
                print(f"Internet available: {self.__internet_available}")
            await asyncio.sleep(1 / 3)  # Print 3 times a second

    async def toggle_internet_status(self):
        while True:
            async with self.lock:
                self.__internet_available = not self.__internet_available
            await asyncio.sleep(1)  # Toggle every second

    async def main_loop(self):
        await asyncio.gather(
            self.async_task(),
            self.toggle_internet_status()
        )

if __name__ == "__main__":
    test_instance = TestClass()

    asyncio.run(test_instance.main_loop())

