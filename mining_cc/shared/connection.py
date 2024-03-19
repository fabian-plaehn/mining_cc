import socket
import time


def connect_to_server(host, port):
    client_socket = socket.socket()  # instantiate
    while True:
        try:
            client_socket.connect((host, port))  # connect to the server
            print("successfully connected")
            break
        except:
            print("connection refused.. try again")
            time.sleep(2)
    client_socket.setblocking(False)
    return client_socket