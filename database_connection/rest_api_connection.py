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


def new_database_request(url: str, params: dict, method:str):
    """
    Database Request with on REST principle

    Args:
        url (str): The URL of the REST API endpoint.
        params (dict): The data to be sent with the request.
        method (str): The HTTP method to be used for the request.
    """
    allowed_methods = ["GET", "POST", "PUT", "DELETE"]
    if method in allowed_methods:
        try:
            response = requests.request(method, url, params=params)
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

    def __init__(self, config: str = "database_connection_config.json", localdev: bool = False) -> None:
        self.__program_running = True

        self.__config = json.load(open((resource_path() / config), "r"))
        
        # setting api url based on azure enviroment
        if not localdev:
            self.__api_url = self.__config["api_url"]
        else:
            self.__api_url = "http://localhost:7071/api/"

        # check if internet is available
        self.__internet_connection = is_internet_available()
        self.__api_queue = asyncio.Queue()
        self.__unsent_queue = asyncio.Queue()

        self.__unsent_data = {}
        self.__total_unsent_data = 0
        self.__best_times = {}

        # Dummy best Time Data if no internet is available
        self.__saved_lap_times = [
            {
                "id": "NONE",
                "sector1": 27.375,
                "sector2": 19.834,
                "sector3": 25.327,
                "time": 72.536,
                "driver_id": "34725692-6400-46ef-9114-9e0d54589c76",
                "convention_id": "1"
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
                "location": "Wolfsburg"
            }
        ]

        self.__existing_driver_ids = []
        self.__existing_convention_ids = []

        # Pynng Setup
        publisher_address = self.__config["pynng"]["publishers"]["data_publisher"]["address"]
        self.__data_publisher = pynng.Pub0()

        time_tracking_address = self.__config["pynng"]["subscribers"]["time_tracking"]["address"]
        time_tracking_topics_dict = self.__config["pynng"]["subscribers"]["time_tracking"]["topics"]

        self.__time_tracking_subscriber = pynng.Sub0()
        for topic in time_tracking_topics_dict:
            self.__time_tracking_subscriber.subscribe(topic)
        self.__time_tracking_subscriber.dial(time_tracking_address, block=False)

        connection_overlay_address = self.__config["pynng"]["requesters"]["connection_overlay"]["address"]
        self.__request_responder = pynng.Rep0()
        print(connection_overlay_address)
        self.__request_responder.listen(connection_overlay_address)
        self.__valid_requests = ["get_data", "get_data_by_id", "refresh", "reconnect", "help", "get_best_times"]
        print("Database connection initialized")

        # current drivers and conventions for testing
        self.__current_driver = None
        self.__current_convention = 1

        self.__current_lap = None
        self.__current_lap_valid = True
        # Refresh Entries on startup
        self.__handle_requests("refresh")
        print(self.__handle_requests("get_best_times"))
    
    def start(self):
        """Starts the RestApiConnection"""
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
                print("------! No Internet Connection")
            await asyncio.sleep(60*5)

    def __refresh_entries(self):
        """Requests all Drivers, Conventions and Laptimes from the API"""
        self.__get_laptimes()
        self.__get_drivers()
        self.__get_conventions()

    def __get_laptimes(self) -> None:
        """get top 30 laptimes from the API"""
        print("Getting Laptimes")
        # payload with the top 30 drivertimes sorted by laptime
        payload= {
            "sorted_by": "laptime",
            "limit": 30
        }
        
        full_url = self.__api_url + "drivertimes"
        response = new_database_request(full_url, payload, "GET")
        exising_ids = []
        exisiting_convention_ids = []
        if response != "Error":
            self.__saved_lap_times = []
            for entry in response:
                print(entry)
                if entry["driver_id"] not in exising_ids:
                    exising_ids.append(entry["driver_id"])
                if entry["convention_id"] not in exisiting_convention_ids:
                    exisiting_convention_ids.append(entry["convention_id"])

                laptime = {
                    "id": entry["drivertime_id"],
                    "sector1": entry["sector1"],
                    "sector2": entry["sector2"],
                    "sector3": entry["sector3"],
                    "time": entry["laptime"],
                    "driver_id": entry["driver_id"],
                    "convention_id": entry["convention_id"]

                }
                print(laptime, "\n")

                self.__saved_lap_times.append(entry)

            self.__existing_driver_ids = exising_ids
            self.__existing_convention_ids = exisiting_convention_ids

        else:
            print("------! Error getting laptimes")

    def __get_drivers(self) -> None:
        """Receive every driver appearing in the laptimes"""
        print("Getting Drivers")

        method = "GET"
        full_url = self.__api_url + "driver"
        # setting up payload for drivers

        for driver in self.__existing_driver_ids: 
            # response = database_request(url, payload, header, method)
            payload= {
                "id": driver
            }
            response = new_database_request(full_url, payload, "GET")
            if response != "Error":
                if response:
                    self.__saved_drivers = []
                    for entry in response:
                        self.__saved_drivers.append(entry)
                
            else:
                print("Error getting drivers")
                        
    def __get_conventions(self) -> None:
        """receive every convention appearing in the laptimes"""
        print("Getting Conventions")
        # url_suffix = self.__functions["MasterFunction"]["url"]
        # header = self.__functions["MasterFunction"]["header"]
        # url = self.__api_url + url_suffix
        method = "GET"
        full_url = self.__api_url + "convention"

        # setting up payload for conventions
        for convention in self.__existing_convention_ids:
            payload = {
                "id": convention
            }
            # response = database_request(url, payload, header, method)
            response = new_database_request(full_url, payload, "GET")
            if response != "Error":
                if response:
                    self.__save_conventions = []
                    for entry in response:
                        self.__save_conventions.append(entry)
            else:
                print("------! Error getting conventions")

    def __get_best_sectors(self) -> dict:
        """Requests best Sector and Laptimes from the API"""

        # setting up payload for best individual sector times
        full_url = self.__api_url + "drivertimes/bestsectors"
        request = new_database_request(full_url, {}, "GET")
        if request != "Error":
            return request
        else:
            return "Error"

    async def __pynng_responder(self):
        print("Pynng Responder started")
        while self.__program_running:
            msg = await self.__request_responder.arecv()
            request = msg.decode() 
            print(f"Received request: {request}")
            response = self.__handle_requests(request)
            print(f"Sending response:\n      {response}")
            await self.__request_responder.asend(response.encode())

    def __handle_requests(self, request: str) -> str:
        """Handles requests received via pynng"""
        data = None
        if ":" in request:
            # message = request.strip()
            message = request.split(":")
            print(message)
            request = message[0]
            data_str = message[1]
            try: 
                data_list = data_str.strip('[]').split(',')
                data_list = [f'"{entry.strip()}"' for entry in data_list]
                data_str =f"[{','.join(data_list)}]"
                data = json.loads(data_str)
                print(type(data), data)
            except json.decoder.JSONDecodeError:
                return "Error: Invalid Data Format"
            
        if request in self.__valid_requests:
            print(f"Handling request: {request}")
            try:
                if request == "get_data":
                    laptimes_dict, drivers_dict, conventions_dict = self.__prepare_data()
                    response = {
                        "internet_connection": self.__internet_connection,
                        "unsent_data": self.__unsent_data,
                        "current_driver": self.__current_driver,
                        "current_convention": self.__current_convention,
                        "current_lap": self.__current_lap,
                        "lap_times": laptimes_dict,
                        "drivers": drivers_dict,
                        "conventions": conventions_dict
                    }
                    return json.dumps(response)

                elif request == "get_data_by_id":
                    if data:
                        return json.dumps(data)
                    else:
                        return "Error: No Data Given"

                elif request == "get_best_times":
                    self.__best_times = self.__get_best_sectors()
                    return json.dumps(self.__best_times)

                elif request == "refresh":
                    if self.__internet_connection:
                        self.__refresh_entries()
                        response = self.__handle_requests("get_data")
                        return response
                    else:
                        return "No Internet Connection"

                elif request == "reconnect":
                    if is_internet_available():
                        self.__internet_connection = True
                        return "Reconnected to API"
                    else:
                        self.__internet_connection = False
                        return "No Internet Connection"

                elif request == "help":
                    return json.dumps(self.__valid_requests)

            except Exception as e:
                print(e)
                return "Error"

        else:
            print("Invalid Request")
            return "Invalid Request"

    def __prepare_data(self) -> tuple[dict, dict, dict]:
        """Prepares sorted data for visualisation"""

        sorted_lap_times: dict[str, dict] = sorted(self.__saved_lap_times, key=lambda item: item["laptime"])

        laptimes_dict = {str(i+1): item for i, item in enumerate(sorted_lap_times)}

        drivers_dict = {str(i+1): item for i, item in enumerate(self.__saved_drivers)}

        conventions_dict = {str(i+1):item for i, item in enumerate(self.__save_conventions)}

        return laptimes_dict, drivers_dict, conventions_dict

    async def __receive_time_tracking(self):
        """
        Handle Time Tracking Data, received via pynng.
        Sends the Received Data to the API if valid
        """
        while True:
            print("...")
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
                                "driver_id": self.__current_driver["id"],
                                "convention_id": self.__current_convention
                            }
                            payload = {
                                "method": "POST",
                                "table": "drivertimes",
                                "data": data
                            }

                            url = self.__api_url + "drivertime"
                            method = "POST"
                            if self.__current_driver["id"] is not None:
                                self.__api_queue.put((url, data, method))
                            
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
            url, data, method = await self.__api_queue.get()
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    if method == "POST":
                        async with session.post(url, data=data) as resp:
                            await resp.text()
                            if resp.status != 200:
                                print(f"Error sending data to API: {resp.status}")
                                identifier = str(time.time())
                                payload = {identifier: {
                                    "url": url,
                                    "data": data,
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
                self.__api_queue.put((url, data, method))
                    