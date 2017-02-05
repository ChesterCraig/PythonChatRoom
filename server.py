import socket
import select
import sqlite3
import sys
import os

#Constant to store packet size
PACKET_SIZE = 1024 

"""
Server can be run as normal will use default ports 5000/5001

1 arg <alternate client port>
alternate host for clients (to allow multiple servers to run on a single machine)

2 args <alternate client port> <alternate server port>
alternate host for clients to connect too
alternate server port (to allow multiple servers to listen for incoming server conenctions on same machine)

3 args <alternate client port> <alternate server port> <known ip-port for active server>
alternate host for clients to connect too
alternate server port
known server addr/port to begin communicating with another server
"""


def run_server():
    """
    Start a server to facilitate the chat between clients.
    The server uses a single socket to accept incoming client connections
    which are then added to a list (socket_list) and are listened to
    to recieve incoming messages. Messages are then stored in a database
    and are transmitted back out to the clients.
    """

    # Define default listener location for incoming client requests
    client_host = "127.0.0.1"
    client_port = 5000         #Client port can be overridden with argument 1
    
    # Define default listener location for incoming server requests
    serv_host = "127.0.0.1"
    serv_port = 5001           #Server port can be overridden with argument 2


    # Define object for our databse, cannot create database until we know our serv_host and serv_port
    c = None
    #Create list to manage all of the client sockets
    socket_list = []
    #Create list to hold all fellow server sockets (doesn't include self)
    serv_socket_list = []
    #Create list to hold our listening sockets
    listen_socket_list = []

    #validate and act on any arguments.
    if len(sys.argv) == 1:
        #no arguments, use defaults
        c = create_database(serv_host,serv_port)
    elif len(sys.argv) == 2 and sys.argv[1].isdigit():
        #Alternate client port provided
        client_port = int(sys.argv[1])
        c = create_database(serv_host,serv_port)

    elif len(sys.argv) == 3 and sys.argv[1].isdigit() and sys.argv[2].isdigit():
        #Alternate client port and serv port
        client_port = int(sys.argv[1])
        serv_port = int(sys.argv[2])
        c = create_database(serv_host,serv_port)

    elif len(sys.argv) == 4 and sys.argv[1].isdigit() and sys.argv[2].isdigit():
        #Alternate client port, serv port and known server address provided
        client_port = int(sys.argv[1])
        serv_port = int(sys.argv[2])
        c = create_database(serv_host,serv_port)

        usr_defined_serv = sys.argv[3].split("-")
        if usr_defined_serv[1].isdigit() == False:
            print("#Known server port provided is invalid, aborting")
            return

        # Connect to and add server to db/servr list. Then shares theis server with servers.
        add_server(usr_defined_serv[0],int(usr_defined_serv[1]),serv_socket_list,c) 
    else:
        print("#Error, too many or invalid arguments provided.")
        return

    print("#Incoming client connections to %s" % (str(client_host) + "-" + str(client_port)))
    print("#Incoming server connections to %s" % (str(serv_host) + "-" + str(serv_port)))
      

    # Create a socket for the server to listen for connecting clients
    server_socket = socket.socket()
    server_socket.bind((client_host, client_port))
    server_socket.listen(10)
  
    # Create a socket for the server to listen for connecting servers
    srv_server_socket = socket.socket()
    srv_server_socket.bind((serv_host, serv_port))
    srv_server_socket.listen(10)

    # Add both listener sockets to the listen_socket_list
    listen_socket_list.append(server_socket)
    listen_socket_list.append(srv_server_socket)


    # Start listening for input from both the server socket and the clients
    while True:
        # Monitor all of the sockets in socket_list and serv_socket_list until something happens
        ready_to_read, ready_to_write, in_error = select.select(listen_socket_list + socket_list + serv_socket_list, [], [], 0)

        # When something happens, check each of the ready_to_read sockets
        for sock in ready_to_read:

            # A new client connection request recieved
            if sock == server_socket:
                # Accept the new socket request
                sockfd, addr = server_socket.accept()
                # Add the socket to the list of client and listener sockets to monitor
                socket_list.append(sockfd)
                # Log what has happened on the server
                print ("#Client (%s, %s) connected" % (addr[0],addr[1]))
                #add new client to gloabl chat room
                assign_to_global_room(sockfd,c,serv_socket_list,serv_port)

            # A new server connection request recieved
            elif sock == srv_server_socket:
                # Accept the new socket request
                sockfd, addr = srv_server_socket.accept()
                # Insert incomplete server record to database and request servers server listener port
                add_incomplete_serv(sockfd,c)
                #update this server with all known servers
                distribute_known_servers(sockfd,c)
                #update this sever with all known client rooms and usernames
                distribute_known_clients(sockfd,c,serv_port)
                # Add the socket to the list of server sockets to monitor
                serv_socket_list.append(sockfd)
                # Log what has happened on the server
                print ("#Server (%s, %s) connected. Require new servers listener port" % (addr[0],addr[1]))

            else:
                # Extract the data from the socket
                rawMsg = sock.recv(PACKET_SIZE)
                msg = rawMsg.decode().strip()

                #Detect disconnection
                if (str(rawMsg) == "b''"):
                    if sock in serv_socket_list:
                        print("#Server disconnected - %s" % get_sock_unique_id(sock))
                        # Remove server socket                                              #<~~ Does this update other servers??
                        serv_socket_list.remove(sock)
                        remove_serv(sock,c) 
                    else:
                        print("#Client disconnected - %s" % get_sock_unique_id(sock))
                        socket_list.remove(sock)
                        remove_client_from_db(sock,c)
                        #inform all other servers that this client has disconnected
                        for serv in serv_socket_list:
                            serv.send(("/SERVCLIENTDISC-%s" % get_sock_unique_id(sock)).encode())
                    continue

                if sock in serv_socket_list:
                    # Recieved a message from a server
                    # Print message out on server to monitor communications.
                    print("#from another server: %s" % msg.strip())

                    # Detect and execute passed server command
                    if "/ADDSERVER" in msg:
                        # Parse message and add server into serv_socket_list - we have been provided with listener port
                        servArgs = msg.split("-")
                        add_server(servArgs[1],int(servArgs[2]),serv_socket_list,c)
                    elif "/WHATLISTENERPORT" in msg:
                        sock.send(("/MYLISTENERPORT-%s" % str(serv_port)).encode())
                    elif "/MYLISTENERPORT" in msg:
                        update_server_record(sock,msg,serv_socket_list,c)
                    elif "/SERVNEWCLIENT" in msg:
                        serv_add_new_client(sock,msg,c,serv_socket_list)
                    elif "/SERVNICK" in msg:
                        serv_assig_nickname(sock,msg,c)
                    elif "/SERVCLIENTDISC" in msg:
                        serv_remove_client(sock,msg,c)
                    elif "/SERVPM" in msg:
                        serv_private_message(sock,msg,socket_list,c)
                    elif "/SERVBC" in msg:
                        serv_broadcast(sock,msg,socket_list,c)
                    elif "/SERVCLIENTROOM" in msg:
                        serv_add_to_room(sock,msg,c) 
                    else:
                        print("#Recieved unsupported message from server %s" % get_sock_unique_id(sock))

                else:
                    # Recieved message from a client.
                    # Print message out on server to monitor communications.
                    print("%s-%s-%s: %s" % (get_clients_room(sock,c),get_username(get_sock_unique_id(sock),c),get_sock_unique_id(sock),msg.strip()))
                    
                    # Detect and execute command else broadcast users message
                    if "/NICK" in msg:
                        assign_nickname(msg,sock,c,serv_socket_list) #assumes nickname does not contain - or ' '
                    elif "/WHO" in msg:
                        list_chatroom_members(sock,c)
                    elif "/MSG" in msg:
                        send_private_message(msg,sock,c,socket_list,serv_socket_list,serv_port)
                    elif "/JOIN" in msg:
                        assign_to_room(msg,sock,c,serv_socket_list)
                    else:
                        broadcast_message_to_group(msg,sock,socket_list,c,serv_socket_list)

