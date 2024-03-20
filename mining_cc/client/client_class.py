import os
import pickle
import platform
import random
import shutil
import socket
import subprocess
from subprocess import Popen, PIPE, STDOUT
import sys
import time
import json

import keyboard
import psutil

from mining_cc.shared.hashes import dirhash, single_file_hash

from mining_cc.shared.utils import get_process_id_and_childen, kill_process_and_children, logger, merge, payload_to_dict
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
path_to_client_exe = f"{client_folder_name}/{client_file_name}"
client_process = None

status_data = subprocess.check_output(["tailscale", "status", "--json"]).decode("utf-8")
status_data = json.loads(status_data)

for node_key, data_dict in status_data["Peer"].items():
    if "mining-cc-server" in data_dict["DNSName"]:
        print("Server_found", data_dict["HostName"], data_dict["DNSName"], data_dict["TailscaleIPs"])
        server_ip = data_dict["TailscaleIPs"][0]
        server_port = 5000
        break

tailscale_ip = status_data["TailscaleIPs"][0]


class Miner_Info:
    def __init__(self, name, run_always, exe_name, config_name) -> None:
        self.name = name
        self.exe_name = exe_name
        self.run_always = run_always
        self.process = None
        self.pid = None
        self.active = False
        self.currently_updating = False
        self.config_name = config_name
        
    def activate(self, e_json=None):
        if self.active:
            logger(f"Miner {self.name} already active")
            pass
        
        logger(f"Activate miner: {self.name}")
        with open(f"{self.name}/{self.config_name}", "rb") as f:
            miner_config = json.load(f)
        
        try:
            miner_config["cpu"]["enabled"] = True
        except:
            pass
        
        if e_json is not None:
            miner_config = merge(miner_config, e_json)

        with open(f"{self.name}/{self.config_name}", "w") as f:
            json.dump(miner_config, f)
            
        self.active = True 
        self.start()
        
    def restart(self):
        self.kill()
        self.start()
        
    def start(self):
        if self.pid is None:
            logger(f"Start miner: {self.name}")
            try: 
                if os_system == "windows":
                    self.process = subprocess.Popen(f"cd {self.name} && {self.exe_name} cd ..",shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True) # , creationflags=CREATE_NEW_CONSOLE)
                    self.pid = self.process.pid
                elif os_system == "linux":
                    self.process = subprocess.Popen(f"{self.name}/{self.exe_name}", shell=True) # , creationflags=CREATE_NEW_CONSOLE)
                    self.pid = self.process.pid
                print("process started")
            except PermissionError:
                if os_system == "linux":
                    os.popen(f"sudo chmod u+x {self.name}/{self.exe_name}")
                    self.start()
        else:
            pid_list = get_process_id_and_childen(self.pid)
            print(pid_list)
            if pid_list is None or len(pid_list) < 2:
                kill_process_and_children(self.pid)
                self.pid = None
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
            try:
                miner_config["cpu"]["enabled"] = False
                with open(f"{self.name}/config.json", "w") as f:
                    json.dump(miner_config, f)
            except:
                pass
                
    def kill(self):
        try:
            logger(f"Kill Miner: {self.name}, {self.pid}")
            if self.pid is None:
                return
            kill_process_and_children(self.pid)
            self.pid = None
        except AttributeError:
            return
        
    def get_std_out(self):
        '''for p in psutil.process_iter():
            try : print("START Process_NAME: ", p.name(), "CMD: ",p.cmdline(), "EXE: ",p.exe(), "END")
            except : pass
        return'''
    
        for p in psutil.process_iter():
            try:
                for arg in p.cmdline():
                    if "QUBIC" in arg:
                        pid_list = get_process_id_and_childen(p.pid)
                        for pid in pid_list:
                            proc = psutil.Process(pid)
                            print("START Process_NAME: ", proc.name(), "CMD: ",proc.cmdline(), "EXE: ",proc.exe(), "END")
            except psutil.AccessDenied:
                pass
        return
        print("GET_STDOUT: ", self.process)
        if self.process is not None:
            print("GET_STDOUT: ", self.process.stdout)
        if self.process is not None and self.process.stdout is not None:
            for std_out in self.process.stdout:
                print(std_out)
                
                return 
                
        
        
miner_info_dict = {"ZEPH":Miner_Info("ZEPH", False, "xmrigDaemon", "config.json"),
                   "XDAG":Miner_Info("XDAG", False, "xmrigDaemon", "config.json"),
                   "RTC":Miner_Info("RTC", False, "xmrigDaemon", "config.json"),
                   "YDA":Miner_Info("YDA", False, "xmrigDaemon", "config.json"),
                   "QUBIC":Miner_Info("QUBIC", False, "qli-Client", "appsettings.json")}

