import os
import pickle
import random
import shutil
import socket
import sys
import time
import json

from mining_cc.shared.hashes import dirhash

from mining_cc.shared.utils import logger
from mining_cc.shared.ProtoHeader import *
from mining_cc.shared.connection import *


class Client:
    def __init__(self):
        try:
            with open("client_config.json", "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            print("config not found. Creating one")
            config = {}
        config["Connection"] = {}
        config["Connection"]["id"] = socket.gethostbyname(socket.gethostname())
        config["Connection"]["host"] = socket.gethostbyname(socket.gethostname())
        config["Connection"]["port"] = 5000

        with open("client_config.json", "w") as f:
            f.write(json.dumps(config, indent=2))
        print("loaded config: ", config)

        self.config = config
        self.id = self.config["Connection"]["id"]
        self.host = self.config["Connection"]["host"]
        self.port = self.config["Connection"]["port"]
        
    def check_miner_versions(self, server_json: dict):
        hash_json = {}
        for file in os.listdir():
            file_path = file
            if not os.path.isdir(file_path):
                continue
            # is dir
            hash_d = dirhash(file_path, excluded_files=["config.json"])
            hash_json[file] = hash_d
        for key, _ in server_json.items():
            if key not in hash_json:
                print("request 2")
                self.client_socket.send(request_new_folder(key))
            elif server_json[key] != hash_json[key]:
                print("request")
                self.client_socket.send(request_new_folder(key))
                
    def new_folder(self, folder_name):
        SIZE = 1024
        
        self.client_socket.setblocking(True)
        logger(f"[RECV] Received the folder name")
        logger(f"{folder_name}")
        
        logger(f"[RECV] Receiving the folder size")
        request, payload = receive_proto_block(self.client_socket)
        folder_size = int(payload.decode())
        logger(f"{folder_size}")
        
        logger(f"[RECV] Receiving the file data.")
        # Until we've received the expected amount of data, keep receiving
        packet = b""  # Use bytes, not str, to accumulate
        while len(packet) < folder_size:
            if (folder_size - len(packet)) > SIZE:  # if remaining bytes are more than the defined chunk size
                buffer = self.client_socket.recv(SIZE)  # read SIZE bytes
            else:
                buffer = self.client_socket.recv(folder_size - len(packet))  # read remaining number of bytes

            if not buffer:
                raise Exception("Incomplete file received")
            packet += buffer
        with open(f"{folder_name}.zip", 'wb') as f:
            f.write(packet)
            
        try:
            shutil.unpack_archive(f"{folder_name}.zip", f"{folder_name}")
        except PermissionError:
            logger("Miner not closed")
            
        logger(f"[RECV] File data received.")
        self.client_socket.send("File data received".encode())
        self.client_socket.setblocking(False)

    def run(self):
        self.client_socket = connect_to_server(self.host, self.port)
        try:
            while True:
                request_typ, payload = receive_proto_block(self.client_socket)
                if request_typ == ExitRequest:
                    client_socket = connect_to_server(self.host, self.port)
                elif request_typ == LoginRequest:
                    self.client_socket.send(format_login_request(self.id))
                elif request_typ == Send_Miner_Hashes:
                    hash_dir = json.loads(payload.decode().replace("'", '"'))
                    self.check_miner_versions(hash_dir)
                elif request_typ == Send_New_Folder:
                    self.new_folder(payload.decode())
                elif request_typ == Activate_Miner:
                    logger("Activate_Miner")
                logger("Requesting Miner Hashes")
                self.client_socket.send(request_miner_hashes())
                time.sleep(1)
                
        except ConnectionResetError:
            self.run()
        except KeyboardInterrupt:
            print("Closing.. Save Config")
            self.client_socket.close()  # close the connection
            with open("client_config.json", "w") as f:
                f.write(json.dumps(self.config, indent=2))
            time.sleep(2)
            print("Exiting")
            sys.exit(0)

if __name__ == "__main__":
    pass