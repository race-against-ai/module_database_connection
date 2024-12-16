import pynng

# Create a REQ socket and dial the server's address
client_socket = pynng.Req0()
client_socket.dial("ipc:///tmp/RAAI/connection_overlay.ipc")

while True:
    try:
        message = input("Enter a message to send to the server (or 'exit' to quit): ")

        if message.lower() == 'exit':
            break

        # Send the message as a request to the server
        client_socket.send(message.encode())

        # Wait for and print the response from the server
        response = client_socket.recv()
        print(f"Received response: {response.decode()}")
    except KeyboardInterrupt:
        break

client_socket.close()