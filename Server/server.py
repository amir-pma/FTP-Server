from socket import *
import json
import threading
import os
import logging
import base64
import datetime
import traceback

class UserInfo:
    def __init__(self, size_, email_, alert_, workingDirectory_):
        self.size = size_
        self.email = email_
        self.alert = alert_
        self.workingDirectory = workingDirectory_

class Server(threading.Thread):
    CONFIG_FILE = "config.json"
    HOST = "localhost"
    CHUNK_SIZE = 10000
    MAIL_SERVER = ("mail.ut.ac.ir", 25)
    MAIL_FROM = "pourmohammadali@ut.ac.ir"
    MAIL_USER = "pourmohammadali\n"
    MAIL_PASS = "Amir@1214392"
    config = None
    usersInfo = {}
    fileDirectory = None

    def __init__(self):
        threading.Thread.__init__(self)
        Server.config = json.loads(open(self.CONFIG_FILE).read())
        Server.fileDirectory = os.getcwd()
        self.fillUsersInfo()
        logging.basicConfig(level=logging.INFO, 
                            format='%(asctime)s   %(levelname)s   %(message)s', 
                            datefmt='%Y-%m-%d %H:%M:%S',
                            filename=self.config['logging']['path'], 
                            filemode='a')
        
    def fillUsersInfo(self):
        for user in Server.config["accounting"]["users"]:
            Server.usersInfo[user["user"]] = UserInfo(int(user["size"]), user["email"], bool(user["alert"]), Server.fileDirectory)
        for user in Server.config["users"]:
            if(user["user"] not in Server.usersInfo):
                Server.usersInfo[user["user"]] = UserInfo(0, "", False, Server.fileDirectory)

    def run(self):
        self.log("Starting server...", True, None, None)
        self.configServerSockets()
        self.log("server listenning for new connections...", True, None, None)
        while(True):
            clientSocket, clientAddress = self.commandSocket.accept()
            self.log("Made new connection to server.", True, clientAddress, None)
            thread = ClientThread(clientAddress, clientSocket, self.dataSocket)
            thread.daemon = True
            thread.start()

    def configServerSockets(self):
        self.commandSocket = socket(AF_INET, SOCK_STREAM)
        self.commandSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.commandSocket.bind((self.HOST, self.config['commandChannelPort']))
        self.commandSocket.listen()
        self.dataSocket = socket(AF_INET, SOCK_STREAM)
        self.dataSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.dataSocket.bind((self.HOST, self.config['dataChannelPort']))
        self.dataSocket.listen()

    @staticmethod
    def log(message, type, clientAddress, username):
        if(username != None):
            logMessage = username + " -> " + message
        elif(clientAddress != None):
            logMessage = "Client" + str(clientAddress) + " -> " + message
        else:
            logMessage = message
        print(logMessage)
        if(Server.config['logging']['enable']):
            if(type):
                logging.info(logMessage)
            else:
                logging.error(logMessage)