def print_table(c):
    """
    This function is used for debugging purposes only in order ot print the user_rooms table on the server.
    """
    print("======user_rooms_table======")
    client_room_qry = "SELECT room, socket, serv FROM user_rooms"
    for row in c.execute(client_room_qry):
        print(row)


def distribute_known_clients(sock,c,serv_port):
    """
    Distributes all known clients (user_name and user_room) records to newly joined server.
    This brings the server up to speed with our current clients allowing it to act on many functions.
    This only sends info on clients connected directly to us.

    BUG NOTES: (only affects challenge section - see bottom of readme)
    Note there is a bug in this function, the for loop appears to end abruptly after the first iteration. 
    even when its proven there are multiple valid entries in the database.
    Appears its one or both of the sock.send commands causing this 
    """

    #print_table(c) #<~~~ DEBUGGING.

    client_room_qry = "SELECT socket, room FROM user_rooms WHERE serv = %s" % serv_port 
    #socket, room
    for row in c.execute(client_room_qry):                                                              
        print("#Sharing known client/room with new server")
        #send client id and room
        sock.send(("/SERVCLIENTROOM-%s-%s" % (row[0],str(row[1]))).ljust(PACKET_SIZE).encode())
        #send client username
        sock.send(("/SERVNICK-%s-%s" % (row[0],get_username(row[0],c))).ljust(PACKET_SIZE).encode())


