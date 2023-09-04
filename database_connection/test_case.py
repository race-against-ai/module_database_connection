import pynng
import json
import select
from time import sleep


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


def receive_data(sub: pynng.Sub0) -> list[dict, str]:
    """
    receives data via pynng and returns a variable that stores the content

    :param sub: subscriber
    :param timer: timeout timer for max waiting time for new signal
    """
    try:
        msg = sub.recv(block=False)
        data = remove_pynng_topic(msg)
        data = json.loads(data[0])
        return [data, data[1]]

    except:
        return None


def remove_pynng_topic(data, sign: str = " ") -> list[str]:
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


ultimate_driver = {
    "1": {
        "id": "my own",
        "name": "driver-44",
        "sector1": 22.536,
        "sector2": 23.058,
        "sector3": 14.793,
        "time": 60.387,
        "convention": "Braunschweig"
    }
}


publisher = pynng.Pub0(listen="ipc:///tmp/RAAI/lap_times.ipc")
info = {
    "update": False,
    "best_times": True,
    "single_driver": 21,
    "help": False,
    "append": "haha funny"
}
#
# signal = {
#     "hello": "hi"
# }
#
# send_data(payload=signal, topic="database", pub=publisher, p_print=True)
# sleep(1)
subscriber = pynng.Sub0()
subscriber.subscribe("time_tracking")
subscriber.dial("ipc:///tmp/RAAI/database_connection.ipc", block=False)

subscriber_dict = {subscriber.recv_fd: subscriber}
inputs = [subscriber.recv_fd]

i = 0
sector = 1
while True:
    if i == 50:
        print("change sector value")
        sector += 1
        if sector > 3:
            sector = 1

    send_data(payload=info, topic="database", pub=publisher, p_print=True)

    i += 1
    sleep(0.5)

