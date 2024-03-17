import os
import pickle
import platform
import random
import shutil
import socket
import subprocess
import sys
import time
import json

import keyboard
import psutil

from mining_cc.shared.hashes import dirhash

from mining_cc.shared.utils import kill_process_and_children, logger, merge, payload_to_dict
from mining_cc.shared.ProtoHeader import *
from mining_cc.shared.connection import *


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


class Miner_Info:
    def __init__(self, name, run_always, exe_name) -> None:
        self.name = name
        self.exe_name = exe_name
        self.run_always = run_always
        self.process = None
        self.active = False
        self.currently_updating = False
        
    def activate(self, e_json=None):
        if self.active:
            logger(f"Miner {self.name} already active")
            pass
        
        logger(f"Activate miner: {self.name}")
        try:
            with open(f"{self.name}/config.json", "r") as f:
                miner_config = json.load(f)
        except FileNotFoundError:
            return 
        
        if self.run_always:
            miner_config["cpu"]["enabled"] = True
            
        if e_json is not None:
            miner_config = merge(miner_config, e_json)
        with open(f"{self.name}/config.json", "w") as f:
            json.dump(miner_config, f)
            
        self.active = True 
        self.start()
        
    def restart(self):
        self.kill()
        self.start()
        
    def start(self):
        if self.process is None:
            logger(f"Start miner: {self.name}")
            try: 
                self.process = subprocess.Popen(f"cd {self.name} &&  {self.exe_name}", shell=True) # , creationflags=CREATE_NEW_CONSOLE)
                print("process started")
            except PermissionError:
                os.popen(f"sudo chmod u+x {self.name}/{self.exe_name}")
                self.start()
                
    def stop(self):
        self.active = False
        if not self.run_always:
            self.kill()
        else:
            try:
                with open(f"{self.name}/config.json", "r") as f:
                    miner_config = json.load(f)
            except FileNotFoundError:
                return
            miner_config["cpu"]["enabled"] = False
            with open(f"{self.name}/config.json", "w") as f:
                json.dump(miner_config, f)
    def kill(self):
        try:
            logger(f"Kill Miner: {self.name}, {self.process.pid}")
            if self.process is None:
                return
            kill_process_and_children(self.process.pid)
            while psutil.pid_exists(self.process.pid):
                pass
            self.process = None
        except AttributeError:
            return
        
        
miner_info_dict = {"ZEPH":Miner_Info("ZEPH", True, "xmrigDaemon"),
                   "XDAG":Miner_Info("XDAG", True, "xmrigDaemon")}

current_Miner: Miner_Info = None

class Client:
    def __init__(self):
        try:
            with open("client_config.json", "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            print("config not found. Creating one")
            config = {}
        config["Connection"] = {}
        config["Connection"]["id"] = socket.gethostname()
        config["Connection"]["host"] = tailscale_ip
        config["Connection"]["port"] = 5000

        with open("client_config.json", "w") as f:
            f.write(json.dumps(config, indent=2))
        print("loaded config: ", config)

        self.config = config
        self.id = self.config["Connection"]["id"]
        self.host = server_ip
        self.port = server_port
        
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
                self.client_socket.send(request_new_folder({"OS_System":os_system, "folder_name":key}))
            elif server_json[key] != hash_json[key]:
                print("request")
                self.client_socket.send(request_new_folder({"OS_System":os_system, "folder_name":key}))
                
    def new_folder(self, payload):
        SIZE = 1024
        folder_name = payload["folder_name"]
        folder_size = payload["folder_size"]
        
        self.client_socket.setblocking(True)
        logger(f"[RECV] Received the folder name")
        logger(f"{folder_name}")
        
        logger(f"[RECV] Receiving the folder size")
        logger(f"{folder_size}")
        
        logger(f"[RECV] Receiving the file data.")
        # Until we've received the expected amount of data, keep receiving
        packet = b""  # Use bytes, not str, to accumulate
        while True:
            type_request, payload = receive_proto_block(self.client_socket)
            if type_request == Send_Folder_Finished:
                break
            packet += payload
        with open(f"{folder_name}.zip", 'wb') as f:
            f.write(packet)

        logger(f"[RECV] File data received.")
        if os.path.isdir(folder_name):
            shutil.rmtree(f"{folder_name}")
        try:
            shutil.unpack_archive(f"{folder_name}.zip", f"{folder_name}")
        except PermissionError:
            logger("Miner not closed")
        self.client_socket.setblocking(False)

    def run(self):
        global miner_info_dict
        check_every = 10
        last_check_time = time.time() - check_every
        self.start_check_miner()
        self.client_socket = connect_to_server(self.host, self.port)
        try:
            while True:
                if keyboard.is_pressed('q'):
                    raise KeyboardInterrupt
        
                request_typ, payload = receive_proto_block(self.client_socket)
                payload = payload_to_dict(payload)
                if request_typ == ExitRequest:
                    self.client_socket = connect_to_server(self.host, self.port)
                elif request_typ == LoginRequest:
                    self.client_socket.send(format_login_request(self.id))
                elif request_typ == Send_Miner_Hashes:
                    self.check_miner_versions(payload)
                elif request_typ == Send_Folder_Info:
                    self.new_folder(payload)
                elif request_typ == Activate_Miner:
                    logger("Activate_Miner")
                    self.activate_miner(payload)
                if (time.time() - last_check_time) > check_every:
                    logger("Requesting Miner Hashes")
                    self.client_socket.send(request_miner_hashes({"OS_System":os_system}))
                    self.start_check_miner()
                    last_check_time = time.time()
                
        except (ConnectionResetError, ConnectionAbortedError):
            self.run()
        except KeyboardInterrupt:
            print("Closing.. Save Config")
            for miner_name, miner in miner_info_dict.items():
                miner.kill()
            self.client_socket.close()  # close the connection
            with open("client_config.json", "w") as f:
                f.write(json.dumps(self.config, indent=2))
            time.sleep(2)
            print("Exiting")
            sys.exit(0)
            
    def start_check_miner(self):
        global miner_info_dict
        for key, miner in miner_info_dict.items():
            if miner.run_always or miner.active:
                miner.start()
                
    def activate_miner(self, payload):  # payload {"miner_name": miner_name, "config": {}}
        global current_Miner
        global miner_info_dict
        payload = pickle.loads(payload)
        miner_name = payload["miner_name"]
        config = payload["config"]
        logger(f"set new miner: {miner_name}")  
        if current_Miner is not None and current_Miner.name != miner_name:
            current_Miner.stop()
            if current_Miner.run_always: current_Miner.restart()
            current_Miner = miner_info_dict[miner_name]
            current_Miner.activate(config)
        elif current_Miner is None:
            for name, miner in miner_info_dict.items():
                miner.stop()
            current_Miner = miner_info_dict[miner_name]
            current_Miner.activate(config)

if __name__ == "__main__":
    pass