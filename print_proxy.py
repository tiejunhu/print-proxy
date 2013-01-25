import os
import sys
import signal
import socket
import select
import logging
import thread
from threading import Thread
from datetime import datetime

'''
print proxy/filter, work on RAW protocol

Work as a proxy without the 'filter' parameter
    - every receveied bytes will be saved as a file per connection
    - file is placed in folder named as client(which connects to this proxy)'s IP address
    - forward the data to target IP/port
    - won't forward if target cannot connect

Work as a filter with the 'filter' parameter
    - each received byte will be checked to determine the end of job (@PJL EOJ)
    - all data before end of job will be forwarded to target IP/port
    - all data after end of job will be saved as a file and won't be forwarded
    - file is placed in folder named as target IP address
    - won't forward if target cannot connect
'''

class ConnectionHandler:
    def __init__(self, connection, address, timeout, target_host, target_port, filter_enabled, no_save):
        self.logger = logging.getLogger('ConnectionHandler')
        self.client_socket = connection
        self.local_address = address
        self.timeout = timeout
        self.target_host = target_host
        self.target_port = target_port
        self.state = 0
        self.ignore_left = False
        self.file = 0
        (host, port) = self.client_socket.getpeername()
        self.log_prefix = "%s:%d" % (host, port)
        self.filter_enabled = filter_enabled
	self.no_save = no_save
        
        self.assign_target_socket()
        self.read_write()
    
    def assign_target_socket(self):
        try:
            self.target_socket = self.connect_target(target_host, target_port)
        except:
            self.info("cannot connect to %s:%d, acting as a null server" % (target_host, target_port))
            self.target_socket = 0
    
    def connect_target(self, host, port):
        (soc_family, _, _, _, address) = socket.getaddrinfo(host, port)[0]
        target = socket.socket(soc_family)
        target.connect(address)
        self.info("connected to target %s:%d" % (host, port))
        
        return target
    
    def _check_and_update_state(self, current_state, v, value):
        if (self.state == current_state):
            if (v == value):
                self.state = self.state + 1
            else:
                self.state = 0
            return True
        return False
    
    def _check_and_update_state_pjl(self, current_state, v, value):
        if self._check_and_update_state(current_state, v, value):
            if self.state == 0:
                self.ignore_left = True
            return True
        return False
    
    def update_state(self, v):
        if self._check_and_update_state(0, v, 0x1b):
            return
        if self._check_and_update_state(1, v, 0x25):
            return
        if self._check_and_update_state(2, v, 0x2d):
            return
        if self._check_and_update_state(3, v, 0x31):
            return
        if self._check_and_update_state(4, v, 0x32):
            return
        if self._check_and_update_state(5, v, 0x33):
            return
        if self._check_and_update_state(6, v, 0x34):
            return
        if self._check_and_update_state(7, v, 0x35):
            return
        if self._check_and_update_state(8, v, 0x58):
            return
        
        if self._check_and_update_state_pjl( 9, v, 0x40):
            return
        if self._check_and_update_state_pjl(10, v, 0x50):
            return
        if self._check_and_update_state_pjl(11, v, 0x4a):
            return
        if self._check_and_update_state_pjl(12, v, 0x4c):
            return
        
        if self.state == 13:
            self.state = 0

    
    def handle_data(self, socket, data):
        datalen = len(data) if data else 0
        if not self.ignore_left:
            if socket is self.client_socket:
                out = self.target_socket
                if self.filter_enabled:
                    i = 0
                    for b in data:
                        i += 1
                        v = ord(b)
                        self.update_state(v)
                        if self.ignore_left: # self.ignore_left will be updated in self.update_state
                            self.create_folder_and_file()
                            self.file.write(data[i - 1:])
                            data = data[:i - 1]
                            self.info("error in stream from offset %d" % (self.total + len(data)))
                            break
            else:
                out = self.client_socket            
            if data and out:
                out.send(data)
        if data:
            if self.file:
                self.file.write(data)
            self.total += datalen

    def read_write(self):
        select_time_out = 3;
        time_out_max = self.timeout / select_time_out
        
        socs = [self.client_socket, self.target_socket] if self.target_socket else [self.client_socket]
            
        if not self.filter_enabled:
            self.create_folder_and_file()
        
        count = 0
        self.total = 0
        
        while 1:
            count += 1
            (recv, _, error) = select.select(socs, [], socs, select_time_out)
            
            if error:
                self.info("error in select")
                break
            
            if recv:
                for in_socket in recv:
                    data = in_socket.recv(8192 * 8)
                    self.handle_data(in_socket, data)
                    if data:
                        count = 0
            
            if count == time_out_max:
                self.info("timeout, received total %d bytes" % self.total)
                break

        if self.file:
            self.file.close()
    
    def create_folder_and_file(self):
	if no_save:
            return
        (folder, filename) = self.get_file_name()
        try:
            os.mkdir(folder)
        except:
            pass
        self.file = open(os.path.join('.', folder, filename), 'wb')
    
    def get_file_name(self):
        now = datetime.now().strftime('%Y%m%d.%H%M%S.%f.pcl')
        if self.filter_enabled:
            host = self.target_host
        else:
            (host, port) = self.client_socket.getpeername()
        self.info("generated dir name %s, file name %s" % (host, now))
        return (host, now)
    
    def info(self, str):
        self.logger.info("%s - %s" % (self.log_prefix, str))

def start_server(host, port, t_host, t_port, filter_enabled, no_save):
    logger = logging.getLogger('start_server')
    logger.info("starting %s server %s:%d" % ('filter' if filter_enabled else 'proxy', host, port))
    
    soc = socket.socket(socket.AF_INET)
    soc.bind((host, port))
    soc.listen(1)
    
    def signal_handler(signal, frame):
        print
        logger.info("stopping server.")
        soc.close()
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    while 1:
        thread.start_new_thread(ConnectionHandler, soc.accept() + (60, t_host, t_port, filter_enabled, no_save))

def usage():
    print "Usage: %s <local ip> <listen port> <target ip> <target port> [filter/nosave]" % sys.argv[0]
    exit(1)

if __name__ == '__main__':
    if (len(sys.argv) < 5):
        usage()
        
    host = sys.argv[1]
    port = int(sys.argv[2])
    target_host = sys.argv[3]
    target_port = int(sys.argv[4])
    filter_enabled = False
    no_save = False
    
    if (len(sys.argv) == 6):
        if sys.argv[5] == 'filter':
            filter_enabled = True
	if sys.argv[5] == 'nosave':
	    no_save = True
    
    logfile = "%s.log" % target_host
    
    logging.basicConfig(filename=logfile, level=logging.DEBUG, format='%(asctime)s - %(levelname)-8s %(name)s  %(message)s')
    
    start_server(host, port, target_host, target_port, filter_enabled, no_save)
