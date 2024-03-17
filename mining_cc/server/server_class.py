import json
import os
from queue import Queue
import socket
import sys
import time
from datetime import datetime
from hashlib import md5

from mining_cc.shared.utils import logger

from mining_cc.shared.hashes import single_file_hash, dirhash

from mining_cc.shared.ProtoHeader import *
from mining_cc.server.src.connection import *
#from server.src.gui_class import Server_GUI
import shutil
from flask import Flask, request


server_folder_name = "Server_Folder"
client_file_name = "client_main.exe"
path_to_client_exe = f"{server_folder_name}/{client_file_name}"

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
        while True:
            self.check_new_connection(server_socket_clients)
            self.check_new_connection(server_socket_deamons)
            for conn, address, username in self.connection_list:
                request_typ, payload = receive_proto_block(conn)
                if request_typ == LoginRequest:
                    self.LoginRequest(conn, address, payload)
                elif request_typ == ExitRequest:
                    self.ExitRequest(conn, address, username)
                elif request_typ == Request_New_Client:
                    self.Request_New_Client(conn)
                elif request_typ == Request_Client_Hash:
                    logger("Request Client Hash")
                    self.Request_Client_Hash(conn)
                elif request_typ == Request_Miner_Hashes:
                    logger("Request Miner Hashes")
                    self.Request_Miner_Hashes(conn)
                elif request_typ == Request_New_Folder:
                    logger(f"Request New Folder: {payload.decode()}")
                    self.Request_New_Folder(conn, payload.decode())
                if username in self.config["Connections"]:
                    self.config["Connections"][username]["Last_seen"] = datetime.today().strftime("%Y/%m/%d %H:%M:%S")
        self.closing()

    def closing(self):
        print("Closing.. Save Config")
        with open("server_config.json", "w") as f:
            f.write(json.dumps(self.config, indent=2))
        sys.exit()
        
    def Request_Miner_Hashes(self, conn):
        hash_json = {}
        for file in os.listdir(server_folder_name):
            file_path = server_folder_name + "/" + file
            if not os.path.isdir(file_path):
                continue
            # is dir
            hash_d = dirhash(file_path, excluded_files=["config.json"])
            hash_json[file] = hash_d
            
        conn.send(send_miner_hashes(hash_json))
        
    def Request_Client_Hash(self, conn: socket.socket):
        if not os.path.isfile(path_to_client_exe):
            logger("client_main.exe not found")
            return 0
        hash = str(single_file_hash(path_to_client_exe))
        print(f"Client Hash: {hash}")
        conn.send(send_client_hash(hash))
    
    def Request_New_Folder(self, conn, folder_name):
        try:
            logger(f"uploading folder: {folder_name}")
            conn.setblocking(True)
            shutil.make_archive(server_folder_name + "/" + folder_name, "zip", server_folder_name + "/" + folder_name)
            
            logger("Send folder name")
            conn.send(send_new_folder(folder_name))
            logger("Send zip size")
            file_size = os.path.getsize(server_folder_name + "/" + folder_name + ".zip")
            print("File Size is :", file_size, "bytes")
            conn.send(send_new_folder(str(file_size)))
            
            print("Sending the file data")
            with open(server_folder_name + "/" + folder_name + ".zip", 'rb') as f1:
                conn.send(f1.read())
            msg = conn.recv(1024).decode()
            print(f"[SERVER]: {msg}")
            
            conn.setblocking(False)
            logger(f"Uploading finished")
        except AttributeError:
            conn.close()
        except (ConnectionResetError, ConnectionAbortedError):
            print(f"Connection: {conn} Connection Reset while updating Client")
            conn.setblocking(False)
            return

    def Request_New_Client(self, conn: socket.socket):
        try:
            #shutil.make_archive("client", "zip", os.getcwd() + "/client_main")
            print("upload Client.exe")
            conn.setblocking(True)
            #os.getcwd() + "/client_main.exe"
            
            file_size = os.path.getsize(path_to_client_exe)
            print("File Size is :", file_size, "bytes")
            #file_size_in_bytes = file_size.to_bytes(8, 'big')

            print("Sending the file size")
            conn.send(send_client_size(str(file_size)))
            msg_type, payload = receive_proto_block(conn)
            print(f"[SERVER]: {payload.decode()}")

            print("Sending the file data")
            with open(path_to_client_exe, 'rb') as f1:
                conn.send(f1.read())
            msg = conn.recv(1024).decode("utf-8")
            print(f"[SERVER]: {msg}")
            conn.setblocking(False)
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
