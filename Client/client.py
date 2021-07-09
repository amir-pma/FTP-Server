from socket import *
import threading
import time
import os

class Client(threading.Thread):
    HOST = "localhost"
    SERVER_COMMAND_PORT = 8000
    SERVER_DATA_PORT = 8001
    CHUNK_SIZE = 10000

    def __init__(self):
        threading.Thread.__init__(self)
        self.dataSocketConnected = False

    def __del__(self):
        self.commandSocket.close()
        self.dataSocket.close()

    def run(self):
        self.configClientSocket()
        while(True):
            command = input()
            self.parseCommand(command)

    def configClientSocket(self):
        print("Connecting to server...")
        self.commandSocket = socket(AF_INET, SOCK_STREAM)
        self.dataSocket = socket(AF_INET, SOCK_STREAM)
        while(True):
            try:
                self.commandSocket.connect((self.HOST, self.SERVER_COMMAND_PORT))
                self.clientAddress = self.commandSocket.getsockname()
                print("Connected to server!")
                break
            except ConnectionRefusedError:
                print("Server not found, trying again...")
                time.sleep(2)

    def parseCommand(self, command):
        if(command == ""):
            return
        self.commandSocket.sendall(command.encode())
        parsed = command.split()
        if(parsed[0] == 'LIST'):
            self.handleList()
        elif(parsed[0] == 'DL'):
            self.handleDownload(parsed)
        else:
            self.handleGeneral(command)

    def handleGeneral(self, command):
        response = self.commandSocket.recv(self.CHUNK_SIZE).decode()
        print(response)

    def handleList(self):
        isConnected = self.initializeDataConnection()
        if(isConnected):
            recievedData = "\n" + self.recieveData()
            response = self.commandSocket.recv(self.CHUNK_SIZE).decode()
            print(response)
            print(recievedData)
        
    def handleDownload(self, parseCommand):
        isConnected = self.initializeDataConnection()
        if(isConnected):
            path = os.path.abspath(parseCommand[-1])
            if(os.path.exists(path)):
                os.remove(path)
            file = open(path, "wb")
            while(True):
                recieved = self.dataSocket.recv(self.CHUNK_SIZE)
                if(not recieved):
                    break
                file.write(recieved)
            file.close()
            self.dataSocketConnected = False
            response = self.commandSocket.recv(self.CHUNK_SIZE).decode()
            print(response)

    def initializeDataConnection(self):
        if(not self.dataSocketConnected):
            self.dataSocket.close()
            self.dataSocket = socket(AF_INET, SOCK_STREAM)
            self.dataSocket.connect((self.HOST, self.SERVER_DATA_PORT))
        self.dataSocket.sendall((str(self.clientAddress)).encode())
        response = self.dataSocket.recv(self.CHUNK_SIZE).decode()
        if(int(response) in (1, 2, 4, 5, 6, 7)):
            response = self.commandSocket.recv(self.CHUNK_SIZE).decode()
            print(response)
            return False
        elif(int(response) == 3):
            return self.handleList()
        else:
            self.dataSocketConnected = True
            self.dataSocket.sendall("ok".encode())
            return True

    def recieveData(self):
        data = []
        recieved = ""
        while(True):
            recieved = self.dataSocket.recv(self.CHUNK_SIZE).decode()
            if(recieved == "--done--"):
                break
            else:
                data.append(recieved)
        return "".join(data)


def run():
    try:
        client = Client()
        client.daemon = True
        client.start()
        while(client.is_alive()):
            pass
    except KeyboardInterrupt:
        pass
    print("\nbye bye!!!")


run()