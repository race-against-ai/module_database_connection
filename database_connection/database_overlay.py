import tkinter as tk
import pynng
import json

# Colors
COOLGRAY = '#3B3730'
SAGE = '#9D9480'
NUDE = '#8C7460'
MONOBLACK = '#171717'
RED = '#58181F'
WHITE = '#FDFDFD'
GREEN = '#2E8B57'
BLUE = '#1E90FF'
YELLOW = '#FFD700'
ORANGE = '#FFA500'
PURPLE = '#800080'
PINK = '#FFC0CB'
BROWN = '#A52A2A'
BLACK = '#000000'


# Errors
# Currently buttons can be spammed, needs to be fixed

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


class Window:
    def __init__(self):
        self.__root = tk.Tk()
        self.__root.wm_title("RAAI Database")
        self.__window_size = (800, 600)
        self.__root.geometry("800x600")
        self.__root.resizable(False, False)
        self.__root.configure(bg=MONOBLACK)

        self.__root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.__is_closed = False

        self.__driver_data = {}
        self.__driver_time_data = {}
        self.__convention_data = {}

        request_address = "ipc:///tmp/RAAI/connection_overlay.ipc"
        self.__request_socket = pynng.Req0()
        self.__request_socket.dial(request_address)

        self.__setup_frames()
        self.__setup_buttons()

    def __send_request(self, request: str) -> None:
        self.__request_socket.send(request.encode())
        print(f"Sent request: {request}")
        response = self.__request_socket.recv()
        print(f"Received response: {response.decode()}")

    def __setup_frames(self):
        root = self.__root
        self.__main_frame = tk.Frame(root, bg=MONOBLACK)
        self.__main_frame.pack(fill=tk.BOTH, expand=True)

        left_side_width = self.__window_size[0] * 0.3
        right_side_width = self.__window_size[0] * 0.7
        self.__left_side = tk.Frame(root, bg=NUDE,
                                    width=left_side_width,
                                    height=self.__window_size[1])
        self.__left_side.pack(side="left", fill=tk.Y, in_=self.__main_frame)

        self.__right_side = tk.Frame(root, bg=RED,
                                     width=right_side_width,
                                     height=self.__window_size[1])
        self.__right_side.pack(side="right", fill=tk.Y, in_=self.__main_frame)

        data_frame_height = self.__window_size[1]*(7/8)
        print(data_frame_height)
        self.__data_frame = tk.Frame(root, bg=GREEN,
                                     width=right_side_width,
                                     height=data_frame_height)
        self.__data_frame.pack(side=tk.TOP, fill=tk.X, in_=self.__right_side, anchor=tk.N)

        self.__bottom_bar_frame = tk.Frame(root, bg=RED,
                                           width=right_side_width,
                                           height=self.__window_size[1] - data_frame_height)
        self.__bottom_bar_frame.pack(side=tk.BOTTOM, in_=self.__right_side, anchor=tk.S,
                                     fill=tk.X)

    def __setup_buttons(self):
        # pass
        button1 = tk.Button(self.__bottom_bar_frame, text="Refresh",
                            command=lambda: self.__send_request("refresh"))
        button1.pack(side=tk.LEFT)

        button2 = tk.Button(self.__bottom_bar_frame, text="Reconnect",
                            command=lambda: self.__send_request("reconnect"))
        button2.pack(side=tk.LEFT)

        button3 = tk.Button(self.__bottom_bar_frame, text="Update",
                            command=lambda: self.__send_request("update"))
        button3.pack(side=tk.LEFT)

    def on_closing(self):
        # Function to handle window close event
        self.__is_closed = True
        self.__root.destroy()

    def run(self):
        self.__root.update()
        while not self.__is_closed:
            self.__root.update_idletasks()
            self.__root.update()


if __name__ == "__main__":
    window = Window()
    window.run()
