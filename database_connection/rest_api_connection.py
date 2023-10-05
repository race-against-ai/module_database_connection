import json
import asyncio
import aiohttp
import aiohttp.client_exceptions
import requests
import pynng
import os
import sys
import time

from pathlib import Path

def is_internet_available():
    """Check if an internet connection is available"""
    try:
        # Attempt to send an HTTP GET request to a well-known website
        response = requests.get("https://raaidatabaseapi.azurewebsites.net", timeout=5)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return True  # Internet connection is available
    except requests.RequestException:
        pass
    return False  # Internet connection is not available


def resource_path() -> Path:
    base_path = getattr(sys, "_MEIPASS", os.getcwd())
    return Path(base_path)


def send_data(pub: pynng.Pub0, payload: dict, topic: str = " ", p_print: bool = True) -> None:
    """
    publishes data via pynng

    :param pub: publisher
    :param payload: data that should be sent in form of a dictionary
    :param topic: the topic under which the data should be published  (e.g. "lap_time:")
    :param p_print: if true, the message that is sent will be printed out. Standard is set to true
    """
    json_data = json.dumps(payload)
    topic = topic + " "
    msg = topic + json_data
    if p_print is True:
        print(f"data send: {msg}")
    pub.send(msg.encode())


def remove_pynng_topic_mod(data, sign: str = " ") -> list[str]:
    """
    removes the topic from data that got received via pynng and returns a variable that stores the content

    :param data: date received from subscriber
    :param sign: last digit from the topic
    """
    decoded_data: str = data.decode()
    i = decoded_data.find(sign)
    topic = decoded_data[0:i]
    decoded_data = decoded_data[i + 1:]
    return [decoded_data, topic]


def database_request(url: str, data: dict, header: str, method: str) -> dict|str:
    """
    Sends a request to a database REST API endpoint.

    Args:
        url (str): The URL of the REST API endpoint.
        data (dict): The data to be sent with the request.
        header (str): The header to be sent with the request.
        method (str): The HTTP method to be used for the request.

    Returns:
        dict or str: The response from the REST API endpoint, or an error message if the request failed.
    """
    
    print("Processing Database Request")
    if method in ["GET", "POST"]:
        try:
            response = requests.post(url, json=data, headers=header)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            print(err)
            return "Error"
    
    else:
        return "Error"


async def publishing_api_worker(queue: asyncio.Queue, unsent_queue: asyncio.Queue):
    timeout = aiohttp.ClientTimeout(total=2, connect=None)
    print("API Worker started")

    while True:
        url, data, header, method = await queue.get()
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                if method == "POST":
                    async with session.post(url, json=data, headers=header) as resp:
                        await resp.text()
                        if resp.status != 200:
                            print(f"Error sending data to API: {resp.status}")
                            identifier = str(time.time())
                            payload = {identifier: {
                                "url": url,
                                "data": data,
                                "header": header,
                                "method": method
                            }}

                            await unsent_queue.put(payload)

                        else:
                            print(f"Data sent to API: {data}")
                
                else:
                    print("Invalid method")

            except aiohttp.client_exceptions.ClientConnectorError:
                print("Error connecting to API")
            except asyncio.exceptions.TimeoutError:
                print("Error connecting to API")


