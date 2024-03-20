import struct

ProtoHeader = struct.Struct("!HI")
Empty_Request = 0
LoginRequest = 1
ExitRequest = 2

Request_New_Client = 3
Request_Client_Hash = 4
Send_Client_Hash = 5
Send_Client_Info = 6
Send_Client_Data = 7
Send_Client_Finished = 8

Request_New_Folder = 9
Request_Miner_Hashes = 10
Send_Miner_Hashes = 11
Send_Folder_Info = 12
Send_Folder_Data = 13
Send_Folder_Finished = 14

Activate_Miner = 15
Send_Miner_Data = 16


def receive_bytes(conn, count):
    """ General purpose receiver:
        Receive exactly @count bytes from @conn """
    buf = b''
    remaining = count
    while remaining > 0:
        # Receive part or all of data
        tbuf = conn.recv(remaining)
        tbuf_len = len(tbuf)
        if tbuf_len == 0:
            # Really you probably want to return 0 here if buf is empty and
            # allow the higher-level routine to determine if the EOF is at
            # a proper message boundary in which case, you silently close the
            # connection. You would normally only raise an exception if you
            # EOF in the *middle* of a message.
            raise ConnectionResetError
        buf += tbuf
        remaining -= tbuf_len
    return buf


def receive_proto_block(conn):
    try:
        """ Receive the next protocol block from @conn. Return a tuple of
            request_type (integer) and payload (byte string) """

        proto_header = receive_bytes(conn, ProtoHeader.size)
        request_type, payload_length = ProtoHeader.unpack(proto_header)
        payload = receive_bytes(conn, payload_length)
    except BlockingIOError:
        return Empty_Request, None
    except (ConnectionResetError, ConnectionAbortedError, OSError):
        return ExitRequest, None

    return request_type, payload


def format_login_request(username):
    """ Create a protocol block containing a user login request.
        Return the byte string containing the encoded request """
    username_bytes = username.encode()
    proto_block = ProtoHeader.pack(LoginRequest, len(username_bytes)) + username_bytes
    return proto_block

def request_new_client(data):  # data {"OS_Version":OS_VERSION}
    data_b = str(data).encode()
    proto_block = ProtoHeader.pack(Request_New_Client, len(data_b)) + data_b
    return proto_block

def request_client_hash(data): # data {"OS_Version":OS_VERSION}
    data_b = str(data).encode()
    proto_block = ProtoHeader.pack(Request_Client_Hash, len(data_b)) + data_b
    return proto_block

def send_client_hash(data):
    data_b = str(data).encode()
    proto_block = ProtoHeader.pack(Send_Client_Hash, len(data_b)) + data_b
    return proto_block

def send_client_info(data):
    data_b = str(data).encode()
    proto_block = ProtoHeader.pack(Send_Client_Info, len(data_b)) + data_b
    return proto_block

def send_client_data(data):
    proto_block = ProtoHeader.pack(Send_Client_Data, len(data)) + data
    return proto_block

def send_client_finished():
    proto_block = ProtoHeader.pack(Send_Client_Finished, 0)
    return proto_block

def request_new_folder(data):  # {"OS_Version", "folder_name"}
    data_b = str(data).encode()
    proto_block = ProtoHeader.pack(Request_New_Folder, len(data_b)) + data_b
    return proto_block

def request_miner_hashes(data): # {"OS_Version":}
    data_b = str(data).encode()
    proto_block = ProtoHeader.pack(Request_Miner_Hashes, len(data_b)) + data_b
    return proto_block

def send_miner_hashes(data): 
    data_b = str(data).encode()
    proto_block = ProtoHeader.pack(Send_Miner_Hashes, len(data_b)) + data_b
    return proto_block

def send_folder_info(data):
    data_b = str(data).encode()
    proto_block = ProtoHeader.pack(Send_Folder_Info, len(data_b)) + data_b
    return proto_block

def send_folder_data(data):
    proto_block = ProtoHeader.pack(Send_Folder_Data, len(data)) + data
    return proto_block

def send_folder_finished():
    proto_block = ProtoHeader.pack(Send_Folder_Finished, 0)
    return proto_block

def send_pickle_data(Header, data):
    proto_block = ProtoHeader.pack(Header, len(data)) + data
    return proto_block