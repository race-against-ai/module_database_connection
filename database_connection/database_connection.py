from __future__ import annotations

import json
import requests
import pynng
import os
import sys
from pathlib import Path


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

        publisher_address = self.__config["pynng"]["publishers"]["data_publisher"]["address"]
        self.__data_publisher = pynng.Pub0(listen=publisher_address)

        time_tracking_address = self.__config["pynng"]["subscribers"]["time_tracking"]["address"]
        time_tracking_topics = self.__config["pynng"]["subscribers"]["time_tracking"]["topics"]
        self.__time_tracking_subscriber = pynng.Sub0()
        for entry in time_tracking_topics:
            self.__time_tracking_subscriber.subscribe(entry)
        self.__time_tracking_subscriber.dial(time_tracking_address, block=False)

        self.__current_driver = {
            "id": None,
            "name": None
        }
        self.__current_lap = None
        self.__current_lap_valid = True

    def receive_time_tracking(self):
        data_recv = receive_data_mod(self.__time_tracking_subscriber)
        if data_recv is not None:
            topic: str = data_recv[1]
            data: dict = data_recv[0]
            print(f"received topic: {topic}")

            if topic == "lap_start":
                print("lap_start")
                print(data, "\n")
                if self.__current_lap is None:
                    self.__current_lap = {
                        "sector1": None,
                        "sector2": None,
                        "sector3": None,
                        "time": None
                    }

            elif topic == "sector_finished":
                print(data, "\n")
                sector = data["sector_number"]
                time = data["sector_time"]
                valid = data["sector_valid"]
                if self.__current_lap_valid:
                    if valid:
                        self.__current_lap[f"sector{sector}"] = time
                    else:
                        self.__current_lap_valid = valid
            elif topic == "lap_finished":
                print("lap_finished")
