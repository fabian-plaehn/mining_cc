from mining_cc.client.client_class import Client
#the_program_to_hide = win32gui.GetForegroundWindow()
#win32gui.ShowWindow(the_program_to_hide , win32con.SW_HIDE)

def client_program():
    client = Client()
    client.run()


if __name__ == '__main__':
    client_program()  # Already an admin here.
