import pynng

# Create a REP socket and listen on a specific address
server_socket = pynng.Rep0()
server_socket.listen("ipc:///tmp/RAAI/connection_overlay.ipc")

while True:
    try:
        request = server_socket.recv()
        print(f"Received request: {request.decode()}")

        # Process the request and generate a response
        response = f"Server received: {request.decode()}"

        # Send the response back to the client
        server_socket.send(response.encode())
    except KeyboardInterrupt:
        break

server_socket.close()