class RestApiConnection:

    def __init__(self, functions: str = "functions.json") -> None:
        self.__program_running = True
        self.__functions = json.load(open((resource_path() / functions), "r"))
        self.__config = json.load(open((resource_path() / "database_connection_config.json"), "r"))
        self.__api_url = self.__config["api_url"]

        self.__internet_connection = is_internet_available()
        self.__api_queue = asyncio.Queue()
        self.__unsent_queue = asyncio.Queue()

        self.__unsent_data = {}
        self.__total_unsent_data = 0
        self.__saved_lap_times = [
            {
                "id": "NONE",
                "name": "JOHN DRIVER",
                "sector1": 27.375,
                "sector2": 19.834,
                "sector3": 25.327,
                "time": 72.536,
                "convention": "familienfest"
            }
        ]
        self.__saved_drivers = [
            {
                "id": "34725692-6400-46ef-9114-9e0d54589c76",
                "name": "Joachim Kalle",
                "email": "None"
            }
        ]
        self.__save_conventions = [
            {
                "id": "1",
                "name": "Familienfest",
                "start_time": "2021-09-01 12:00:00",
                "end_time": "2021-09-01 18:00:00"
            }
        ]

        self.__existing_driver_ids = []
        self.__existing_convention_ids = []

        publisher_address = self.__config["pynng"]["publishers"]["data_publisher"]["address"]
        self.__data_publisher = pynng.Pub0()

        time_tracking_address = self.__config["pynng"]["subscribers"]["time_tracking"]["address"]
        time_tracking_topics = self.__config["pynng"]["subscribers"]["time_tracking"]["topics"]
        self.__time_tracking_subscriber = pynng.Sub0()

        connection_overlay_address = self.__config["pynng"]["requesters"]["connection_overlay"]["address"]
        self.__request_responder = pynng.Rep0()
        self.__request_responder.listen(connection_overlay_address)
        self.__valid_requests = ["get_data", "get_data_by_id", "refresh", "reconnect", "help"]
        print("Database connection initialized")

        self.__current_driver = None
        self.__current_convention = 2

        self.__current_lap = None
        self.__current_lap_valid = True
    
    def start(self):
        loop = asyncio.get_event_loop()
        responder_task = loop.create_task(self.__pynng_responder())
        time_tracker_task = loop.create_task(self.__receive_time_tracking())
        test_task = loop.create_task(self.__check_for_internet_connection())

        loop.run_until_complete(asyncio.wait([responder_task, time_tracker_task, test_task]))
        loop.run_forever() 

    async def __check_for_internet_connection(self):
        while True:
            self.__internet_connection = is_internet_available()
            if self.__internet_connection:
                print("Internet Connection established")
            else:
                print("No Internet Connection")
            await asyncio.sleep(60*5)

    async def __pynng_responder(self):
        print("Pynng Responder started")
        while self.__program_running:
            msg = await self.__request_responder.arecv()
            request = msg.decode() 
            print(f"Received request: {request}")
            if request in self.__valid_requests:
                try:
                    if request == "get_data":
                        laptimes_dict, drivers_dict, conventions_dict = self.__prepare_data()
                        response = json.dumps({
                            "internet_connection": self.__internet_connection,
                            "unsent_data": self.__unsent_data,
                            "current_driver": self.__current_driver,
                            "current_convention": self.__current_convention,
                            "current_lap": self.__current_lap,
                            "lap_times": laptimes_dict,
                            "drivers": drivers_dict,
                            "conventions": conventions_dict
                        })
                        await self.__request_responder.asend(response.encode())

                    elif request == "get_data_by_id":
                        await self.__request_responder.asend(json.dumps(self.__fake_data[self.__current_driver]).encode())

                    elif request == "refresh":
                        if self.__internet_connection:
                            response = "Refreshed"
                            await self.__request_responder.asend(response.encode())

                        else:
                            await self.__request_responder.asend("No Internet Connection".encode())

                    elif request == "reconnect":
                        if is_internet_available():
                            self.__internet_connection = True
                            await self.__request_responder.asend("Reconnected to API".encode())
                        else:
                            self.__internet_connection = False

                    elif request == "help":
                        await self.__request_responder.asend(json.dumps(self.__valid_requests).encode())

                except Exception as e:
                    print(e)
                    await self.__request_responder.asend("Error")

            else:
                print("Invalid Request")
                await self.__request_responder.asend("Invalid Request")

    def __prepare_data(self) -> tuple[dict, dict, dict]:
        sorted_lap_times: dict[str, dict] = sorted(self.__saved_lap_times, key=lambda item: item["time"])
        laptimes_dict = {str(i+1): item for i, item in enumerate(sorted_lap_times)}

        drivers_dict = {str(i+1): item for i, item in enumerate(self.__saved_drivers)}
        conventions_dict = {self.__save_conventions[i]["id"]: item for i, item in enumerate(self.__save_conventions)}
        return laptimes_dict, drivers_dict, conventions_dict

    async def __receive_time_tracking(self):
        """
        Handle Time Tracking Data, received via pynng.
        Sends the Received Data to the API if valid
        """
        while True:
            msg = await self.__time_tracking_subscriber.arecv()
            if msg is not None:
                data_recv = remove_pynng_topic_mod(msg)
                topic: str = data_recv[1]
                data: dict = data_recv[0]
                print(f"received topic: {topic}")

                if topic == "lap_start":
                    print("lap_start")
                    print(data, "\n")
                    if self.__current_lap is None:
                        self.__reset_lap()
                    else:
                        url_suffix = self.__functions["PostDriverTime"]["url"]
                        header = self.__functions["PostDriverTime"]["header"]
                        method = self.__functions["PostDriverTime"]["method"]
                        url = self.__url_prefix + url_suffix
                        for entry, value in self.__current_lap.items():
                            if value is None:
                                self.__current_lap_valid = False
                                break
                        if self.__current_lap_valid and self.__current_driver:
                            data = {
                                "id": self.__current_driver["id"],
                                "lap_time": self.__current_lap["time"],
                                "sector1": self.__current_lap["sector1"],
                                "sector2": self.__current_lap["sector2"],
                                "sector3": self.__current_lap["sector3"],
                                "convention": self.__current_convention
                            }
                            if self.__current_driver["id"] is not None:
                                self.__api_queue.put((url, data, header, method))
                            
                            else:
                                print("No Driver ID")

                        self.__reset_lap()

                elif topic == "sector_finished":
                    print(data, "\n")
                    sector = data["sector_number"]
                    lap_time = data["sector_time"]
                    valid = data["sector_valid"]
                    if self.__current_lap_valid:
                        if valid:
                            self.__current_lap[f"sector{sector}"] = lap_time

                elif topic == "lap_finished":
                    print("lap_finished")
                    lap_time = data["lap_time"]
                    valid = data["lap_valid"]
                    if valid:
                        self.__current_lap["time"] = lap_time

    async def __publishing_api_worker(self):
        timeout = aiohttp.ClientTimeout(total=2, connect=None)
        print("API Worker started")

        while True:
            url, data, header, method = await self.__api_queue.get()
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    if method == "POST":
                        async with session.post(url, json=data, headers=header) as resp:
                            await resp.text()
                            if resp.status != 200:
                                print(f"Error sending data to API: {resp.status}")
                                identifier = str(time.time())
                                payload = {identifier: {
                                    "url": url,
                                    "data": data,
                                    "header": header,
                                    "method": method
                                }}
                                await self.__unsent_queue.put(payload)

                            else:
                                print(f"Data sent to API: {data}")

                except aiohttp.client_exceptions.ClientConnectorError:
                    print("Error connecting to API")
                except asyncio.exceptions.TimeoutError:
                    print("Error connecting to API")

    async def __no_internet_api_worker(self):
        print("No Internet API Worker started")
        while True:
            payload = await self.__unsent_queue.get()
            identifier = payload.keys()[0]
            data = payload[identifier]["data"]
            url = payload[identifier]["url"]
            header = payload[identifier]["header"]
            method = payload[identifier]["method"]

            if self.__internet_connection is False:
                if len(self.__unsent_data) <= 30:
                    self.__unsent_data[identifier] = payload[identifier]
                    print(f"Amount of Data in unsent_data: {len(self.__unsent_data)}")
                
                else:
                    self.__internet_connection = is_internet_available()
                    if not os.path.isfile("unsent_data.json"):
                        json_data = json.load(open("unsent_data.json", "w"))
                    json.dump(self.__unsent_data, open("unsent_data.json", "a"))
                
            else:
                self.__api_queue.put((url, data, header, method))
                    