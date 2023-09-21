import tkinter as tk
import requests

# Colors
COOLGRAY = '#3B3730'
SAGE = '#9D9480'
NUDE = '#8C7460'
MONOBLACK = '#171717'
RED = '#58181F'
WHITE = '#FDFDFD'


class Window:
    def __init__(self):
        self.__root = tk.Tk()
        self.__root.wm_title("RAAI Database")
        self.__root.geometry("800x600")
        self.__root.resizable(False, False)
        self.__root.configure(bg=MONOBLACK)

        self.__driver_data = {}
        self.__driver_time_data = {}
        self.__convention_data = {}

        self.__setup_frames()

    def __setup_frames(self):
        self.__main_frame = tk.Frame(self.__root, bg=MONOBLACK)
        self.__main_frame.pack(fill=tk.BOTH, expand=True)

        self.__left_side = tk.Frame(self.__main_frame, bg=SAGE)
        self.__left_side.grid(row=0, column=0, sticky="nsew")

        self.__right_side = tk.Frame(self.__main_frame, bg=SAGE)
        self.__right_side.grid(row=0, column=1, sticky="nsew")

        self.__data_frame = tk.Frame(self.__right_side, bg=COOLGRAY)
        self.__data_frame.pack(fill=tk.BOTH, expand=True)

        self.__bottom_bar_frame = tk.Frame(self.__data_frame, bg=SAGE)
        self.__bottom_bar_frame.pack(side=tk.BOTTOM, fill=tk.X, expand=False)

        self.__data_frame.grid_rowconfigure(1, weight=1)

        self.__main_frame.grid_columnconfigure(0, weight=1)
        self.__main_frame.grid_columnconfigure(1, weight=1)
        self.__main_frame.grid_rowconfigure(0, weight=1)

    def __setup_buttons(self):
        self.__bottom_bar_frame = tk.Frame(self.__data_frame, bg=SAGE)
        self.__bottom_bar_frame.pack(side=tk.BOTTOM, fill=tk.X, expand=False)

        self.__data_frame.grid_rowconfigure(1, weight=1)

        button1 = tk.Button(self.__bottom_bar_frame, text="Button 1")
        button1.pack(side=tk.LEFT)

        button2 = tk.Button(self.__bottom_bar_frame, text="Button 2")
        button2.pack(side=tk.LEFT)

        button3 = tk.Button(self.__bottom_bar_frame, text="Button 3")
        button3.pack(side=tk.LEFT)

    def run(self):
        self.__root.update()
        while True:
            self.__root.update_idletasks()
            self.__root.update()
            # self.__update_data()
            # self.__update_buttons()


if __name__ == "__main__":
    window = Window()
    window.run()
