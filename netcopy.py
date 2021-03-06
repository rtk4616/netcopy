#!/usr/bin/env python

#Protocol:
# num_files:uint(4) 
# repeat num_files times:
# 	filename:string
# 	size:uint(8)
# 	data:bytes(size)

import sys, socket
import os
from time import time

DEFAULT_PORT = 52423
PROGRESSBAR_WIDTH = 50
BUFSIZE = 1024*1024

CONNECTION_TIMEOUT = 3.0
RECEIVE_TIMEOUT = 5.0


if os.name == "nt":
	sep = "\\"
else:
	sep = '/'

def main():
	if len(sys.argv)<2:
		usage()
		return
	if sys.argv[1]=='-s' and len(sys.argv) >= 4:
		try:
			send()
		except KeyboardInterrupt:
			printError("\nAbort")
	elif sys.argv[1]=='-r':
		try:
			recieve()
		except KeyboardInterrupt:
			printError("\nAbort")
	else:
		usage()

def printError(s):
	sys.stderr.write(s+'\n')


def encodeInt(l, size):
	if l > ((0x1 << (8*size))-1):
		raise ValueError("Number too large: {0}".format(l))

	b = bytearray(size)
	i = 0
	while l > 0:
		b[i] = (l & 0xff)
		l = l >> 8
		i+=1
	b.reverse()
	return b

def encodeString(s):
	return s+b'\x00'

def recieveInt(size, conn):
	data = conn.recv(size)
	b = bytearray(data)
	if len(b) != size:
		raise ValueError("Received invalid data")
	value = 0
	for i in range(0,size):
		value = value << 8
		value += b[i]
	return value

def recieveString(conn):
	s = ""
	ch = ''
	while True:
		ch = conn.recv(1)
		if ch == b'\x00':
			break
		s += ch
	return s 

def send():
	port = DEFAULT_PORT
	i = 2
	files = []
	while i < len(sys.argv): #-2
		if sys.argv[i]=='-p':
			if i+1 >= len(sys.argv):
				printError("Expecting port after '-p'")
				return
			try:
				port = int(sys.argv[i+1])
			except ValueError:
				printError("Invalid port: "+sys.argv[i+1])
				return
			i+=1
		else:
			receiver = sys.argv[i]
			files = sys.argv[i+1:]
			break
		i+=1

	num_files = 0
	open_files = []
	for fn in files:	
		try:
			f = open(fn, "rb")
			open_files.append((fn, f))
			num_files+=1
		except IOError as e: 
			printError("Could not open file {0}: {1}. Skipping".format(fn, e.strerror))

	if num_files == 0:
		printError("No files to send. Aborting")
		return 

	try:	
		client = socket.create_connection((receiver, port), CONNECTION_TIMEOUT)
	except Exception as e:
		message = str(e)
		if hasattr(e, 'strerror'):
			message = e.strerror
		printError("Could not connect to {0}: {1}".format(receiver, message))
		return

	print("--- Sending {0} file(s) to {1} ---".format(num_files, receiver))
	metadata = bytearray()
	metadata += encodeInt(num_files, 4)

	for (fn, f) in open_files:
		metadata += encodeString(fn[fn.rfind(sep)+1:])
		f.seek(0,2)
		size = f.tell()
		print("- Sending {0} ({1} bytes)".format(fn, size))
		metadata += encodeInt(size, 8)
		client.sendall(metadata)
		metadata = bytearray()
		f.seek(0,0)

		while size > 0:
			bytebuf = bytearray(f.read(BUFSIZE))
			client.sendall(bytebuf)
			size -= BUFSIZE
		
		f.close()
	
	client.close()

def recieve():
	port = DEFAULT_PORT
	i = 2
	while i < len(sys.argv):
		if sys.argv[i]=='-p':
			if i+1 >= len(sys.argv):
				printError("Expecting port after '-p'")
				return
			try:
				port = int(sys.argv[i+1])
			except ValueError:
				printError("Invalid port: "+sys.argv[i+1])
				return
			i+=1
		else:
			printError("Unrecognized argument: "+sys.argv[i])
			return
		i+=1

	try:	
		server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		server.bind(('', port))
	except Exception as e:
		printError("Could not bind socket: {0}".format(e.strerror))	
		return

	print("Waiting for incoming connections...")
	server.listen(1)
	conn, addr = server.accept()
	print("Connected to {0}".format(addr[0]))
	num_files = recieveInt(4, conn)

	print("Recieving {0} file(s)".format(num_files))
	if num_files > (0x1 << 16):
		printError("Too many files. Aborting")
		return
	
	try:
		for i in range(0,num_files):
			fn = recieveString(conn)
			filesize = recieveInt(8, conn)
			print("- {0} ({1} bytes)".format(fn, filesize))
			if os.path.isfile(fn):
				print("  Error: file '{0}' already exists. Skipping".format(fn))
				conn.recv(filesize)
				continue
			f = open(fn, "wb")
			size = filesize
			printProgressBar(0)	

			lastreceivetime = time()
			printProgressBar(0)
			while size > 0:
				buffersize = min(BUFSIZE, size)	
				data = conn.recv(buffersize)
				if len(data) == 0:
					if time()-lastreceivetime > RECEIVE_TIMEOUT:
						printError("\nReceive timeout. Aborting")
						server.close()
						return
					continue

				lastreceivetime = time()
				size -= len(data)
				f.write(data)
				ratio = float(filesize-size)/float(filesize)
				printProgressBar(ratio)
			printProgressBar(1)
			print("")
			f.close()
	except ValueError:
		printError("Protocol error. Aborting")
	finally:
		server.close()

def printProgressBar(ratio):
	if ratio < 0 or ratio > 1:
		raise ValueError("Error: invalid ratio: {0}".format(ratio))
	progressbar_length = int(ratio * PROGRESSBAR_WIDTH)
	progressbar = '#'*progressbar_length + ' '*(PROGRESSBAR_WIDTH-progressbar_length)  + " - {0:.2f}%".format(ratio*100.0)
	sys.stdout.write("\r"+progressbar)
	sys.stdout.flush()

def usage():
	print("Usage:\n"
			"\t{0} -s [-p port] [receiver] [files...]\t- Send files to receiver\n"
			"\t{0} -r [-p port]\t\t\t\t- Receive files"
			.format(sys.argv[0][sys.argv[0].rfind(sep)+1:]))

if __name__ == "__main__":
	main()
