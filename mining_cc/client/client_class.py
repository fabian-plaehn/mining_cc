import copy
from multiprocessing import Process
import os
import pickle
import platform
import queue
import random
import shutil
import socket
import subprocess
from subprocess import Popen, PIPE, STDOUT
import sys
import threading
import time
import json
import parse
import keyboard
import psutil
import requests

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
current_miner_stats = {}

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
        
        self.thread_kill = 0
        self.report_process = threading.Thread(target=self.report_miner_info, args=(self.thread_kill,))
        self.report_process.daemon = True
        
        
    def activate(self, e_json=None):
        if self.active:
            logger(f"Miner {self.name} already active")
            return
        
        logger(f"Activate miner: {self.name}")
        # TODO can crash here
        with open(f"{self.name}/{self.config_name}", "rb") as f:
            miner_config = json.load(f)
        
        try:miner_config["cpu"]["enabled"] = True
        except:pass
        
        if e_json is not None:miner_config = merge(miner_config, e_json)

        with open(f"{self.name}/{self.config_name}", "w") as f:
            json.dump(miner_config, f)
            
        self.active = True 
        self.start()
        
    def restart(self):
        self.kill()
        self.start()
        
    def start(self):
        logger(f"Try start miner: {self.name}")
        if self.pid is None:
            try: 
                if not os.path.isfile(os.path.join(os.getcwd(),self.name,self.exe_name)):
                    logger(f"Miner {self.name} not found")
                    return
                if not self.name == "QUBIC": self.process = subprocess.Popen("sudo " + os.path.join(os.getcwd(),self.name,self.exe_name), shell=True, cwd=os.path.join(os.getcwd(),self.name), stdin=PIPE, stdout=PIPE, stderr=STDOUT) # , creationflags=CREATE_NEW_CONSOLE)
                else:  self.process = subprocess.Popen(os.path.join(os.getcwd(),self.name,self.exe_name), shell=True, cwd=os.path.join(os.getcwd(),self.name), stdin=PIPE, stdout=PIPE, stderr=STDOUT) # , creationflags=CREATE_NEW_CONSOLE)
                self.pid = self.process.pid
                
                self.thread_kill += 1
                self.report_process = threading.Thread(target=self.report_miner_info, args=(self.thread_kill,))
                self.report_process.daemon = True
                
                self.report_process.start()
                print("process started")
            except PermissionError:
                logger("Permission error")
                if os_system == "linux":
                    os.popen(f"sudo chmod u+x {os.path.join(os.getcwd(),self.name,self.exe_name)}")
                    self.start()
        else:
            pid_list = get_process_id_and_childen(self.pid)
            print(pid_list)
            if pid_list is None or len(pid_list) < 2:
                logger(f"Miner {self.name} not enough processes running")
                self.restart()
            else:
                logger(f"Miner {self.name} already running")
                
    def stop(self):
        self.active = False
        if self.report_process is not None:
            self.thread_kill += 1
        if not self.run_always: self.kill()
        else:
            try:
                with open(os.path.join(os.getcwd(),self.name,self.config_name), "r") as f:
                    miner_config = json.load(f)
                miner_config["cpu"]["enabled"] = False
                with open(os.path.join(os.getcwd(),self.name,self.config_name), "w") as f:
                    json.dump(miner_config, f)
            except: pass
                
    def kill(self):
        try:
            logger(f"Kill Miner: {self.name}, {self.pid}")
            if self.report_process is not None:
                self.thread_kill += 1
            for process in psutil.process_iter():
                for arg in process.cmdline():
                    if self.name in arg:
                        print("cleaned :", process.name, process.cmdline())
                        kill_process_and_children(process.pid)
                if self.name in process.exe():
                    print("cleaned :", process.name, process.exe())
                    kill_process_and_children(process.pid)
            self.pid = None
        except AttributeError:
            return
        
    def report_miner_info(self, thread_id):
        logger("Reporter thread started")
        global current_miner_stats
        miner_name_to_api_port = {"RTC":58001, "ZEPH":58002, "XDAG":58003, "YDA":58004}
        while True:
            try:
                if thread_id < self.thread_kill: break
                if self.name == "QUBIC" and self.process is not None and self.process.stdout is not None:
                    for std_out_p in self.process.stdout:
                        print(std_out_p)
                        if thread_id < self.thread_kill: break
                        parsed = parse.parse("{date} {time}\tINFO\tE:{epoch} | SOL: {sol}/{sol_total} | Try {id} | {hs} it/s {chunk}\n", std_out_p.decode())
                        print(parsed)
                        try: current_miner_stats = {"name": self.name, "hashrate":float(parsed["hs"]), "time_stamp":time.time()}
                        except: current_miner_stats = {"name": self.name, "hashrate":0, "time_stamp":time.time()}
                if self.name in miner_name_to_api_port:
                    for std_out_p in self.process.stdout:
                        print(std_out_p)
                        if thread_id < self.thread_kill: break
                        answer = requests.get(f"http://127.0.0.1:{miner_name_to_api_port[self.name]}/2/summary")
                        try: current_miner_stats = {"name": self.name, "hashrate":float(answer.json()["hashrate"]["total"][0]), "time_stamp":time.time()}
                        except: current_miner_stats = {"name": self.name, "hashrate":0, "time_stamp":time.time()}
                time.sleep(1)
            except: pass
        logger("Reporter Thread killed")
        
