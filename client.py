import sys
import socket
import select

#Constant to store packet size
PACKET_SIZE = 1024 


def run_client():
    """
    Run the client. This should listen for input text from the user
    and send messages to the server. Responses from the server should
    be printed to the console.

    A single <ip-portnumber> argument can be provided to over rule the default 127.0.0.1-5000 server
    """

    # Specify where the server is to connect to (defaults)
    server_address = '127.0.0.1'
    port = 5000

    #check if user provided alternate server address 
    if len(sys.argv) == 2:
        usr_defined_serv = sys.argv[1].split("-")
        if usr_defined_serv[1].isdigit() == False:
            print("Port provided is invalid, aborting")
            return

        server_address = usr_defined_serv[0]
        port = int(usr_defined_serv[1])
        print("Overwritten defaul server address/port. Now using %s" % sys.argv[1])
    
    # Create a socket and connect to the server
    client_socket = socket.socket()
    try:
        client_socket.connect((server_address, port))
    except socket.error as exc:
        print("Failed to connect to server on at %s. Exception socket.error : %s" % (server_address + "-" + str(port),exc))
        return
    socket_list = [sys.stdin, client_socket]

    # Log that it has connected to the server
    print ('Connected to chat server.')
    print ('Type here to send messages:')

    # Start listening for input and messages from the server
    while True:        
        # Listen to the sockets (and command line input) until something happens
        ready_to_read, ready_to_write, in_error = select.select(socket_list , [], [], 0)
     
        # When one of the inputs are ready, process the message
        for sock in ready_to_read:            
            # The server has sent a message
            if sock == client_socket:
                rawMsg = sock.recv(PACKET_SIZE)

                # Detect disconnection
                if (str(rawMsg) == "b''"):
                    print("#Server disconnected - Please restart client")
                    return

                # decode the data coming from the socket and print it out to the console
                msg = rawMsg.decode().strip()
                print (msg)
            else:
                # The user entered a message
                msg = sys.stdin.readline()
                # Send the message to the server
                client_socket.send(msg.encode())

        
if __name__ == '__main__':
    run_client()