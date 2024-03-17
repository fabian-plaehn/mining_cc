import json
import os
import socket
import subprocess
import time
import threading
from flask import Flask, request, Response
import psutil
import requests
import platform

from mining_cc.shared.hashes import single_file_hash
from mining_cc.shared.utils import logger
app = Flask(__name__)

client_folder_name = "Client_Folder"
client_file_name = "client_main.exe"
server_ip = "100.96.210.95"
server_port = 5000
path_to_client_exe = f"{client_folder_name}/{client_file_name}"
client_process = None
os_system = platform.system().lower()

class Client_Info:
    def __init__(self, ip, port, name, time_stamp) -> None:
        self.ip = ip
        self.name = name
        self.port = port
        self.time_stamp = time_stamp
        
    def __eq__(self, __value: object) -> bool:
        return self.ip == __value.ip and self.name == __value.name and self.port == __value.port
        
    def __repr__(self) -> str:
        return f"{self.ip}/{self.port}/{self.name}"

def download_new_client():
    global client_process
    logger("downloading new client")
    if client_process is not None:
        logger("Shutting down client process")
        client_process.kill()
        while psutil.pid_exists(client_process.pid):
            pass
        client_process = None
    resp = requests.get(f"http://{server_ip}:{server_port}/{os_system}/new_client")
    if not resp.ok:
        return 
    fd = open(path_to_client_exe, "wb")
    fd.write(resp.content)
    fd.close()

def check_client_version():
    logger("checking client version")
    if not os.path.isdir(client_folder_name):
        os.mkdir(client_folder_name)
                
    if not os.path.isfile(f"{client_folder_name}/{client_file_name}"):
        download_new_client()
    else:
        resp = requests.get(f"http://{server_ip}:{server_port}/{os_system}/new_client_hash")
        if not resp.ok:
            return 
        server_hash = resp.content.decode()
        client_hash = single_file_hash(path_to_client_exe)
        logger(f"hash_server:  {server_hash}")
        logger(f"hash deamon: {client_hash}")
        if server_hash != client_hash:
            logger("Hash not equal")
            download_new_client()
        #self.client_socket.send(request_client_hash())
        
@app.route('/new_client_available', methods=["GET"])
def new_client_available():
    check_client_version()
    
def start_check_client():
    global client_process
    try:
        if client_process is None:
            client_process = subprocess.Popen(path_to_client_exe)
        if client_process is not None and not psutil.pid_exists(client_process.pid):
            client_process = None
    except FileNotFoundError:
        pass

def main_run():
    while True:
        try:
            requests.post(f"http://{server_ip}:{server_port}/login", json={"ip":socket.gethostbyname(socket.gethostname()),
                                                                            "port":"5001",
                                                                            "name":socket.gethostname() + "_deamon"})
            check_client_version()
        except requests.exceptions.ConnectionError:
            logger("Server offline ...")
        start_check_client()
        time.sleep(10)
    
def run():
    t = threading.Thread(target=main_run)
    t.start()
    app.run(socket.gethostbyname(socket.gethostname()), port=5001)

if __name__ == "__main__":
    run()
    