def serv_add_to_room(sock,msg,c):
    """
    Reacts to message from another server. Updates the user_rooms table with clients new room.
    This function is used:
    1. when this server joins a group of existing servers and they sync up clients/rooms
    2. when a client connected to another server changes room via /JOIN. 
    """
    # Parse message from server
    servArgs = msg.split("-")
    servs_client_id = servArgs[1] + "-" + servArgs[2]
    room = str(servArgs[3])

    #Get servers listening port from db
    c.execute("SELECT port from servers WHERE socket = \'%s\'" % (get_sock_unique_id(sock)))
    portList = c.fetchone()
    if portList == None:
        print("#Error, Unable to get %s servers listening port. Cannot add client %s to room %s" % (get_sock_unique_id(sock),servs_client_id,room))
        return

    sending_servs_port = portList[0]

    # Update the client room
    c.execute("INSERT OR REPLACE INTO user_rooms (room, socket,serv) values (\'%s\', \'%s\', %s)" % (room,servs_client_id,sending_servs_port))
    print("ADDING C to room from another server - (\'%s\', \'%s\', %s)" % (room,servs_client_id,sending_servs_port))


def serv_broadcast(sock,msg,socket_list,c):
    """
    Sends out broadcast to all other clients identfied as being in same chat room as original sender
    """
    servArgs = msg.split("-")
    sender_client_id = servArgs[1] + "-" + servArgs[2]

    senders_message = msg[msg.find(servArgs[2]) + len(servArgs[2]) + 1:]

    senders_room = get_clients_room(sender_client_id,c)   #<~~ THIS IS RETURNING ANON every time

    # Abort if we fail to get clients room
    if senders_room == None:
        print("#Failed to get chat room of client %s. Cannot broadcast thier message." % sender_client_id)
        return

    # Broadcast message to all clients connected to this server that are in same chat room. 
    for client in socket_list:
        if get_clients_room(get_sock_unique_id(client),c) == senders_room:
            client.send(("%s-%s: %s" % (senders_room,get_username(sender_client_id,c),senders_message.strip())).encode())


def serv_private_message(sock,msg,socket_list,c):
    """
    Sends a forwarded private message to a connected client. 
    Message has been forwareded from another server who identified this server as being conencted to the appropriate client
    """
    # Parse message from server
    servArgs = msg.split("-")
    sender_client_id = servArgs[1] + "-" + servArgs[2]
    recipient = servArgs[3]
    #pull private message from msg
    privateMessage = msg[msg.find(servArgs[2]) + len(servArgs[2]) + 1:]

    print("#fwd pm from %s to %s reading: %s" % (get_username(sender_client_id,c),recipient,privateMessage))

    for s in socket_list:
        if get_username(get_sock_unique_id(s),c) == recipient:
            s.send(("#PM from %s: %s" % (get_username(sender_client_id,c),privateMessage)).encode())
            break


