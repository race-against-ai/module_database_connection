import tkinter as tk
import requests


class Window:
    def __int__(self):
        self.__root = tk.Tk()
        self.__root.title("RAAI Database")
        self.__root.geometry("800x600")
        self.__root.resizable(False, False)
        self.__root.configure(bg="white")


