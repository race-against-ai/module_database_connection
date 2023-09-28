# Copyright (C) 2022 NG:ITL
# from database_connection.new_fake import FakeDataSender
from database_connection.database_connection import DatabaseConnection

if __name__ == "__main__":
    data_sender = DatabaseConnection("api_functions.json")
    data_sender.start()