def serv_remove_client(sock,msg,c):
    """
    Removes a client from database that was conencted to another server
    """
    # Parse message from server
    servArgs = msg.split("-")    
    servs_client_id = servArgs[1] + "-" + servArgs[2]

    c.execute("DELETE FROM user_rooms where socket = \'%s\'" % servs_client_id)
    c.execute("DELETE FROM user_names where socket = \'%s\'" % servs_client_id)


def serv_assig_nickname(sock,msg,c):
    """
    Assigns the nickname for this client in the database. The client is connected to another server (sock)
    """
    # Parse clients ip and port from server message
    servArgs = msg.split("-")    
    servs_client_id = servArgs[1] + "-" + servArgs[2]
    nickname = servArgs[3]

    print("#Inserting nickname from other server into db - %s - %s" % (servs_client_id,nickname))
    c.execute("INSERT OR REPLACE INTO user_names (username, socket) values (\'%s\', \'%s\')" % (nickname, servs_client_id))


def distribute_known_servers(sock,c):
    """
    Sends all known servers to the provided socket
    """
    other_servers_qry = "SELECT ip, port FROM servers WHERE socket <> \'%s\' AND port IS NOT NULL" % get_sock_unique_id(sock)
    for row in c.execute(other_servers_qry):
        print("#Informing server %s of known server %s" % (get_sock_unique_id(sock),(str(row[0]) + "-" + str(row[1]))))
        sock.send(("/ADDSERVER-%s" % (str(row[0]) + "-" + str(row[1]))).encode())


def remove_serv(sock,c):
    """
    Removes a server and it's clients from the database.
    Doesn't need to inform other servers as they should have also been connected to it and therefore experiecned disconnection
    """
    #remove user_name records
    c.execute("DELETE FROM user_names WHERE socket in (SELECT r.socket FROM servers s INNER JOIN user_rooms r ON r.socket = s.socket WHERE r.serv = %s)" % sock.getpeername()[1])
    # Remove user_rooms records for any clients conencted to this server
    c.execute("DELETE FROM user_rooms WHERE serv = (SELECT port FROM servers WHERE socket = \'%s\' LIMIT 1)" % get_sock_unique_id(sock))
    # Remove server record
    c.execute("DELETE FROM servers WHERE socket = \'%s\'" % get_sock_unique_id(sock))
    

def add_incomplete_serv(sock,c):
    """
    Adds the incomplete server record to the servers table. 
    Requests the servers incoming server listing port so we can:
    """

    #check its not already in there for some reason  --- TO BE DONE
    #Insert incomplete server record to database.
    c.execute("INSERT INTO servers (socket, ip, port) values (\'%s\', \'%s\',NULL)" % (get_sock_unique_id(sock), sock.getpeername()[0]))
    #check it went in?  --- TO BE DONE

    #send a /WHATLISTENERPORT request to new server
    sock.send("/WHATLISTENERPORT".ljust(PACKET_SIZE).encode())
    

def update_server_record(sock,msg,serv_socket_list,c):
    """
    Updates database with the connected servers listener port, then shares this with all known servers..
    """
    # Check if socket exists
    c.execute("SELECT count(*) FROM servers WHERE socket = \'%s\' " % get_sock_unique_id(sock))
    serv_exist = c.fetchone()
    if serv_exist[0] != 1:
         print("#Cannot add lisener port to %s server as its socket is not in the database" % get_sock_unique_id(sock))
         return

    #parse message and get port number
    servArgs = msg.split("-")
    port = int(servArgs[1])
    
    # Update listener port in database
    c.execute("UPDATE servers SET port = %s WHERE socket = \'%s\'" % (port, get_sock_unique_id(sock)))

    #Share this server with all the other servers (excluding one that just provided its serv listening port)
    for serv in serv_socket_list:
        if serv != sock:
            print("#Sharing %s with %s post serv listener port update" % ((sock.getpeername()[0] + str(port)),get_sock_unique_id(serv)))
            serv.send(("/ADDSERVER-%s" % (sock.getpeername()[0] + "-" + str(port))).encode())


