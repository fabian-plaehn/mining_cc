import time
import psutil

if __name__ == '__main__':

    for pids in psutil.pids():
        try:
            psutil.pid_exists(pids)
            p = psutil.Process(pids)
            print(p.name(), p.pid, p.is_running(), p.cpu_percent())
        except psutil.NoSuchProcess:
            pass