class ClientThread(threading.Thread):
    def __init__(self, clientAddress_, clientSocket_, dataSocket_):
        threading.Thread.__init__(self)
        self.clientAddress = clientAddress_
        self.clientSocket = clientSocket_
        self.dataSocket = dataSocket_
        self.isLoggedIn = False
        self.hasEnteredUsername = False
        self.userName = ""
        self.isAccountingEnable = False
        self.isDataSocketConnected = False

    def __del__(self):
        self.clientSocket.close()

    def run(self):
        try:
            while(True):
                command = self.clientSocket.recv(Server.CHUNK_SIZE).decode()
                self.parseCommand(command)
        except (ConnectionResetError, ConnectionAbortedError) as e:
            Server.log("Disconnected from server.".format(self.clientAddress), True, self.clientAddress, self.getUserName())
        except Exception as e:
            Server.log("Error -> " + str(e), False , self.clientAddress, self.getUserName())
            traceback.print_exc()
            self.clientSocket.sendall("500 Error.".encode())
            self.run()

    def getUserName(self):
        if(self.isLoggedIn):
           return self.userName
        else:
            return None

    def sendSyntaxError(self, command):
        Server.log("Had syntax error in command (" + command + ").", False, self.clientAddress, self.getUserName())
        self.clientSocket.sendall("501 Syntax error in parameters or arguments.".encode())

    def checkArgumentsNum(self, args, validNums, command):
        if(len(args) not in validNums):
            self.sendSyntaxError(command)
            return False
        return True

    def checkIfLoggedIn(self):
        if(not self.isLoggedIn):
            Server.log("Used command that needed login.", False, self.clientAddress, None)
            self.clientSocket.sendall("332 Need account for login.".encode())
            return False
        else:
            return True

    def parseCommand(self, command):
        parsed = command.split()
        if((parsed[0] == "USER") and self.checkArgumentsNum(parsed, (2,), command)):
            self.handleUser(parsed)
        elif((parsed[0] == "PASS") and self.checkArgumentsNum(parsed, (2,), command)):
            self.handlePass(parsed)
        elif((parsed[0] == "QUIT") and self.checkArgumentsNum(parsed, (1,), command)):
            self.handleQuit()
        elif((parsed[0] == "HELP") and self.checkArgumentsNum(parsed, (1,), command)):
            self.handleHelp()
        elif((parsed[0] == "PWD") and self.checkArgumentsNum(parsed, (1,), command)):
            self.handlePrintWorkingDirectory()
        elif((parsed[0] == "CWD") and self.checkArgumentsNum(parsed, (1,2), command)):
            self.handleChangeWorkingDirectory(parsed)
        elif(parsed[0] == "LIST"):
            self.handleList(command, lambda: len(parsed) == 1)
        elif(parsed[0] == "DL"):
            self.handleDownload(parsed, command, lambda: len(parsed) == 2)
        elif(parsed[0] == "MKD"):
            if((len(parsed) == 2) or ((len(parsed) == 3) and (parsed[1] == "-i"))):
                self.handleMakeDirectory(parsed)
            else:
                self.sendSyntaxError(command)
        elif(parsed[0] == "RMD"):
            if((len(parsed) == 2) or ((len(parsed) == 3) and (parsed[1] == "-f"))):
                self.handleRemoveDirectory(parsed)
            else:
                self.sendSyntaxError(command)
        else:
            Server.log("Entered command that is not implemented.", False, self.clientAddress, self.getUserName())
            self.clientSocket.sendall("502 Command not found.".encode())


    def handleUser(self, parsedCommand):
        username = parsedCommand[1]
        if(self.isLoggedIn):
            Server.log("Entered username (" + username + ") but was already logged in.", True, self.clientAddress, self.userName)
            self.clientSocket.sendall("503 You are already logged in.".encode())
            return
        self.userName = username
        self.hasEnteredUsername = True
        Server.log("Entered username (" + username + ")", True, self.clientAddress, None)
        self.clientSocket.sendall("331 User name okay, need password.".encode())

    def handlePass(self, parsedCommand):
        password = parsedCommand[1]
        if(not self.hasEnteredUsername):
            Server.log("Entered password (" + password + ") but username wasn't entered first.", False, self.clientAddress, self.getUserName())
            self.clientSocket.sendall("503 Bad sequence of commands.".encode())
            return
        user = self.findUser(self.userName, password)
        self.hasEnteredUsername = False
        if(user == None):
            Server.log("Entered password (" + password + ") but username or password was wrong.", False, self.clientAddress, None)
            self.clientSocket.sendall("430 Invalid username or password.".encode())
            return
        self.isLoggedIn = True
        self.isAccountingEnable = self.checkIfAccountingIsEnable()
        Server.log("Logged in with username (" + self.userName + ") and password (" + password + ").", True, self.clientAddress, None)
        self.clientSocket.sendall("230 User logged in, proceed.".encode())

    def handleQuit(self):
        if(not self.checkIfLoggedIn()):
            return
        self.isLoggedIn = False
        self.hasEnteredUsername = False
        self.isAccountingEnable = False
        Server.usersInfo[self.userName].workingDirectory = Server.fileDirectory
        Server.log("Logged out successfully on address " + str(self.clientAddress) + ".", True, self.clientAddress, self.userName)
        self.clientSocket.sendall("221 Successful Quit.".encode())

    def handleHelp(self):
        Server.log("Got help message.", True, self.clientAddress, self.getUserName())
        response = "214\n"
        response += "USER [name], Its argument is used to specify the user's string. It is used for user authentication.\n"
        response += "PASS [password], Its argument is used to specify the user's password. It is used for user authentication.\n" 
        response += "PWD, It is used for printing current working directory\n" 
        response += "CWD [path], Its argument is used to specify the directory's path. It is used for changing the current working directory.\n" 
        response += "MKD [flag] [name], Its name argument is used to specify the file/directory path. It will create a new file if the -i flag is present and a new directory, if not. It is used for creating a new file or directory.\n" 
        response += "RMD [flag] [name], Its name argument is used to specify the file/directory path. It will remove the specified directory if the -f flag is present and the specified file, if not. It is used for removing a file or directory.\n" 
        response += "LIST, It is used for printing a list of all file/directories that are in the current working directory\n" 
        response += "DL [name], Its argument is used to specify the file's name. It is used for downloading a file.\n" 
        response += "HELP, It is used for printing the list of availibale commands and how to use them.\n" 
        response += "QUIT, It is used for logging out from the server."
        self.clientSocket.sendall(response.encode())
    
    def handlePrintWorkingDirectory(self):
        if(not self.checkIfLoggedIn()):
            return
        workingDirectory = (Server.usersInfo[self.userName]).workingDirectory
        response = "257 " + workingDirectory
        Server.log("Got working directory (" + workingDirectory + ").", True, self.clientAddress, self.userName)
        self.clientSocket.sendall(response.encode())

    def handleChangeWorkingDirectory(self, parsedCommand):
        if(not self.checkIfLoggedIn()):
            return
        if(len(parsedCommand) == 1):
            newDirectoryPath = Server.fileDirectory
        else:
            newDirectoryPath = parsedCommand[1]
        try:
            os.chdir(Server.usersInfo[self.userName].workingDirectory)
            os.chdir(newDirectoryPath)
            newWorkingDirectory = os.getcwd()
            Server.usersInfo[self.userName].workingDirectory = newWorkingDirectory
            Server.log("Changed working directory to (" + newWorkingDirectory + ").", True, self.clientAddress, self.userName)
            self.clientSocket.sendall("250 Successful Change.".encode())
        except:
            Server.log("Wanted to changed working directory to (" + newDirectoryPath + ") but the path is invalid.", False, self.clientAddress, self.userName)
            self.clientSocket.sendall("550 No such file or directory.".encode())

    def handleMakeDirectory(self, parsedCommand):
        if(not self.checkIfLoggedIn()):
            return
        try:
            path = os.path.join(Server.usersInfo[self.userName].workingDirectory, parsedCommand[-1])
            if(not self.checkAdminAuthorization(path)):
                Server.log("Wanted to create file/directory (" + path + ") but it needed admin authorization.", False, self.clientAddress, self.userName)
                self.clientSocket.sendall("550 File unavailable.".encode())
            elif(os.path.exists(path)):
                Server.log("Wanted to create file/directory (" + path + ") but it already existed.", False, self.clientAddress, self.userName)
                self.clientSocket.sendall("550 File/Directory already exists.".encode())
            else:
                if(len(parsedCommand) == 2):
                    os.mkdir(path)
                else:
                    open(path, 'x')
                Server.log("Successfully created file/directory with path (" + path + ").", True, self.clientAddress, self.userName)
                response = "257 " + path + " created."
                self.clientSocket.sendall(response.encode())
        except:
            Server.log("Wanted to create directory (" + path + ") but name was invalid or the directories in path didn't exist.", False, self.clientAddress, self.userName)
            traceback.print_exc()
            self.clientSocket.sendall("550 File/Directory names in path are invalid or do not exist.".encode())

    def handleRemoveDirectory(self, parsedCommand):
        if(not self.checkIfLoggedIn()):
            return
        path = os.path.join(Server.usersInfo[self.userName].workingDirectory, parsedCommand[-1])
        if(not self.checkAdminAuthorization(path)):
            Server.log("Wanted to remove file/directory (" + path + ") but it needed admin authorization.", False, self.clientAddress, self.userName)
            self.clientSocket.sendall("550 File unavailable.".encode())
        elif(not os.path.exists(path)):
            Server.log("Wanted to remove file/directory (" + path + ") but it didn't existed.", False, self.clientAddress, self.userName)
            self.clientSocket.sendall("550 File/Directory doesn't exists.".encode())
        else:
            if(len(parsedCommand) == 3):
                if(not os.path.isdir(path)):
                    Server.log("Wanted to removed file with path (" + path + ") but used command for removing directory.", False, self.clientAddress, self.userName)
                    self.clientSocket.sendall("553 This command is for deleting directory not file.".encode())
                else:
                    try:
                        os.rmdir(path)
                        Server.log("Successfully removed directory with path (" + path + ").", True, self.clientAddress, self.userName)
                        response = "250 " + path + " deleted."
                        self.clientSocket.sendall(response.encode())
                    except:
                        Server.log("Wanted to removed directory with path (" + path + ") but it wasn't empty.", False, self.clientAddress, self.userName)
                        self.clientSocket.sendall("10066 Directory not empty.".encode())
            else:
                if(os.path.isdir(path)):
                    Server.log("Wanted to removed directory with path (" + path + ") but used command for removing file.", False, self.clientAddress, self.userName)
                    self.clientSocket.sendall("553 This command is for deleting file not directory.".encode())
                else:
                    os.remove(path)
                    Server.log("Successfully removed file with path (" + path + ").", True, self.clientAddress, self.userName)
                    response = "250 " + path + " deleted."
                    self.clientSocket.sendall(response.encode())

    def handleList(self, command, syntaxChecker):
        isConnected = self.initializeDataConnection(command, syntaxChecker, False, None)
        if(isConnected):
            data = ""
            workingDirectory = Server.usersInfo[self.userName].workingDirectory
            for file in os.listdir():
                path = os.path.join(workingDirectory, file)
                if(self.checkAdminAuthorization(path)):
                    data += file + "\n"
            self.sendData(data)
            Server.log("Recieved file/directories list.", True, self.clientAddress, self.userName)
            self.clientSocket.sendall("226 List transfer done.".encode())

    def handleDownload(self, parsedCommand, command, syntaxChecker):
        isConnected = self.initializeDataConnection(command, syntaxChecker, True, parsedCommand[-1])
        if(isConnected):
            path = os.path.join(Server.usersInfo[self.userName].workingDirectory, parsedCommand[-1])
            file = open(path, "rb")
            if(self.isAccountingEnable):
                remainingCredit = Server.usersInfo[self.userName].size - os.path.getsize(path)
                Server.usersInfo[self.userName].size = remainingCredit
            readOutput = file.read(Server.CHUNK_SIZE)
            while(readOutput):
                self.clientDataSocket.sendall(readOutput)
                readOutput = file.read(Server.CHUNK_SIZE)
            self.clientDataSocket.close()
            self.isDataSocketConnected = False
            file.close()
            Server.log("Downloaded file (" + path + ").", True, self.clientAddress, self.userName)
            self.clientSocket.sendall("226 Successful Download.".encode())
            if(self.isAccountingEnable and (remainingCredit < Server.config["accounting"]["threshold"]) and Server.usersInfo[self.userName].alert):
                self.sendLowCreditEmail()
    
    def initializeDataConnection(self, command, syntaxChecker, isDownload, fileName):
        if(not self.isDataSocketConnected):
            self.clientDataSocket, clientDataAddress = self.dataSocket.accept()
        checkingAddress = self.clientDataSocket.recv(Server.CHUNK_SIZE).decode()
        if(not syntaxChecker()):
            self.clientDataSocket.sendall("1".encode())
            Server.log("Had syntax error in command (" + command + ").", False, self.clientAddress, self.getUserName())
            self.clientSocket.sendall("501 Syntax error in parameters or arguments.".encode())
            return False
        elif(not self.isLoggedIn):
            self.clientDataSocket.sendall("2".encode())
            Server.log("Used command that needed login.", False, self.clientAddress, None)
            self.clientSocket.sendall("332 Need account for login.".encode())
            return False
        elif(checkingAddress != str(self.clientAddress)):
            self.clientDataSocket.sendall("3".encode())
            return self.initializeDataConnection()
        elif(isDownload):
            path = os.path.join(Server.usersInfo[self.userName].workingDirectory, fileName)
            if(not self.checkAdminAuthorization(path)):
                self.clientDataSocket.sendall("4".encode())
                Server.log("Wanted to download file (" + path + ") but it needed admin authorization.", False, self.clientAddress, self.userName)
                self.clientSocket.sendall("550 File unavailable.".encode())
                return False
            elif(not os.path.exists(path)):
                self.clientDataSocket.sendall("5".encode())
                Server.log("Wanted to download file (" + path + ") but it didn't existed.", False, self.clientAddress, self.userName)
                self.clientSocket.sendall("550 File doesn't exists.".encode())
                return False
            elif(os.path.isdir(path)):
                self.clientDataSocket.sendall("6".encode())
                Server.log("Wanted to download file with path (" + path + ") that was a folder.", False, self.clientAddress, self.userName)
                self.clientSocket.sendall("552 Cant download folder.".encode())
                return False
            remainingCredit = Server.usersInfo[self.userName].size - os.path.getsize(path)
            if(self.isAccountingEnable and (remainingCredit < 0)):
                self.clientDataSocket.sendall("7".encode())
                Server.log("Wanted to download file with path (" + path + ") but didn't have enough credit.", False, self.clientAddress, self.userName)
                self.clientSocket.sendall("425 Can't open data connection.".encode())
                return False
        self.isDataSocketConnected = True
        self.clientDataSocket.sendall("8".encode())
        self.clientDataSocket.recv(Server.CHUNK_SIZE)
        return True
            
    def sendData(self, data):
        while(True):
            if(len(data) > Server.CHUNK_SIZE):
                sendingData = data[:Server.CHUNK_SIZE]
                data = data[Server.CHUNK_SIZE:]
                self.clientDataSocket.sendall(sendingData.encode())
            else:
                self.clientDataSocket.sendall(data.encode())
                break
        self.clientDataSocket.sendall("--done--".encode())

    def sendLowCreditEmail(self):
        Server.log("(MAIL) Sending low credit mail...", True, self.clientAddress, self.userName)
        mailSocket = socket(AF_INET, SOCK_STREAM)
        mailSocket.connect(Server.MAIL_SERVER)
        response = mailSocket.recv(Server.CHUNK_SIZE).decode()
        if(response[:3] != "220"):
            Server.log("(MAIL) 220 reply not received from server.", False, self.clientAddress, self.userName)
            return mailSocket.close()
        mailSocket.sendall("HELO FTPServer\n".encode())
        response = mailSocket.recv(Server.CHUNK_SIZE).decode()
        if(response[:3] != "250"):
            Server.log("(MAIL) 250 reply not received from server.", False, self.clientAddress, self.userName)
        mailSocket.sendall("AUTH LOGIN\n".encode())
        response = mailSocket.recv(Server.CHUNK_SIZE).decode()
        if(response[:3] not in ["250", "334"]):
            Server.log("(MAIL) 250 reply not received from server.", False, self.clientAddress, self.userName)
            return mailSocket.close()
        user = base64.b64encode(Server.MAIL_USER.encode()) + "\n".encode()
        password = base64.b64encode(Server.MAIL_PASS.encode()) + "\n".encode()
        mailSocket.sendall(user)
        response = mailSocket.recv(Server.CHUNK_SIZE).decode()
        if(response[:3] != "334"):
            Server.log("(MAIL) 334 reply not received from server.", False, self.clientAddress, self.userName)
            return mailSocket.close()
        mailSocket.sendall(password)
        response = mailSocket.recv(Server.CHUNK_SIZE).decode()
        if(response[:3] != "235"):
            Server.log("(MAIL) 235 reply not received from server.", False, self.clientAddress, self.userName)
            return mailSocket.close()
        mailSocket.sendall(("MAIL FROM: <\"" + Server.MAIL_FROM + "\">\n").encode())
        response = mailSocket.recv(Server.CHUNK_SIZE).decode()
        if(response[:3] != "250"):
            Server.log("(MAIL) 250 reply not received from server.", False, self.clientAddress, self.userName)
            return mailSocket.close()
        mailSocket.sendall(("RCPT TO: <\"" + Server.usersInfo[self.userName].email + "\">\n").encode())
        response = mailSocket.recv(Server.CHUNK_SIZE).decode()
        if(response[:3] != "250"):
            Server.log("(MAIL) 250 reply not received from server.", False, self.clientAddress, self.userName)
            return mailSocket.close()
        mailSocket.sendall("DATA\n".encode())
        response = mailSocket.recv(Server.CHUNK_SIZE).decode()
        if(response[:3] != "354"):
            Server.log("(MAIL) 354 reply not received from server.", False, self.clientAddress, self.userName)
            return mailSocket.close()
        data = "from: FTPServer <FTPServer@ftpserver.com>\n"
        data += "to: " + Server.usersInfo[self.userName].email + "\n"
        data += "subject: FTP Server low credit\n\n"
        data += "Your credit in ftp server is " + str(int(Server.usersInfo[self.userName].size/1000))
        data += "KB and it's less than the minimum threshold value."
        data += "Please add to your credit if you want to continue using our server.\n"
        data += "Have a nice day!\n\n"
        data += datetime.datetime.now().strftime("%d,%B,%Y  %I:%M%p")
        data += "\r\n.\r\n"
        mailSocket.sendall(data.encode())
        response = mailSocket.recv(Server.CHUNK_SIZE).decode()
        if(response[:3] != "250"):
            Server.log("(MAIL) 250 reply not received from server.", False, self.clientAddress, self.userName)
            return mailSocket.close()
        mailSocket.sendall("QUIT\n".encode())
        response = mailSocket.recv(Server.CHUNK_SIZE).decode()
        if(response[:3] != "221"):
            Server.log("(MAIL) 221 reply not received from server.", False, self.clientAddress, self.userName)
            return mailSocket.close()
        Server.log("(MAIL) Low credit mail sent successfully with credit " + str(Server.usersInfo[self.userName].size) +".", True, self.clientAddress, self.userName)
        mailSocket.close()

    def findUser(self, username, password):
        for user in Server.config["users"]:
            if((user["user"] == username) and (user["password"] == password)):
                return user
        return None
    
    def checkIfAccountingIsEnable(self):
        if(not Server.config["accounting"]["enable"]):
            return False
        for user in Server.config["accounting"]["users"]:
            if(self.userName == user["user"]):
                return True
        return False
    
    def checkAdminAuthorization(self, path):
        if(not Server.config["authorization"]["enable"]):
            return True
        os.chdir(Server.fileDirectory)
        for filePath in Server.config["authorization"]["files"]:
            if(os.path.abspath(filePath) == path):
                return self.checkIfAdmin()
        return True

    def checkIfAdmin(self):
        if(not Server.config["authorization"]["enable"]):
            return True
        elif(self.userName in Server.config["authorization"]["admins"]):
            return True
        else:
            return False


def start():
    try:
        server = Server()
        server.daemon = True
        server.start()
        while(server.is_alive()):
            pass
    except KeyboardInterrupt:
        Server.log("Server stopped.", True, None, None)
        

start()