def create_database(serv_host,serv_port):
    """c
    reates the database and returns the object to maniuplate it
    """
    #define database name
    db_name = "server%s.db" % (str(serv_host) + "-" + str(serv_port))

    # Remove database if it exists
    if os.path.isfile(db_name):
        os.remove(db_name)

    # Create an sqllite database to maintain chatrooms and start a sqlite database connection 
    conn = sqlite3.connect(db_name)
    c = conn.cursor()

    # Create table in the sqlite database
    c.execute("CREATE TABLE if not exists user_rooms (socket text PRIMARY KEY, serv int NOT NULL, room text NOT NULL)")
    c.execute("CREATE TABLE if not exists user_names (username text PRIMARY KEY, socket text NOT NULL UNIQUE)")
    #note that servers.port can be null until listener port is defined by means of \MYLISTENERPORT message
    c.execute("CREATE TABLE if not exists servers (socket text PRIMARY KEY, ip text NOT NULL, port int)") 
    return c


def serv_add_new_client(sock,msg,c,serv_socket_list):
    """
    inserts a new client into the global room, referencing the sending servers serv_port
    This assumes that we've recieved the servers serv_port. Ideally we need to NOT proccess any incoming
    messages from a server unless we know thier serv_port (listed in servers.port)
    """
    
    #check that we have this server serv listener port
    c.execute("SELECT port FROM servers WHERE socket = \'%s\' AND port IS NOT NULL" % get_sock_unique_id(sock))
    send_serv_fetch = c.fetchone()

    if send_serv_fetch == None:
         print("#Cannot add new user for %s server. Hanshake incomplete, don't have it's listening serv port" % get_sock_unique_id(sock))
         return

    sending_servs_port = send_serv_fetch[0]

    #parse clients ip and port from other servers message
    servArgs = msg.split("-")    
    servs_client_id = servArgs[1] + "-" + servArgs[2]
    
    print("#Inserting new client into global rooms <id,serv> = <%s,%s>" % (servs_client_id, str(sending_servs_port)))

    #Add client to global room
    serv_add_to_room(sock,"/SERVCLIENTROOM-%s-%s" % (servs_client_id,"global"),c)


def add_server(ip,port,serv_socket_list,c):
    """
    Add a server to the list where the ip and listener port is known..
    eg defined on execution or provided from another server
    only adds to the list if the socket doesn't already exist 
    """
    # Check if server exists
    c.execute("SELECT count(*) FROM servers WHERE ip = \'%s\' and port = %s" % (ip, str(port)))
    serv_exist = c.fetchone()

    if serv_exist[0] == 1:
         print("#Dont need to add %s, already exists" % (ip + "-" + str(port)))
         return

    #Connects to server on its server listener port
    known_serv_socket = socket.socket()
    known_serv_socket.connect((ip,port))

    #adds server to database
    c.execute("INSERT INTO servers (socket, ip, port) values (\'%s\',\'%s\', %s)" % (get_sock_unique_id(known_serv_socket), ip, port))

    #adds server to serv_socket_list
    serv_socket_list.append(known_serv_socket)

    #informs all other servers about new server (we can do this with get_sock_unique_idbecause we know listener port of server)
    for serv in serv_socket_list:
        if serv != known_serv_socket:
            print("#Informing %s of new server %s" % (get_sock_unique_id(serv),get_sock_unique_id(known_serv_socket)))
            serv.send(("/ADDSERVER-%s" % get_sock_unique_id(known_serv_socket)).encode())

    #inform new server of all our other known servers
    distribute_known_servers(known_serv_socket,c)


def get_sock_unique_id(sock):
    """
    returns <ip>-<port> for passed socket. 
    This ID is used to identify client and servers
    """
    id = str(sock.getpeername()[0]) + "-" + str(sock.getpeername()[1])
    return id


def remove_client_from_db(sock,c):
    """
    Removes the any references to the client in the chat room and username tables
    """
    c.execute("DELETE FROM user_rooms where socket = \'%s\'" % get_sock_unique_id(sock))
    c.execute("DELETE FROM user_names where socket = \'%s\'" % get_sock_unique_id(sock))


