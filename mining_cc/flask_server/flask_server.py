import json
import os
import shutil
import socket
import time
import threading
from typing import List
from flask import Flask, request, Response, send_file, send_from_directory
import keyboard
import requests
from werkzeug.serving import make_server
from mining_cc.shared.hashes import dirhash, single_file_hash
from mining_cc.shared.utils import logger
app = Flask(__name__)
app.use_x_sendfile = True



server_folder_name = "Server_Folder"

client_file_name = "client_main"
deamon_file_name = "deamon_main"

path_to_client_windows = server_folder_name + "/windows/" + client_file_name + ".exe"
path_to_client_linux = server_folder_name + "/linux/" + client_file_name + ".bin"

path_to_deamon_windows = server_folder_name + "/windows/" + deamon_file_name + ".exe"
path_to_deamon_linux = server_folder_name + "/linux/" + deamon_file_name + ".bin"


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

client_list: List[Client_Info] = []

@app.route('/login', methods=["POST"])
def login_server():
    global client_list
    data = json.loads(request.data)
    client_info = Client_Info(data["ip"], data["port"], data["name"], time.time())
    if client_info not in client_list:
        print(f"New Client: {client_info}")
        client_list.append(client_info)
    return Response(status=200)


@app.route('/<os_version>/new_client', methods=["GET"])
def send_client(os_version):
    if os_version == "windows":
        path_to_client = path_to_client_windows
        filename = client_file_name + ".exe"
    elif os_version == "linux":
        path_to_client = path_to_client_linux
        filename = client_file_name + ".bin"
    else:
        return Response(400)
    return Response(open(path_to_client, "rb"), headers={"filename":filename})

@app.route('/<os_version>/new_client_hash', methods=["GET"])
def send_client_hash(os_version):
    if os_version == "windows":
        path_to_client = path_to_client_windows
        filename = client_file_name + ".exe"
    elif os_version == "linux":
        path_to_client = path_to_client_linux
        filename = client_file_name + ".bin"
    else:
        return Response(400)
        
    if not os.path.isfile(path_to_client):
        logger("client_main.exe not found")
        return 0
    hash = str(single_file_hash(path_to_client))
    
    print(f"Client Hash: {hash}")
    return Response(str(hash).encode(), headers={"filename":filename})

@app.route('/<os_version>/new_miner_hashes', methods=["GET"])
def send_miner_hashes(os_version):
    if os_version == "windows":
        server_folder = server_folder_name + "/windows"
    elif os_version == "linux":
        server_folder = server_folder_name + "/linux"
    else:
        return Response(400)
    
    hash_json = {}
    for file in os.listdir(server_folder):
        file_path = server_folder + "/" + file
        if not os.path.isdir(file_path):
            continue
        # is dir
        hash_d = dirhash(file_path, excluded_files=["config.json"])
        hash_json[file] = hash_d
    print(hash_json)
    return Response(str(hash_json).encode(), status=200)

@app.route('/<os_version>/new_miner', methods=["GET"])
def send_new_miner(os_version):
    if os_version == "windows":
        server_folder = server_folder_name + "/windows"
    elif os_version == "linux":
        server_folder = server_folder_name + "/linux"
    else:
        return Response(400)
    print(request.data)
    foldername = json.loads(request.data)["foldername"]
    shutil.make_archive(server_folder + "/" + foldername, "zip", server_folder + "/" + foldername)
    return Response(open(server_folder + "/" + foldername + ".zip", "rb"), status=200)


'''fd = open("my_file.exe", "wb")
fd.write(resp.content)
fd.close()'''
'''base_sheet["pools"][0]["algo"] = sheet.algo
base_sheet["pools"][0]["url"] = sheet.pool
base_sheet["pools"][0]["user"] = f"{sheet.user[self.farm_name]}"
base_sheet["pools"][0]["pass"] = sheet.password'''

def main_run():
    global client_list
    i = 0
    check_every = 10
    last_check_time = time.time() - check_every
    while True:
        if keyboard.is_pressed('q'):
            logger("shutting down detected")
            requests.get(f"http://{socket.gethostbyname(socket.gethostname())}:{5000}/shutdown")
            break
        if (time.time() - last_check_time) > check_every:
            for client in client_list:
                print(client)
                if "deamon" not in client.name:
                    try:
                        if i % 2 == 0:
                            requests.post(f"http://{client.ip}:{client.port}/set_miner", json={"name":"ZEPH", "pools":[{"algo": None, "pass":"test"}]})
                        else:
                            requests.post(f"http://{client.ip}:{client.port}/set_miner", json={"name":"XDAG", "pools":[{"algo": None, "pass":"test"}]})
                        i += 1
                    except requests.exceptions.ConnectionError:
                        logger("Client offline")
                        client_list.remove(client)
            print("clientlist: ", client_list)
            last_check_time = time.time()
    pass

# idea safe
@app.route("/get-pdf/<pdf_id>")
def get_pdf(pdf_id):
    pass

class ServerThread(threading.Thread):
    def __init__(self, app):
        threading.Thread.__init__(self)
        self.server = make_server(socket.gethostbyname(socket.gethostname()), 5000, app, threaded=True)
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
    global app
    t = threading.Thread(target=main_run)
    t.start()
    #app.run(socket.gethostbyname(socket.gethostname()), 5000)
    start_server()
    
    t.join()
    logger("Thread ended")
    stop_server()
    
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
    global app
    print("download deamon_received", os.getcwd() + "/" + path_to_client)
    return send_from_directory(directory=os.getcwd() + "/" + server_folder, path=filename,
                               as_attachment=True, download_name=filename,mimetype='application/x-binary')


if __name__ == "__main__":
    run()