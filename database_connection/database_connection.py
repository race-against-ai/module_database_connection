import json
import requests
import pynng
import asyncio
import os
import sys
from pathlib import Path
import threading
import queue
import time


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


def send_request(url: str, data: dict, headers: dict = None, method: str = "POST"):
    if method == "POST":
        return requests.post(url, data=data, headers=headers)
    elif method == "GET":
        return requests.get(url, data=data, headers=headers)
    elif method == "PUT":
        return requests.put(url, data=data, headers=headers)
    elif method == "DELETE":
        return requests.delete(url, data=data, headers=headers)
    else:
        raise ValueError("Invalid method")


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


def receive_data_mod(sub: pynng.Sub0, block_state: bool = True) -> list[dict | str] | None:
    """
    receives data via pynng and returns a variable that stores the content,
    modified to also show the topic used

    :param sub: subscriber
    :param block_state: Signal if Process should be Blocked until message is received
    """
    try:
        msg = sub.recv(block=False)
        data = remove_pynng_topic_mod(msg)
        info = json.loads(data[0])
        return [info, data[1]]

    except pynng.TryAgain:
        return None


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

   
class DatabaseConnection:
    """
    A Connection to the Database API,
    Handles Requests to visualize Data and sends Data to the API
    """
    def __init__(self, functions: str = "functions.json"):
        self._program_running = True

        self.__thread_lock = asyncio.Lock()
        self.__functions = json.load(open(functions, "r"))
        self.__config = json.load(open((resource_path() / "database_connection_config.json"), "r"))
        self.__url_prefix = "https://raaidatabaseapi.azurewebsites.net/api/"

        self.__internet_connection = is_internet_available()
        self.__api_queue = asyncio.Queue()
        self.__stop_event = threading.Event()
        self.__unsent_data = {}

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

        # self.__api_worker_thread = threading.Thread(target=self.__api_worker)
        # self.__api_worker_thread.deamon = True

        # self.__unsent_data_thread = threading.Thread(target=self.__send_unsent_data_worker)
        # self.__unsent_data_thread.deamon = True

        # self.__request_receiver_thread = threading.Thread(target=self.__request_receiver_worker)
        # self.__request_receiver_thread.deamon = True

        publisher_address = self.__config["pynng"]["publishers"]["data_publisher"]["address"]
        self.__data_publisher = pynng.Pub0(listen=publisher_address)

        connection_overlay_address = self.__config["pynng"]["requesters"]["connection_overlay"]["address"]
        self.__request_responder = pynng.Rep0()
        self.__request_responder.listen(connection_overlay_address)
        self.__valid_requests = ["get_data", "get_data_by_id", "refresh", "reconnect"]
        print("Database connection initialized")

        time_tracking_address = self.__config["pynng"]["subscribers"]["time_tracking"]["address"]
        time_tracking_topics = self.__config["pynng"]["subscribers"]["time_tracking"]["topics"]
        self.__time_tracking_subscriber = pynng.Sub0()
        for entry in time_tracking_topics:
            self.__time_tracking_subscriber.subscribe(entry)
        self.__time_tracking_subscriber.dial(time_tracking_address, block=False)

        self.__current_driver = {}
        self.__current_convention = 2

        self.__current_lap = None
        self.__current_lap_valid = True

    def start(self):
        try: 
            self.__start_api_worker_thread()
            self.__request_receiver_thread.start()
            while self._program_running:
                if self.__unsent_data and not self.__unsent_data_thread.is_alive():
                    self.__unsent_data_thread.start()
                self.__receive_time_tracking()
        except KeyboardInterrupt:
            print("KeyboardInterrupt")
            self.stop()
        self._program_running = False
        
        print("done")
    
    async def start_async(self):
        await asyncio.gather(
            self.__api_worker(),
            self.__request_receiver_worker(),
            self.__send_unsent_data_worker(),
            self.__main_loop()
        )
    
    def start_async_tasks(self):
        asyncio.run(self.start_async())

    async def __main_loop(self):
        print("Starting Database Connection")
        while self.get_program_running():
            async with self.__thread_lock:
                self.__receive_time_tracking()

    def start_non_threaded(self):
        print("Starting Database Connection")
        while self._program_running:
            try:
                self.__receive_time_tracking(threaded=False)
                self.__request_receiver_wroker_non_threaded()
                if self.__unsent_data:
                    self.__send_unsent_data_worker_non_threaded()
            except KeyboardInterrupt:
                print("KeyboardInterrupt")
                break
        print("Goodbye")

    def stop(self):
        self.__stop_event.set() 

    def __request_receiver_wroker_non_threaded(self):
        try:
            request = self.__request_responder.recv(block=False)
            if request is not None:
                print(f"Received request: {request.decode()}")
                request = request.decode()
                if request in self.__valid_requests:
                    if request == "refresh":
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
                        self.__request_responder.send(response.encode('utf-8'))
                
                    else:
                        response = "Not Implemented Yet"
                        self.__request_responder.send(response.encode())

                else:
                    response = "Invalid request"
                    self.__request_responder.send(response.encode())

        except pynng.TryAgain:
            pass

    async def __request_receiver_worker(self):
        """
        Thread for Handling Requests from the Connection Overlay
        """
        print("Request receiver started")
        while self.get_program_running():
            async with self.__thread_lock:
                print("Request receiver running")
                if self.__stop_event.is_set():
                    return
                try:
                    request = self.__request_responder.recv(block=False)
                    if request is not None:
                        print(f"Received request: {request.decode()}")
                        request = request.decode()
                        if request in self.__valid_requests:
                            if request == "refresh":
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
                                self.__request_responder.send(response.encode('utf-8'))
                        
                        else:
                            response = "Invalid request"
                            self.__request_responder.send(response.encode())

                except pynng.TryAgain:
                    pass

    def __prepare_data(self) -> tuple[dict, dict, dict]:
        sorted_lap_times: dict[str, dict] = sorted(self.__saved_lap_times, key=lambda item: item["time"])
        laptimes_dict = {str(i+1): item for i, item in enumerate(sorted_lap_times)}

        drivers_dict = {str(i+1): item for i, item in enumerate(self.__saved_drivers)}
        conventions_dict = {self.__save_conventions[i]["id"]: item for i, item in enumerate(self.__save_conventions)}
        return laptimes_dict, drivers_dict, conventions_dict

    def get_program_running(self) -> bool:
        return self._program_running

    def __assign_new_driver(self, driver_id: int, driver_name: str):
        """
        Asign new current driver to handle lap times for the API
        """
        self.__current_driver["id"] = driver_id
        self.__current_driver["name"] = driver_name

    def __change_convention(self, convention_id: int):
        self.__current_convention = convention_id

    def __reset_lap(self):
        """Reset Current Lap"""
        self.__current_lap = {
            "sector1": None,
            "sector2": None,
            "sector3": None,
            "time": None
        }
        self.__current_lap_valid = True

    def __receive_time_tracking(self, threaded:bool = True):
        """
        Handle Time Tracking Data, received via pynng.
        Sends the Received Data to the API if valid
        """
        data_recv = receive_data_mod(self.__time_tracking_subscriber)
        if data_recv is not None:
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
                            if threaded:
                                self.__api_queue.put((url, data, header, method))
                            else:
                                self.__api_worker_non_threaded(url, data, header, method)

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

    def __retry_internet_connection(self):
        if not self.__internet_connection:
            self.__internet_connection = is_internet_available()

    def __start_api_worker_thread(self):
        self.__api_worker_thread.start()

    def __stop_api_worker_thread(self):
        self._program_running = False
        self.__api_queue.put(None)
        self.__api_worker_thread.join()

    def __api_worker_non_threaded(self, url: str, data: dict, headers: dict, method: str):
        try:
            response = send_request(url, data, headers, method)

            if self.__internet_connection:
                response = send_request(url, data, headers, method)
                if response.status_code == 200:
                    print(f"API request successful: {response.status_code}")

                else:
                    print(f"API request failed: {response.status_code}")
                    print(f"                    {response.text}")
            else:
                identifier = str(time.time())
                self.__unsent_data[identifier] = {
                    "url": url,
                    "data": data,
                    "headers": headers,
                    "method": method
                }
                print(f"API request failed: {response.status_code}")
                print(f"                    {response.text}")
                print("Data saved for later transmission")

        except Exception as e:
            print(e)
            print("Error while sending API request")

    async def __api_worker(self):
        """
        API Worker Thread, handles API requests seperately from the main thread,
        to avoid blocking the main thread
        """
        print("API worker started")
        while self.get_program_running():
            async with self.__thread_lock:
                if not self.__api_queue.empty():
                    try:
                        request = self.__api_queue.get()
                        if request is None:
                            break

                        else:
                            url, data, headers, method = self.__api_queue.get()

                            response = send_request(url, data, headers, method)

                            if self.__internet_connection:
                                response = send_request(url, data, headers, method)
                                if response.status_code == 200:
                                    print(f"API request successful: {response.status_code}")

                                else:
                                    print(f"API request failed: {response.status_code}")
                                    print(f"                    {response.text}")
                            else:
                                identifier = str(time.time())
                                self.__unsent_data[identifier] = {
                                    "url": url,
                                    "data": data,
                                    "headers": headers,
                                    "method": method
                                }

                                print(f"API request failed: {response.status_code}")
                                print(f"                    {response.text}")
                                print("Data saved for later transmission")

                            self.__api_queue.task_done()

                    except Exception as e:
                        print(e)
                        print("Error while sending API request")

        print("API worker stopped")

    def __save_unsent_data(self):
        """Save Unsent Data in the Case of forced Shutdowns"""
        filename = f"unsent_data_{time.time()}"
        i = 0
        if os.path.exists(filename):
            while os.path.exists(filename):
                new_filename = f"{filename}_{i}"
                i += 1
            
        json.dump(self.__unsent_data, open("filename.json", "w"))

    def __send_unsent_data_worker_non_threaded(self):
        print("Sending unsent data")
        if self.__unsent_data and self.__internet_connection:
            for identifier, data in self.__unsent_data.items():
                if self.__stop_event.is_set():
                    return
                url = data["url"]
                data = data["data"]
                headers = data["headers"]
                method = data["method"]

                response = send_request(url, data, headers, method)

                if response.status_code == 200:
                    print(f"API request successful: {response.status_code}")
                    del self.__unsent_data[identifier]

                else:
                    print(f"API request failed: {response.status_code}")
                    print(f"                    {response.text}")
                    self.__internet_connection = False
                    break
        
        elif not self.__internet_connection:
            if not is_internet_available():
                print("No internet connection available")
            else:
                self.__internet_connection = True
                print("Internet connection available")

    async def __send_unsent_data_worker(self):
        print("Sending unsent data")
        """
        Thread for sending unsent data to the API in the case of a lost Internet Connection
        """
        async with self.__thread_lock:
            if self.__stop_event.is_set():
                self.__save_unsent_data()
                return
            if self.__unsent_data and self.__internet_connection:
                for identifier, data in self.__unsent_data.items():
                    if self.__stop_event.is_set():
                        return
                    url = data["url"]
                    data = data["data"]
                    headers = data["headers"]
                    method = data["method"]

                    response = send_request(url, data, headers, method)

                    if response.status_code == 200:
                        print(f"API request successful: {response.status_code}")
                        del self.__unsent_data[identifier]

                    else:
                        print(f"API request failed: {response.status_code}")
                        print(f"                    {response.text}")
                        self.__internet_connection = False
                        break
            
            elif not self.__internet_connection:
                if not is_internet_available():
                    print("No internet connection available")
                    await asyncio.sleep(60*5)
                else:
                    self.__internet_connection = True
                    print("Internet connection available")
                    await asyncio.sleep(5)

                