def get_clients_room(sock,c):
    """
    Returns a string containing the current clients chat room.
    Accepts either a socket or the id <ip>-<port> of a socket as input for sock.
    """
    if type(sock) == str:
        c.execute("SELECT room FROM user_rooms WHERE socket = \'%s\'" % sock)
    else:
        #assume type is socket
        c.execute("SELECT room FROM user_rooms WHERE socket = \'%s\'" % get_sock_unique_id(sock))

    chatRoom = c.fetchone()

    if chatRoom == None:
        return None
    else:
        return chatRoom[0].strip()


def assign_to_global_room(sock,c,serv_socket_list,serv_port):
    """
    Assigns a new client that is directly connected to this server to the default global chat room
    Then updates all other servers to they can put the this new client in thier database, referncing this serer.
    """

    clientID = sock.getpeername()[1]
    #get the room associated with a specific socket (if associated)
    chatRoom = get_clients_room(sock,c)

    if chatRoom == None:
        # Client not in a room, is a new user.. add to global room.
        print("#assigned user %s to global chatroom" % get_sock_unique_id(sock))
        c.execute("INSERT INTO user_rooms (room, socket, serv) values (\'global\', \'%s\', %s)" % (get_sock_unique_id(sock),serv_port))
        sock.send("#Welcome, you have been automatically assigned to the \'global\' chatroom.".encode())
    
    # Update all other servers with the new client, they will add to thier user_rooms db, referncing this server's serv_port to identfy where client is conencted
    for serv in serv_socket_list:
        serv.send(("/SERVNEWCLIENT-%s" % get_sock_unique_id(sock)).encode())


def assign_to_room(msg,sock,c,serv_socket_list):
    """
    Inserts a record into or updates an existing record in th db identfying which room the socket is assigned to
    socket can only be in a single room at all times. default is global
    """ 
    userArgs = msg.split()
    if len(userArgs) < 2:
        sock.send("#/JOIN requires a second arument as room name e.g /MSG <roomname>".encode())
        return
    
    newRoom = userArgs[1].strip()

    # Get current room (for checking)
    chatRoom = get_clients_room(sock,c)
    if (chatRoom == newRoom):
        sock.send(("#You're already in the " + newRoom  + " chatroom").encode())
    else:
        c.execute("UPDATE user_rooms set room = \'%s\' where socket = \'%s\'" % (newRoom, get_sock_unique_id(sock)))
        print("#Assigning %s-%s to %s" % (get_sock_unique_id(sock),get_username(get_sock_unique_id(sock),c),newRoom))

    # Update all other servers with new client->Room join
    for serv in serv_socket_list:
        serv.send(("/SERVCLIENTROOM-%s-%s" % (get_sock_unique_id(sock),newRoom)).encode())


def get_username(sock_id,c):
    """
    Fetches username from database based on socket id e.g. ip-port
    """
    c.execute("SELECT username FROM user_names WHERE socket = \'%s\'" % sock_id)
    userName = c.fetchone()

    if userName == None:
        return "Anonymous"
    else:
        return userName[0].strip()


