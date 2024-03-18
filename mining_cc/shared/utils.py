import datetime
import json

import psutil


_debug = False
_info = True
_trace = False

def payload_to_dict(payload):
    try:
        payload = json.loads(payload.decode().replace("'", '"'))
    except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
        return payload
    return payload

def get_process_id_and_childen(pid: int, sig: int = 15):
    proc_id_list = []
    
    try:
        proc = psutil.Process(pid)
        proc_id_list.append(proc.pid)
    except psutil.NoSuchProcess as e:
        # Maybe log something here
        return
    for child_process in proc.children(recursive=True):
        proc_id_list.append(child_process.pid)
    return proc_id_list

def kill_process_and_children(pid: int, sig: int = 15):
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess as e:
        # Maybe log something here
        return

    for child_process in proc.children(recursive=True):
        try: child_process.send_signal(sig)
        except psutil.NoSuchProcess: pass
            
    try: proc.send_signal(sig)
    except psutil.NoSuchProcess: pass
    
def merge(a: dict, b: dict, path=[]):
    for key in b:
        if key in a:
            
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge(a[key], b[key], path + [str(key)])
            if isinstance(a[key], list) and isinstance(b[key], list):
                for i, element in enumerate(a[key]):
                    if isinstance(element, dict) and isinstance(b[key][i], dict):
                        a[key][i] = merge(element, b[key][i])
                        
            elif a[key] != b[key]:
                a[key] = b[key]
                #raise Exception('Conflict at ' + '.'.join(path + [str(key)]))
        else:
            a[key] = b[key]
    return a

def logger(info, level='info'):
    """
    Log output to the console (if verbose output is enabled)

    """
    import logging
    if not globals()[f'_{level}']:
        return

    logging.basicConfig(level=getattr(logging, level.swapcase()),
                        handlers=[logging.StreamHandler()])
    logger = logging.getLogger(__name__)
    currentDateAndTime = datetime.datetime.now()
    getattr(logger, level if hasattr(logger, level) else 'debug')(
        f"{currentDateAndTime.strftime('%H:%M:%S')}| " + str(info))