current_Miner: Miner_Info = None

class Client:
    def __init__(self):
        try:
            with open("client_config.json", "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            print("config not found. Creating one")
            config = {}
            config["Current_Miner"] = None
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
        
        if "Current_Miner" in self.config and self.config["Current_Miner"] is not None:
            self.activate_miner({"miner_name":config["Current_Miner"], "config":{}})
        
    def check_miner_versions(self, server_json: dict):
        hash_json = {}
        for file in os.listdir():
            file_path = file
            if not os.path.isdir(file_path):
                continue
            # is dir
            hash_d = single_file_hash(file_path + ".zip")
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
            miner_info_dict[folder_name].currently_updating = True
            if miner_info_dict[folder_name].pid is not None:
                print(get_process_id_and_childen(miner_info_dict[folder_name].pid))
                kill_process_and_children(miner_info_dict[folder_name].pid)
                # new version
            time.sleep(0.1)
            shutil.rmtree(f"{folder_name}")
        try:
            shutil.unpack_archive(f"{folder_name}.zip", f"{folder_name}")
        except PermissionError:
            logger("Miner not closed")
        
        if os_system == "linux":
            for file in os.listdir(folder_name):
                if os.path.isfile(folder_name + "/" + file):
                    subprocess.check_call(['chmod', '+x', folder_name+"/"+file])
                    #os.popen(f"sudo chmod u+x {folder_name}/{file}")
        miner_info_dict[folder_name].currently_updating = False
        self.client_socket.setblocking(False)

    def run(self):
        global miner_info_dict
        self.start_check_miner()
        self.client_socket = connect_to_server(self.host, self.port)
        check_every = 10
        last_check_time = time.time() - 10
        
        req_hashes_every = 120
        last_req_hashes_time = time.time() - req_hashes_every
        try:
            while True:
                time.sleep(1)
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
                    payload = pickle.loads(payload)
                    self.activate_miner(payload)
                if (time.time() - last_check_time) > check_every:
                    logger("Check On Miner")
                    if current_Miner is not None: current_Miner.get_std_out()
                    self.start_check_miner()
                    last_check_time = time.time()
                if (time.time() - last_req_hashes_time) > req_hashes_every:
                    logger("Requesting Miner Hashes")
                    self.client_socket.send(request_miner_hashes({"OS_System":os_system}))
                    last_req_hashes_time = time.time()
                    with open("client_config.json", "w") as f:
                        f.write(json.dumps(self.config, indent=2))
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
        if os_system == "linux":
            for path, subdirs, files in os.walk("./"):
                for name in files:
                    if name.endswith(".json"):
                        continue
                    subprocess.check_call(['chmod', '+x', os.path.join(path, name)])
        for key, miner in miner_info_dict.items():
            if miner.run_always or miner.active:
                miner.start()
                

    def activate_miner(self, payload):  # payload {"miner_name": miner_name, "config": {}}
        global current_Miner
        global miner_info_dict
        
        miner_name = payload["miner_name"]
        config = payload["config"]
        logger(f"set new miner: {miner_name}")  
        self.config["Current_Miner"] = miner_name
        if current_Miner is not None and current_Miner.name != miner_name:
            current_Miner.stop()
            if current_Miner.run_always: current_Miner.restart()
            current_Miner = miner_info_dict[miner_name]
            miner_info_dict[miner_name].activate(config)
        elif current_Miner is None:
            for name, miner in miner_info_dict.items():
                miner.stop()
            current_Miner = miner_info_dict[miner_name]
            miner_info_dict[miner_name].activate(config)

if __name__ == "__main__":
    pass

#wget -O qli-Service-install.sh https://dl.qubic.li/cloud-init/qli-Service-install.sh
#chmod u+x qli-Service-install.sh
#./qli-Service-install.sh 16 eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJJZCI6IjY0ZTdmNzIyLTA1ZDgtNDNlYy05YTU0LTBlNTljMGUzMGRjOSIsIk1pbmluZyI6IiIsIm5iZiI6MTcxMDc1Njk1OSwiZXhwIjoxNzQyMjkyOTU5LCJpYXQiOjE3MTA3NTY5NTksImlzcyI6Imh0dHBzOi8vcXViaWMubGkvIiwiYXVkIjoiaHR0cHM6Ly9xdWJpYy5saS8ifQ.WQut3zCgcVGNDgxSGveI32m_p8WH9WC1i9iETRrkYrkw4HLBJAgaK6feqOHPDBqoxcjVWbS39Unr8zPXAJfAxg