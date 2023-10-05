# Copyright (C) 2022 NG:ITL
# from database_connection.new_fake import FakeDataSender
# from database_connection.database_connection import DatabaseConnection
from database_connection.rest_api_connection import RestApiConnection

if __name__ == "__main__":
    # data_sender = DatabaseConnection("api_functions.json")
    # data_sender.start_non_threaded()
    # data_sender.start_async_tasks()

    data_sender = RestApiConnection("api_functions.json")
    data_sender.start()