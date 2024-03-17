import json
import os
import platform
import shutil
import socket
import subprocess
import time
import threading
from flask import Flask, request, Response
import keyboard
import psutil
import requests
from multiprocessing import Process
from mining_cc.shared.hashes import single_file_hash, dirhash
from mining_cc.shared.utils import kill_process_and_children, logger, merge
from werkzeug.serving import make_server

app = Flask(__name__)

os_system = platform.system().lower()
status_data = subprocess.check_output(["tailscale", "status", "--json"]).decode("utf-8")
status_data = json.loads(status_data)

tailscale_ip = status_data["TailscaleIPs"][0]

class Miner_Info:
    def __init__(self, name, run_always) -> None:
        self.name = name
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
            self.process = subprocess.Popen(f"cd {self.name} &&  xmrigDaemon", shell=True) # , creationflags=CREATE_NEW_CONSOLE)
        
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
        
        
miner_info_dict = {"ZEPH":Miner_Info("ZEPH", True),
                   "XDAG":Miner_Info("XDAG", True)}

current_Miner: Miner_Info = None
        

client_folder_name = "Client_Folder"
client_file_name = "client_main.exe"
server_ip = "100.96.210.95"
server_port = 5000


path_to_client_exe = f"{client_folder_name}/{client_file_name}"
client_process = None

def download_miner_folder(foldername):
    global miner_info_dict
    resp = requests.get(f"http://{server_ip}:{server_port}/{os_system}/new_miner", json={"foldername":foldername})
    if not resp.ok:
        return 
    fd = open(foldername + ".zip", "wb")
    fd.write(resp.content)
    fd.close()
    
    miner_info_dict[foldername].currently_updating = True
    miner_info_dict[foldername].kill()
    if os.path.isdir(foldername):
        shutil.rmtree(f"{foldername}")
    try:
        shutil.unpack_archive(f"{foldername}.zip", f"{foldername}")
    except PermissionError:
        logger("Miner not closed")

def check_miner_versions():
    hash_json = {}
    for file in os.listdir():
        file_path = file
        if not os.path.isdir(file_path):
            continue
        hash_d = dirhash(file_path, excluded_files=["config.json"])
        hash_json[file] = hash_d
    logger(hash_json)
    resp = requests.get(f"http://{server_ip}:{server_port}/{os_system}/new_miner_hashes")
    if not resp.ok:
            return 
    server_hashes = json.loads(resp.content.decode().replace("'",'"'))
    logger(server_hashes)
    for key, _ in server_hashes.items():
        if key not in hash_json:
            download_miner_folder(key)
        elif server_hashes[key] != hash_json[key]:
            download_miner_folder(key)
    
def start_check_miner():
    global miner_info_dict
    for key, miner in miner_info_dict.items():
        if miner.run_always or miner.active:
            miner.start()

def main_run():
    check_every = 10
    last_check_time = time.time() - check_every
    while True:
        if keyboard.is_pressed('e'):
            logger("shutting down detected")
            requests.get(f"http://{socket.gethostbyname(socket.gethostname())}:{5002}/shutdown")
            break
        if (time.time() - last_check_time) > check_every:
            try:
                requests.post(f"http://{server_ip}:{server_port}/login", json={"ip":tailscale_ip,
                                                                                "port":"5002",
                                                                                "name":socket.gethostname()})
                check_miner_versions()
            except requests.exceptions.ConnectionError:
                logger("Server offline ...")
            start_check_miner()
            last_check_time = time.time()
    
@app.route('/set_miner', methods=["POST"])
def set_new_miner():
    global current_Miner
    logger("Set new miner")
    miner_name = json.loads(request.data)["name"]
    logger(f"set new miner: {miner_name}")  
    if current_Miner is not None and current_Miner.name != miner_name:
        logger(f"set new miner: {miner_name}, {current_Miner.name}, {current_Miner.name != miner_name}")
        current_Miner.stop()
        if current_Miner.run_always: current_Miner.restart()
        
        current_Miner = miner_info_dict[miner_name]
        current_Miner.activate(json.loads(request.data))
    elif current_Miner is None:
        for name, miner in miner_info_dict.items():
            miner.stop()
        current_Miner = miner_info_dict[miner_name]
        current_Miner.activate(json.loads(request.data))
        
    return Response(status=200)
    
class ServerThread(threading.Thread):
    def __init__(self, app):
        threading.Thread.__init__(self)
        self.server = make_server(tailscale_ip, 5002, app)
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
    t = threading.Thread(target=main_run)
    t.start()
    start_server()
    t.join()
    logger("Thread ended")
    stop_server()
    
    for miner_name, miner in miner_info_dict.items():
        miner.kill()
    #

if __name__ == "__main__":
    run()