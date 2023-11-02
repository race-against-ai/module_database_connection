import pynng
import random
import json
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

# Create a Publisher socket
pub_sock = pynng.Pub0()
pub_sock.dial("ipc:///tmp/RAAI/lap_times.ipc")

lap_times = []
for i in range(2):
    random_lap_time = random.randint(1, 100)

    sector_payload = {
        "current_driver": "test_driver",
        "sector_number": i+1,
        "sector_time": random_lap_time,
        "sector_valid": True,
        "type": "yellow",
    }

    sector_topic = "sector_finished"
    send_data(pub=pub_sock, payload=sector_payload, topic=sector_topic)
    lap_times.append(random_lap_time)


    if i == 2:
        complete_lap_time = sum(lap_times)
        lap_payload = {
        "current_driver": "test_driver",
        "lap_time": complete_lap_time,
        "lap_valid": True,
        "type": "yellow",
        }
        topic = "lap_finished"

        send_data(pub=pub_sock, payload=lap_payload, topic="lap_time")

        lap_start_topic = "lap_start"
        send_data(pub=pub_sock, payload={}, topic=lap_start_topic)
    
    sleep(2)
    
    


