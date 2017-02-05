README:
Chester Craig's NWEN241 Python Project - Challenge doco:

The server.py and client.py can be executed as normal without any arguments. 
This will run a single server defaulted to:
5000 - client listening port
5001 - server listening port


All servers are configured with 2 listening ports, one for incoming client connects and one for incoming server connections.
Once the first server is running any additional servers must be provided with an alternate client and server listening port.
Additional servers can be provided the server listening port of another server (on the loop back address).
This will connect the servers and any clients connected to them together.

When a new server is started and connected to another the server it connected to will synchronise its database (user_rooms and user_names tables).

Each server maintains another sqllite db table that tracks all the servers its connected to and its server listener port.
The user_rooms table has been extended to store the client's servers's listener port. 
As the system is only setup to run on the loop back address this is restricted to the port number.

The client will by default try connect to a server at 5000.
Alternatively it can be passed an alternate server client listening port


-------------------------------------------------------------------------------
How to run distributed servers: 
(note that these only work on loopback address - at present.)

1. Start a server via 'python3 server.py'
	This will default to the following listening ports:
	Incoming client connections to 127.0.0.1-5000
	Incoming server connections to 127.0.0.1-5001

2.Either connect a client to the existing server or additional server.
-client via 'python3 client.py 127.0.0.1-5000' or 'python3 client.py'
-server via 'python3 server.py 5020 5021 127.0.0.1-5001'

3.Continue to create or terminate clients at will.
	The system will remove all clients and servers as they drop off. 
	Any clients connected to a disconnected server are removed.


-------------------------------------------------------------------------------
SERVER ARGUMENTS:
Server can be run as normal will use default ports 5000/5001

1 arg <alternate client port> 
e.g. python3 server.py 5020
alternate host for clients (to allow multiple servers to run on a single machine)

2 args <alternate client port> <alternate server port> 
e.g python3 server.py 5020 5021
alternate host for clients to connect too
alternate server port (to allow multiple servers to listen for incoming server connections on same machine)

3 args <alternate client port> <alternate server port> <known ip-port for active server>
python3 server.py 5020 5021 127.0.0.1-5001
alternate host for clients to connect too
alternate server port
known server addr/port to begin communicating with another server

----------------------------------
NOTES:
there is a bug in the distribute_known_clients() function. 
it seems to be prematurely aborting the for loop.
This results in only a single client being transferred from an existing server to another as it connects. 

This bug can be avoided by starting up all required server before connecting clients.


