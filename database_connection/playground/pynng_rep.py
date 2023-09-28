import pynng
import json


# Create a REP socket and listen on a specific address
server_socket = pynng.Rep0()
server_socket.listen("ipc:///tmp/RAAI/connection_overlay.ipc")

internet_connection = True
unsent_data = {
    "1":{
        "id": "NONE",
        "name": "JOHN DRIVER",
        "sector1": 27.375,
        "sector2": 19.834,
        "sector3": 25.327,
        "time": 72.536,
        "convention": "familienfest"
    }
}
current_driver = {
    "id": "34725692-6400-46ef-9114-9e0d54589c76",
    "name": "Joachim Kalle"
}

drivers = {
    "1": {
        "id": "34725692-6400-46ef-9114-9e0d54589c76",
        "name": "Joachim Kalle",
        "email": "None"
    },
    "2": {
        "id": "34725692-6400-46ef-9114-9e0d54589c76",
        "name": "Joachim Kalle",
        "email": "None"
    },
    "3": {
        "id": "34725692-6400-46ef-9114-9e0d54589c76",
        "name": "Joachim Kalle",
        "email": "gertrund-gisella@email.de"
    }
}

conventions = {
    "1": {
        "id": "1",
        "name": "Familienfest",
        "start_time": "2021-09-01 12:00:00",
        "end_time": "2021-09-01 18:00:00"
    }
}

current_convention = 2
current_lap = {
    "sector1": 100,
    "sector2": 200,
    "sector3": 300,
    "time": 600
}

data = json.load(open("./fake_database_entries.json", "r"))

def handle_request(request: str):
    print(f"Received request: {request}")
    if request == "refresh":
        response = json.dumps({
            "internet_connection": internet_connection,
            "unsent_data": unsent_data,
            "current_driver": current_driver,
            "current_convention": current_convention,
            "current_lap": current_lap,
            "lap_times": data["drivers"],
            "drivers": drivers,
            "conventions": conventions
        })
        # print(data["drivers"])
        print(conventions)
        server_socket.send(response.encode('utf-8'))
    else:
        response = "Invalid request"
        server_socket.send(response.encode())
    

while True:
    try:
        request = server_socket.recv()

        handle_request(request.decode())
    except KeyboardInterrupt:
        break

server_socket.close()