'''def get_miner_info(name, process) -> dict:
    if name == "QUBIC":
        logger("Listen to STDOUT")
        if process is not None and process.stdout is not None:
            for std_out in process.stdout:
                print(std_out)
    
def report_miner_info(socket, get_miner_info, miner_process):
    pass'''
    
def absolut_clean_up():
    global miner_info_dict
    for miner_name, _ in miner_info_dict.items():
        try:
            for process in psutil.process_iter():
                for arg in process.cmdline():
                    if miner_name in arg:
                        print("cleaned :", process.name, process.cmdline())
                        kill_process_and_children(process.pid)
                if miner_name in process.exe():
                    print("cleaned :", process.name, process.exe())
                    kill_process_and_children(process.pid)
        except: pass
          
miner_info_dict = {"ZEPH":Miner_Info("ZEPH", False, "xmrigDaemon", "config.json"),
                   "XDAG":Miner_Info("XDAG", False, "xmrigDaemon", "config.json"),
                   "RTC":Miner_Info("RTC", False, "xmrigDaemon", "config.json"),
                   "YDA":Miner_Info("YDA", False, "xmrigDaemon", "config.json"),
                   "QUBIC":Miner_Info("QUBIC", False, "qli-Client", "appsettings.json")}

current_Miner = None

class Client:
    def __init__(self):
        global current_Miner
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
            current_Miner = self.config["Current_Miner"]
        
    def check_miner_versions(self, server_json: dict):
        hash_json = {}
        for file in os.listdir(os.getcwd()):
            file_path = file
            if not os.path.isdir(os.path.join(os.getcwd(),file_path)):
                continue
            hash_d = single_file_hash(os.path.join(os.getcwd(),file_path+".zip") )
            hash_json[file] = hash_d
        for key, _ in server_json.items():
            if key not in hash_json:
                self.client_socket.send(request_new_folder({"OS_System":os_system, "folder_name":key}))
            elif server_json[key] != hash_json[key]:
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
        global current_Miner
        global current_miner_stats
        absolut_clean_up()
        self.start_check_miner()
        self.client_socket = connect_to_server(self.host, self.port)
        check_every = 10
        last_check_time = time.time()
        
        req_hashes_every = 120
        last_req_hashes_time = time.time() - req_hashes_every
        #report_process = Process(target=current_Miner.report_miner_info, args=(self.client_socket,))
        #report_process.start()
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
                    logger(f"Check On Miner / Current Miner: {current_Miner}")
                    self.start_check_miner()
                    print(current_miner_stats)
                    self.client_socket.send(send_pickle_data(Send_Miner_Data, pickle.dumps(current_miner_stats)))
                    last_check_time = time.time()
                if (time.time() - last_req_hashes_time) > req_hashes_every:
                    logger("Requesting Miner Hashes")
                    self.client_socket.send(request_miner_hashes({"OS_System":os_system}))
                    logger("Send Miner Data")
                    
                    last_req_hashes_time = time.time()
                    with open("client_config.json", "w") as f:
                        f.write(json.dumps(self.config, indent=2))
        except (ConnectionResetError, ConnectionAbortedError):
            self.run()
        except KeyboardInterrupt:
            print("Closing.. Save Config")
            for _, miner in miner_info_dict.items():
                miner.kill()
            absolut_clean_up()
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
            if miner.run_always:
                miner.start()
                
            if current_Miner is not None: miner_info_dict[current_Miner].start()
                

    def activate_miner(self, payload):  # payload {"miner_name": miner_name, "config": {}}
        global current_Miner
        global miner_info_dict

        miner_name = payload["miner_name"]
        config = payload["config"]
        logger(f"set new miner: {miner_name}")  
        self.config["Current_Miner"] = miner_name
        print("current Miner: ",current_Miner)
        if current_Miner is not None and current_Miner != miner_name:
            miner_info_dict[current_Miner].stop()
            if miner_info_dict[current_Miner].run_always: miner_info_dict[current_Miner].restart()
            current_Miner = miner_info_dict[miner_name]
            miner_info_dict[miner_name].activate(config)
        elif current_Miner is None:
            for name, miner in miner_info_dict.items():
                miner.stop()
            current_Miner = miner_name
            miner_info_dict[miner_name].activate(config)
        current_Miner = miner_name
        
if __name__ == "__main__":
    pass

#wget -O qli-Service-install.sh https://dl.qubic.li/cloud-init/qli-Service-install.sh
#chmod u+x qli-Service-install.sh
#./qli-Service-install.sh 16 eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJJZCI6IjY0ZTdmNzIyLTA1ZDgtNDNlYy05YTU0LTBlNTljMGUzMGRjOSIsIk1pbmluZyI6IiIsIm5iZiI6MTcxMDc1Njk1OSwiZXhwIjoxNzQyMjkyOTU5LCJpYXQiOjE3MTA3NTY5NTksImlzcyI6Imh0dHBzOi8vcXViaWMubGkvIiwiYXVkIjoiaHR0cHM6Ly9xdWJpYy5saS8ifQ.WQut3zCgcVGNDgxSGveI32m_p8WH9WC1i9iETRrkYrkw4HLBJAgaK6feqOHPDBqoxcjVWbS39Unr8zPXAJfAxg