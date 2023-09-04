import pynng
import random
import uuid
from pathlib import Path
import os
import sys
import json


def resource_path() -> Path:
    base_path = getattr(sys, "_MEIPASS", os.getcwd())
    return Path(base_path)


def read_settings(filepath) -> dict:
    if os.path.isfile(filepath):
        with open(filepath, 'r') as f:
            file = json.load(f)

        return file

    else:
        raise FileNotFoundError


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


class FakeDataSender:
    """A Fake Data Sender to Simulate an actual Connection to the Database"""
    def __init__(self):
        self.__config = read_settings(resource_path() / "database_connection_config.json")
        self.__current_driver = None
        self.__current_lap_valid = True
        self.__driver_placings = {}
        self.__new_entries = []
        self.__fake_data = {"drivers": {}}
        conventions = ["IAA", "Braunschweig", "Congress-Park"]
        for i in range(50):
            i += 1
            driver = f"driver-{i}"
            # print(driver)
            driver_id = str(uuid.uuid4())
            sector1 = round(i * 10.2 + 0.123, 3)
            sector2 = round(i * (8.0 + float(f"0.0{i}")) + 0.456, 3)
            sector3 = round(i * 12 + 0.789, 3)
            time = round(sector1 + sector2 + sector3, 3)
            # print(time)
            random_number = random.randint(0, 2)
            place = conventions[random_number]

            self.__fake_data["drivers"][i] = {
                "id": driver_id,
                "name": driver,
                "sector1": sector1,
                "sector2": sector2,
                "sector3": sector3,
                "time": time,
                "convention": place
            }

        publisher_address = self.__config["pynng"]["publishers"]["data_publisher"]["address"]
        self.__data_publisher = pynng.Pub0(listen=publisher_address)

        time_tracking_address = self.__config["pynng"]["subscribers"]["time_tracking"]["address"]
        time_tracking_topics = self.__config["pynng"]["subscribers"]["time_tracking"]["topics"]
        self.__time_tracking_subscriber = pynng.Sub0()
        for entry in time_tracking_topics:
            self.__time_tracking_subscriber.subscribe(entry)
        self.__time_tracking_subscriber.dial(time_tracking_address, block=False)

        self.__randomize_times()
        self.__sort_driver_by_time()
        self.__dump_database()

    def run(self):
        while True:
            self.__receive_time_tracking()

    def __assign_new_driver(self):
        """
        Change the current driver for the database.
        In the future this should be doable with reading a QR-Code and pulling it from the Database.
        Currently just creates a placeholder driver
        """
        placeholder_driver = {
            "id": "34725692-6400-46ef-9114-9e0d54589c76",
            "name": "John Driver",
            "sector1": None,
            "sector2": None,
            "sector3": None,
            "time": None,
            "convention": "wolfsburg"
        }
        self.__current_driver = placeholder_driver

    def __receive_time_tracking(self):
        """
        Function to receive information from the time tracking component
        """
        data = receive_data_mod(self.__time_tracking_subscriber, block_state=False)
        if data:
            topic: str = data[1]
            info: dict = data[0]
            print(f"received topic: {topic}")

            match topic:
                case "lap_start":
                    print("received lap start info")
                    # msg looks like this:{
                    # "sector_1_best_time": 9.87,
                    # "sector_2_best_time": 3.08,
                    # "sector_3_best_time": 5.53,
                    # "lap_best_time": 19.48
                    # }
                    # When this signal is received we should save the current driver to a file
                    print(info, "\n")
                    if self.__current_driver is None:
                        self.__assign_new_driver()
                    self.__current_lap_valid = True

                case "sector_finished":
                    print("sector was finished")
                    # msg looks like this: {
                    # "sector_number": p_sector: int,
                    # "sector_time": p_time: float,
                    # "sector_valid": p_valid: bool,
                    # "type":  purple, green or yellow: str}
                    print(info, "\n")
                    sector = info["sector_number"]
                    time = info["sector_time"]
                    valid = info["sector_valid"]
                    if self.__current_lap_valid:
                        if valid:
                            self.__current_driver[f"sector{sector}"] = time
                        else:
                            self.__current_lap_valid = valid

                case "lap_finished":
                    print("lap was finished")
                    # lap is: {
                    # lap_time: p_time: float,
                    # "lap_valid: p_valid: bool,
                    # "type": purple, green or yellow
                    # }
                    print(info, "\n")
                    time = info["lap_time"]
                    if self.__current_lap_valid:
                        self.__current_driver["time"] = time
                    self.__receive_new_entry()
                    self.__new_entries.append(self.__current_driver)
                    self.__assign_new_driver()

    def __send_best_times(self) -> dict:
        print(f"sending top 20")
        top_20_drivers = dict(list(self.__fake_data["drivers"].items())[:20])
        return top_20_drivers

    def __receive_new_entry(self):
        print("adding Data to Database")
        placing = 51
        while placing in list(self.__fake_data["drivers"].keys()):
            placing += 1
            print(placing)
        print("finished")
        if placing not in list(self.__fake_data["drivers"].keys()):
            self.__fake_data["drivers"][placing] = self.__current_driver
            self.__sort_driver_by_time()
            self.__dump_database()
        else:
            print(f"{placing} already in database")

    def __dump_database(self) -> dict:
        with open("fake_database_entries.json", "w") as f:
            data = json.dumps(self.__fake_data, indent=4)
            f.write(data)

        return {"database": "dumped"}

    def __randomize_times(self):
        print("Randomizing Driver Times")
        for driver in self.__fake_data["drivers"]:
            sector1 = round(random.uniform(10, 100), 3)
            sector2 = round(random.uniform(10, 100), 3)
            sector3 = round(random.uniform(10, 100), 3)
            time = round(sector1 + sector2 + sector3, 3)
            self.__fake_data["drivers"][driver]["sector1"] = sector1
            self.__fake_data["drivers"][driver]["sector2"] = sector2
            self.__fake_data["drivers"][driver]["sector3"] = sector3
            self.__fake_data["drivers"][driver]["time"] = time
        self.__sort_driver_by_time()

    def __sort_driver_by_time(self):
        print("sorting Drivers by Time")
        sorted_drivers = dict(sorted(
            self.__fake_data["drivers"].items(),
            key=lambda item: item[1]["time"],
        ))
        new_database = {}
        i = 0
        for entry, values in sorted_drivers.items():
            i += 1
            new_database[i] = values
            self.__driver_placings[values["id"]] = i
        print(self.__driver_placings)
        self.__fake_data["drivers"] = new_database
        print(sorted_drivers)
