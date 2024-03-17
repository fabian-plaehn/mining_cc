import time

import PySimpleGUI as sg, sys
import requests
from datetime import datetime

def create_row(user, config):
    connections = config["Connections"]
    return [sg.Checkbox(f"{user}", key=f"checkbox_{user}"), sg.Text(connections[user]["Sheet"], key=f"sheet_{user}"),
           sg.Text("Offline", key=f"status_{user}"), sg.Text("Hashrate: ", key=f"hashrate_{user}")]


class Server_GUI:
    def __init__(self, config):
        sg.theme('DarkAmber')
        connections = config["Connections"]
        print(connections)
        col = []

        layout = [[sg.Button("SELECT ALL")], [sg.Button("DESELECT ALL")],
                  [sg.Column(col, size=(500, 300), scrollable=True, key="columns")],
                  [sg.Text("Miner_Sheet"), sg.OptionMenu(values=["XMR", "ZEPH", "MMR", "None"], default_value="XMR", key="Miner_Sheet"), sg.Button("Submit")],
                  [sg.Multiline(size=(60, 10), key="Terminal")],
                  [sg.Cancel('Exit')]
                  ]
        self.last_updated = time.time()
        self.update_every = 1
        self.form = sg.Window('Checkbox practice').Layout(layout)

    def update_window(self, config, connection_list=None):
        connections = config["Connections"]

        event, values = self.form.Read(timeout=2)
        for i, user in enumerate(connections):
            if f"checkbox_{user}" not in values:
                self.form.extend_layout(self.form["columns"], [create_row(user, config)])

    def handle(self, config):
        event, values = self.form.Read(timeout=2)
        connections = config["Connections"]

        if (time.time() - self.last_updated) > self.update_every:
            for i, user in enumerate(connections):
                if f"checkbox_{user}" in values:
                    try:
                        response = requests.get(f"http://{user}:8888/2/summary", timeout=(0.01, 0.1))
                        hashrate = response.json()["hashrate"]["total"][0]
                    except requests.exceptions.ConnectionError:
                        hashrate = 0
                    self.form[f"hashrate_{user}"].Update(f'{hashrate} H/s')
                    try:
                        self.form[f"status_{user}"].Update(f'{config["Connections"][user]["Last_seen"]} H/s')
                    except KeyError:
                        pass
            self.last_updated = time.time()

        if event == "SELECT ALL":
            for i, user in enumerate(connections):
                self.form[f"checkbox_{user}"].Update(True)
        if event == "DESELECT ALL":
            for i, user in enumerate(connections):
                self.form[f"checkbox_{user}"].Update(False)
        if event == "Submit":
            for i, user in enumerate(connections):
                if values[f"checkbox_{user}"]:
                    self.form[f"sheet_{user}"].Update(values["Miner_Sheet"])

        if event == "Exit":
            sys.exit()

    def print(self, msg):
        self.form["Terminal"].print(msg)

