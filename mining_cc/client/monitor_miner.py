import requests
import json
import os
import sys
import psutil
import signal
import time
import datetime
import subprocess
from datetime import datetime

BoxName = 'MyAwesomeBox'
MinerFolder = 'C:\\Users\\User\\Desktop\\Miner\\'
MinerCommand = 'xmrig -c zeph_config.json'
MinerRemoteAddress = 'http://127.0.0.1:58001/2/summary'

MinHashRate = "8400"


SlackUser = "slack_username"
SlackChannel = "#slack_channel"
SlackToken = "slack_token"

'''
    Applying GPU settings, Currently only applying OverDrive Tools.
    If you are using AMD BlockChain Driver, you might need to add restart GPU here
'''

def startMiner():

    print('Starting XMRig instance')
    sendSlack('%s Starting Miner Instance' % (BoxName))
    return subprocess.Popen('%s\%s' % (MinerFolder, MinerCommand), cwd=MinerFolder)


'''
    Killing miner using psutil
'''


def killMiner():
    print('Stoping XMRig')
    sendSlack('%s Stopping Miner Instance' % (BoxName))
    for proc in psutil.process_iter():
        if proc.name() == "xmrig-amd.exe":
            proc.kill()


'''
    Sending message to slack
'''


def sendSlack(message):
    print("send slack", message)


'''
    Restarting miner instance
'''


def restart():
    killMiner()
    #applySettings()
    startMiner()


'''
    Stopping miner instance
'''


def shutdown(signal, number):
    killMiner()


'''
    Rebooting machine
'''


def reboot():
    killMiner()
    # subprocess.call(["shutdown", "/r", "/t", "5"])
    sys.exit()


'''
    Main Loop
'''


def main():
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    minute = 0
    shares = 0
    restarted = 0

    restart()
    while True:
        time.sleep(2)
        if restarted > 5:
            sendSlack('Rebooting box because failed to initialize miner or gpu properly')
            reboot()

        try:
            request = requests.get(MinerRemoteAddress)
            if not request.status_code or request.status_code != 200:
                sendSlack('Restarting miner because failed to connect to miner properly')
                restarted += 1
                restart()
            else:
                break

        except Exception as e:
            sendSlack('Restarting miner due to error: %s' % (str(e)))
            restarted += 1
            restart()

    time.sleep(30)

    while True:
        try:
            request = requests.get(MinerRemoteAddress)
            if request.status_code == 200:
                data = json.loads(request.text)

                # Check hashrate every 1 minute
                if data and data.get('hashrate', False) and data.get('hashrate').get('total'):
                    if int(MinHashRate) > int(data.get('hashrate').get('total')[0]):
                        sendSlack('Restarting miner due to low hashrate detected')
                        #restart()

                # Check number of shares every 20 minutes
                minute = minute + 1
                if minute == 20:
                    if int(shares) == int(data['results']['shares_good']):
                        sendSlack('Restarting miner due to low shares detected')
                        #restart()

                    else:
                        shares = data['results']['shares_good']
                        minute = 0

            if not request.status_code or request.status_code != 200:
                sendSlack('Restarting miner due to invalid server request detected')
                #restart()


        except Exception as e:
            sendSlack('Restarting miner due to error while spying: %s' % (str(e)))
            #restart()

        time.sleep(60)


if __name__ == "__main__":
    main()

os.system('pause')