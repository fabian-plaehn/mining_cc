from hashlib import md5
import json
import os
import platform
import socket
import subprocess
import sys
import time
from typing import Literal

import psutil

from mining_cc.shared.connection import connect_to_server
from mining_cc.shared.ProtoHeader import *
from mining_cc.shared.hashes import single_file_hash, dirhash
from mining_cc.shared.utils import kill_process_and_children, logger, payload_to_dict
import threading

os_system = platform.system().lower()
client_folder_name = "Client_Folder"
if os_system == "windows":
    extension = ".exe"
elif os_system == "linux":
    extension = ".bin"
else:
    raise Exception("not supported os")
client_file_name = "client_main" + extension
server_ip = "100.96.210.95"
server_port = 5000
path_to_client_exe = f"{client_folder_name}/{client_file_name}"
client_process = None

status_data = subprocess.check_output(["tailscale", "status", "--json"]).decode("utf-8")
status_data = json.loads(status_data)

tailscale_ip = status_data["TailscaleIPs"][0]

print(f"OS_System: {os_system}, client_path: {path_to_client_exe}, tailscale_ip: {tailscale_ip}")


class Deamon:
    def __init__(self):
        try:
            with open("client_config.json", "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            logger("config not found. Creating one", "info")
            config = {}
        config["Connection"] = {}
        config["Connection"]["id"] = f"{socket.gethostname()}_deamon"
        config["Connection"]["host"] = tailscale_ip
        config["Connection"]["port"] = 5001
        with open("client_config.json", "w") as f:
            f.write(json.dumps(config, indent=2))
        logger(f"loaded config: {config}", "info")

        self.config = config
        self.id = self.config["Connection"]["id"]
        self.host = "100.96.210.95"
        self.port = 5001
        
        self.t_stop = False
        self.test_value = 0
        self.t = threading.Thread(target=self.test, args=[1])
        self.t.start()
        
        self.client_process = None
        
    def test(self, i):
        pass
        
    def update_client(self, paylod:Literal[b""]):
        try:
            logger("updating client")
            
            if self.client_process is not None:
                logger("Shutting down client process")
                kill_process_and_children(self.client_process.pid)
                while psutil.pid_exists(self.client_process.pid):
                    pass
                self.client_process = None
            SIZE = 1024
            BYTEORDER_LENGTH = 8
            FORMAT = "utf-8"
            
            self.client_socket.setblocking(True)
            filename = paylod["file_name"]
            filesize = paylod["file_size"]
            file_size = int(filesize)
            logger(f"File size received: {file_size} bytes")
            logger(f"File name received: {filename} bytes")

            logger(f"[RECV] Receiving the file data.")
            # Until we've received the expected amount of data, keep receiving
            packet = b""  # Use bytes, not str, to accumulate
            while True:
                type_request, payload = receive_proto_block(self.client_socket)
                if type_request == Send_Client_Finished:
                    break
                packet += payload
            with open(path_to_client_exe, 'wb') as f:
                f.write(packet)

            logger(f"[RECV] File data received.")
            self.client_socket.setblocking(False)
        except UnicodeDecodeError:
            self.client_socket.close()
        
    def check_client_version(self):
        logger("checking client version")
        if not os.path.isdir(client_folder_name):
            os.mkdir(client_folder_name)
                  
        if not os.path.isfile(f"{client_folder_name}/{client_file_name}"):
            self.client_socket.send(request_new_client({"OS_System":os_system}))
            return
        else:
            logger("Request Client Hash")
            self.client_socket.send(request_client_hash({"OS_System":os_system}))
            
    def start_check_client(self):
        try:
            if self.client_process is None:
                try:
                    self.client_process = subprocess.Popen(path_to_client_exe)
                except PermissionError:
                    subprocess.Popen(f"chmod u+x {path_to_client_exe}")
                    self.start_check_client()
                except OSError:
                    return
            if self.client_process is not None and not psutil.pid_exists(self.client_process.pid):
                self.client_process = None
        except FileNotFoundError:
            pass
        
    def run(self):
        self.start_check_client()
        self.client_socket = connect_to_server(self.host, self.port)
        check_every = 10
        last_check_time = time.time() - check_every
        try:
            while True:
                request_typ, payload = receive_proto_block(self.client_socket)
                payload = payload_to_dict(payload)
                if request_typ == ExitRequest:
                    logger("ExitRequest received")
                    self.client_socket = connect_to_server(self.host, self.port)
                elif request_typ == LoginRequest:
                    logger("LoginRequest received")
                    self.client_socket.send(format_login_request(self.id))
                elif request_typ == Send_Client_Info:
                    logger("Send_Client_Size received")
                    self.update_client(payload)
                elif request_typ == Send_Client_Hash:
                    logger("Send_Client_Hash received")
                    hash = single_file_hash(path_to_client_exe)
                    hash_server = payload["hash"]
                    logger(f"hash_server:  {hash_server}")
                    logger(f"hash deamon: {hash}")
                    if hash != hash_server:
                        self.client_socket.send(request_new_client({"OS_System":os_system}))
                
                if (time.time() - last_check_time) > check_every:
                    self.check_client_version()
                    self.start_check_client()
                    last_check_time = time.time()
                
        except ConnectionResetError:
            self.run()
        except KeyboardInterrupt:
            logger("Closing.. Save Config")
            self.t_stop = True
            self.client_socket.close()  # close the connection
            with open("client_config.json", "w") as f:
                f.write(json.dumps(self.config, indent=2))
            logger("Exiting")
            self.client_process.kill()
            self.client_process.wait()
            sys.exit(0)
            