def send_private_message(msg,sock,c,socket_list,serv_socket_list,serv_port):
    """
    /MSG <name> <message> : Direct message a specific user. 
    This will only send the message to the user with the specified username.
    The user must have defined thier username to recieve private messages
    If the user is not conencted to this client it will send the appropriate command to the server the client is connected
    This function allows clients to send themselves private messages as well for fun!.
    """
    userArgs = msg.split()
    if len(userArgs) < 2:
        sock.send("#/MSG requires a second arument as recipeint e.g /MSG <username>".encode())
        return

    recipient = userArgs[1]
    privateMessage = msg[msg.find(userArgs[1]) + len(recipient) + 1:] #get message bit

    #Get socket and server for this recipient, if exists.
    c.execute("SELECT n.socket, r.serv FROM user_names n INNER JOIN user_rooms r on n.socket = r.socket WHERE n.username = \'%s\'" % recipient)
    recipientSocket = c.fetchone()

    if recipientSocket == None:
        sock.send(("#" + recipient.strip() + " isn't online, message not sent").encode())
    else:
        # Check if client is connected to this server
        if recipientSocket[1] == serv_port:
            # Client connected to us, send pm
            for s in socket_list:
                if get_sock_unique_id(s) == recipientSocket[0]:
                    s.send(("#PM from %s: %s" % (get_username(get_sock_unique_id(sock),c),privateMessage)).encode())
                    break
        else:
            # Client connected to another server, forward private message to appropriate server.
            for serv in serv_socket_list:
                # Only send to server with matching serv listener port
                # Get servers listening port from db
                c.execute("SELECT port from servers WHERE socket = \'%s\'" % (get_sock_unique_id(serv)))
                serv_port_list = c.fetchone()
                if serv_port_list == None:
                    print("#Error, unable to get servers listener port.. ")
                else:
                    if serv_port_list[0] == recipientSocket[1]:
                        serv.send(("/SERVPM-%s-%s-%s" % (get_sock_unique_id(sock),recipient,privateMessage)).encode())
                        break #Client will only be connected to single server, once sent we're done here


def broadcast_message_to_group(msg,sock,socket_list,c,serv_socket_list):
    """
    Sends message to everyone in senders chatroom
    Forwards message to other servers
    """
    chat_room = get_clients_room(sock,c)

    #get list of all clients in this room
    c.execute("SELECT socket FROM user_rooms where room = \'%s\'" % chat_room)
    socketIDList = c.fetchall()

    #loop through ids in this room and send message to matching sockets in socket_list
    #excludes original message sender
    for row in socketIDList:
        #get socket from socket list (ID's need to match)
        for client in socket_list:
            #if client not in listen_socket_list and get_sock_unique_id(client) == row[0] and get_sock_unique_id(client) != get_sock_unique_id(sock):
            if get_sock_unique_id(client) == row[0] and get_sock_unique_id(client) != get_sock_unique_id(sock):
                client.send(("%s-%s: %s" % (chat_room,get_username(get_sock_unique_id(sock),c),msg.strip())).encode())

    #forward to all servers
    for serv in serv_socket_list:
        serv.send(("/SERVBC-%s-%s" % (get_sock_unique_id(sock),msg.strip())).encode())


def list_chatroom_members(sock,c):
    """
    /WHO : Allows users to list the usernames currently in the channel.
    """
    chatUsersString = ""
    chatRoom = get_clients_room(sock,c)

    userNameQry = "SELECT ifnull(u.username,'Anonymous') FROM user_rooms r LEFT OUTER JOIN user_names u ON r.socket = u.socket WHERE r.room = \'%s\'" % chatRoom

    whoString = ""
    for row in c.execute(userNameQry):
        whoString += str(row[0]) + ", "

    sock.send(("#users present: " + whoString[:-2]).encode())   


def assign_nickname(msg,sock,c,serv_socket_list):
    """
    /NICK <name>: Allows the user to enter a unique nickname which is then displayed in front of their messages.
    This then sends message to all other servers asking them to update thier databases with the new clients nickname
    """
    userArgs = msg.split()
    if len(userArgs) < 2:
        sock.send("#/NICK requires a second arument as for nickname e.g /NICK <name>".encode())
        return

    nickname = userArgs[1].strip()   #going to get list index out of range if they dont provide nickname, crashing server

    #check if username is used first
    c.execute("SELECT username FROM user_names WHERE username = \'%s\'" % nickname.strip())
    if c.fetchone() != None:
        sock.send(("#Username already in use.").encode()) 
    elif "-" in nickname:
        sock.send(("#Username is invalid, cannot contain \'-\'").encode()) 

    else:
        #insert or update the username for this user
        c.execute("INSERT OR REPLACE INTO user_names (username, socket) values (\'%s\', \'%s\')" % (nickname, get_sock_unique_id(sock)))

        #update all other servers with the clients nickname
        for serv in serv_socket_list:
            serv.send(("/SERVNICK-%s-%s" % (get_sock_unique_id(sock),nickname)).encode())


if __name__ == "__main__":
    run_server()



