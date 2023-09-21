import json
import requests
import pynng
import os
import sys
from pathlib import Path
import threading
import queue
import time
import asyncio


def is_internet_available():
    try:
        # Attempt to send an HTTP GET request to a well-known website
        response = requests.get("http://www.google.com", timeout=5)
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
        data = json.loads(data[0])
        return [data, data[1]]

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
    def __init__(self, functions: str = "functions.json"):

        self.__functions = json.load(open(functions, "r"))
        self.__config = json.load(open((resource_path() / "database_connection_config.json"), "r"))
        self.__url_prefix = "https://raaidatabaseapi.azurewebsites.net/api/"

        self.__internet_connection = is_internet_available()
        self.__api_queue = queue.Queue()
        self.__unsent_data = {}

        self.__asyncio_loop_running = False

        self.__api_worker_thread = threading.Thread(target=self.__api_worker)
        self.__api_worker_thread.deamon = True

        self.__unsent_data_thread = threading.Thread(target=self.__send_unsent_data_worker)
        self.__unsent_data_thread.deamon = True

        publisher_address = self.__config["pynng"]["publishers"]["data_publisher"]["address"]
        self.__data_publisher = pynng.Pub0(listen=publisher_address)

        connection_overlay_address = self.__config["pynng"]["requesters"]["connection_overlay"]["address"]
        self.__request_responder= pynng.Rep0()
        self.__request_responder.listen(connection_overlay_address)

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
        self.__api_worker_thread.start()
        self.__asyncio_loop_running = True
        asyncio.run(self.__receive_request())
        while True:
            if self.__unsent_data:
                self.__unsent_data_thread.start()
            self.__receive_time_tracking()

    async def __receive_request(self):
        while self.__asyncio_loop_running:
            request = self.__request_responder.recv()

            response = f"Server received: {request.decode()}"

            # Send the response back to the client
            self.__request_responder.send(response.encode())

    def __assign_new_driver(self, driver_id: int, driver_name: str):
        self.__current_driver["id"] = driver_id
        self.__current_driver["name"] = driver_name

    def __change_convention(self, convention_id: int):
        self.__current_convention = convention_id

    def __reset_lap(self):
        self.__current_lap = {
            "sector1": None,
            "sector2": None,
            "sector3": None,
            "time": None
        }
        self.__current_lap_valid = True

    def __receive_time_tracking(self):
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
                            self.__api_queue.put((url, data, header, method))

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

    def __api_worker(self):
        while True:
            try:
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

    def __send_unsent_data_worker(self):
        if is_internet_available():
            for identifier, data in self.__unsent_data.items():
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
                    break

        else:
            print("No internet connection available")
