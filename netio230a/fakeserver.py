#!/usr/bin/env python
# -*- encoding: UTF8 -*-

# Author: Philipp Klaus, philipp.l.klaus AT web.de


#   This file is part of netio230a.
#
#   netio230a is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   netio230a is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with netio230a.  If not, see <http://www.gnu.org/licenses/>.


# This is a fake Koukaam NETIO230A telnet server.
# It tries to imitate the behaviour of the original device.
# The reason this exitsts is mainly the unittest for the netio230a class.

import socketserver
import threading
import random
import string
import hashlib
import re
import datetime
import sys


# we need to initialize the variable here, because we need the global scope:
fake_server = None

# Koukaam Netio230A Behaviour:
N_WELCOME = "100 HELLO %X - KSHELL V1.2" # welcome message
N_OK = "250 " # OK prefix
N_OK_L = "250 OK" # complete OK line
N_VER = "250 V %s"
N_ALIAS = "250 %s"
N_SWDELAY = "250 %s"
N_BOOLEAN = "250 %s"
N_INV_V = "500 INVALID VALUE"
N_INV_P = "501 INVALID PARAMETR"
N_UNKNOWN = "502 UNKNOWN COMMAND" # happens when you enter something like `prt`
N_AUTH_ERR = "503 INVALID LOGIN"
N_ALR_AUTH = "504 ALREADY LOGGED IN"
N_FORB = "505 FORBIDDEN"
N_BYE = "110 BYE"
N_LINE_ENDING = "\r\n"

N_ALIAS_LENGTH = 18
N_NUM_OUTLETS = 4
N_MAX_SWDELAY = 999

# Fake Netio230A configuration:
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="admin"

class InvVError(Exception):
    pass
class InvPError(Exception):
    pass

class FakeNetio230aServerHandler(socketserver.BaseRequestHandler):

    def send(self,message):
        self.fakeserver.log(message+N_LINE_ENDING)
        self.request.send((message+N_LINE_ENDING).encode('ascii'))

    def receive(self):
        return self.request.recv(1024)

    def handle(self):
        global fake_server
        self.fakeserver = fake_server
        device = fake_server.device
        # First, we have to send the welcome message (including the salt for the md5 password hash):
        salt = random.randint(0, 2**32-1)
        self.send(N_WELCOME % salt)
        # now we wait for incoming authentication requests:
        auth = False
        while not auth:
            what_to_do = self.process(self.receive(),False)
            if what_to_do[0] == 'quit':
                break
            if what_to_do[0] == 'invalid_login':
                self.send(N_AUTH_ERR)
            if what_to_do[0] == 'login':
                if ADMIN_USERNAME == what_to_do[1] and ADMIN_PASSWORD == what_to_do[2]: auth = True
            if what_to_do[0] == 'clogin':
                md = hashlib.md5()
                to_hash = ADMIN_USERNAME+ADMIN_PASSWORD+"%X" % salt
                md.update(to_hash.encode("ascii"))
                if md.hexdigest() ==  what_to_do[2]: auth = True
            if what_to_do[0] in ['login','clogin']:
                if auth:
                    self.send(N_OK_L)
                    break
                else:
                    self.send(N_AUTH_ERR)
            if not what_to_do[0] in ['quit', 'invalid_login', 'login', 'clogin']:
                self.send(N_FORB)
        # now we serve all incoming requests:
        while auth:
            what_to_do = self.process(self.receive())
            #pdb.set_trace()
            if what_to_do[0] == 'port_list':
                self.send(N_OK + ''.join([str(int(status)) for status in device.getOutlets()]))
            if what_to_do[0] == 'port_setup':
                outlet = device.outlets[what_to_do[1]-1]
                self.send(N_OK + '"%s" %s %d %d' % (outlet.name, "timer" if outlet.timer.enabled else "manual", outlet.interrupt_delay, outlet.power_status_after_power_on) )
            if what_to_do[0] == 'port_set':
                device.setOutlet(what_to_do[1]-1,what_to_do[2])
                self.send(N_OK_L)
            if what_to_do[0] == 'unknown_command':
                self.send(N_UNKNOWN)
            if what_to_do[0] == 'invalid_parameter':
                self.send(N_INV_P)
            if what_to_do[0] == 'invalid_value':
                self.send(N_INV_V)
            if what_to_do[0] == 'already_authenticated':
                self.send(N_ALR_AUTH)
            if what_to_do[0] == 'version':
                self.send(N_VER % device.version)
            if what_to_do[0] == 'set_alias':
                device.alias = what_to_do[1]
                self.send(N_OK_L)
            if what_to_do[0] == 'get_alias':
                self.send(N_ALIAS % device.alias)
            if what_to_do[0] == 'get_system_discover':
                self.send(N_BOOLEAN % ("enable" if device.discover else "disable") )
            if what_to_do[0] == 'set_system_discover':
                device.discover = what_to_do[1]
                self.send(N_OK_L)
            if what_to_do[0] == 'get_system_swdelay':
                self.send(N_SWDELAY % device.swdelay)
            if what_to_do[0] == 'set_system_swdelay':
                device.swdelay = what_to_do[1]
                self.send(N_OK_L)
            if what_to_do[0] == 'quit':
                break
        self.send(N_BYE)

    # still unknown commands:
    #port 1
    #email server

    def process(self,data,already_authenticated = True):
        data = data.decode('ascii')
        self.fakeserver.log(data+"\n")
        data = data.strip()
        if data == 'quit':
            return ['quit']
        if self.begins(data,'login') or self.begins(data,'clogin'):
            if already_authenticated: return ['already_authenticated']
            try:
                fragments = data.split(' ')
                username = fragments[1]
                password_or_hash = fragments[2]
            except:
                return ['invalid_login']
            return ['login' if self.begins(data,'login') else 'clogin',username,password_or_hash]
        if data == 'version':
            return ['version']
        if data == 'alias':
            return ['get_alias']
        if self.begins(data,'alias '):
            new_alias = data.split(' ')[1]
            if len(new_alias) > N_ALIAS_LENGTH: return ['invalid_parameter']
            return ['set_alias', new_alias]
        if data == 'system discover':
            return ['get_system_discover']
        if self.begins(data,'system discover'):
            try:
                new = data.split(" ")[2][0]
                if new == 'e': return ['set_system_discover', True]
                if new == 'd': return ['set_system_discover', False]
            except:
                pass
            return ['invalid_value']
        if data == 'system swdelay':
            return ['get_system_swdelay']
        if self.begins(data,'system swdelay '):
            try:
                value = int(re.match("system swdelay ([0-9]*)", data).groups()[0])
            except:
                return ['invalid_value']
            if value > N_MAX_SWDELAY: return ['invalid_value']
            return ['set_system_swdelay', value]
        if data == 'port list':
            return ['port_list']
        if self.begins(data,'port'):
            try:
                fragments = data.split(' ')
                second_part = fragments[1]
            except IndexError:
                return ['invalid_parameter'] # this is what you get for the invalid command `port`
            if second_part == 'setup':
                pass
                try:
                   which = int(fragments[2])
                   if not which in range(1,N_NUM_OUTLETS+1):
                       raise InvPError
                except InvPError:
                    return ['invalid_parameter']
                except IndexError:
                    return ['invalid_parameter']
                return ['port_setup',which]
            elif len(second_part)==1:
                try:
                    which = int(second_part)
                    if not which in range(1,N_NUM_OUTLETS+1):
                        raise InvPError
                    to = int(fragments[2])
                    if not (to in [0,1]):
                        raise InvVError
                except InvVError:
                    return ['invalid_value']
                except InvPError:
                    return ['invalid_parameter']
                except ValueError:
                    return ['invalid_parameter']
                except IndexError:
                    return ['port_get',which]
                return ['port_set',which,bool(to)]
        return ['unknown_command']

    def begins(self,data,with_this):
        return data[0:len(with_this)] == with_this

class FakeNetio230aTimer(object):
    enabled = False
    mode = 0 # once (0), daily (1), weekly (2)
    on_time = None
    off_time = None
    week_schedule = [True for i in range(7)] # set the timer for the day of week

class FakeNetio230aWatchdog(object):
    enabled = False
    ip = "0.0.0.0"
    timeout = 9 # ping command timeout [in seconds]
    power_on_delay = 60 # time for which the Watchdog will be inactive after the output restarts [in seconds]
    ping_interval = 3 # interval between ping commands [in seconds]
    max_retry = 3 # how many times should be the output restarted
    retry_power_off = False # keep the output OFF after Max retry limit is reached
    send_email = False # send an email after power cycle and when max retry is reached

class FakeNetio230aOutlet(object):
    power_status = False
    power_status_after_power_on = False #default output state after power on
    name = "outlet x"
    timer = FakeNetio230aTimer()
    watchdog = FakeNetio230aWatchdog()
    interrupt_delay = 5 # seconds

class FakeNetio230a(object):
    ### Artificial addons of the fakeserver:
    logging = False
    ### implicit properties of the device:
    outlets = [ FakeNetio230aOutlet() for i in range(N_NUM_OUTLETS)]
    ### Configuration as listed on /system.htm
    ip = "192.168.1.101"
    subnet = "255.255.255.0"
    gateway = "192.168.1.1"
    dns = "192.168.1.1"
    dhcp_mode = False
    swdelay = 15 # Switch delay (x0.1s): delay between triggering two outputs
    system_messages = True
    kshell_network_mode = True # If True listens to the network if False listens on the RS232 interface
    kshell_port = 1234
    web_port = 80
    alias = "Zarathustra"
    version = "2.33"
    #### hidden system configurations:
    discover = True
    ### Date & time as listed on /timesetup.htm
    up_since = datetime.datetime.now()
    sntp_enabled = True
    sntp_synchronized = False
    sntp_server = "ntp.pool.org"
    timezone = 7200 # Local time offset in minutes
    #Daylight saving time: 	Enable Disable
    #Daylight saving time begin: 	- -   ::
    #Daylight saving time end:
    ### E-mail configuration as listed on /email.htm
    email_from = "mail@example.com"
    email_to = "mail@example.com"
    email_smtp_server = "smtp.example.com"
    email_subject = "Email from NETIO230A"
    
    def setOutlet(self, which, to):
        self.outlets[which].power_status = bool(to)
    def getOutlets(self):
        return [outlet.power_status for outlet in self.outlets]


class FakeNetio230aServer(socketserver.ThreadingMixIn, socketserver.TCPServer):

    def __init__(self, server_address, RequestHandlerClass,logfile_name=""):

        global fake_server
        #if fake_server is not None: raise NameError("Can only start a single instance of the FakeServer")
        fake_server = self

        self.device = FakeNetio230a()
        ### Seems like we don't really need this line (at least with Python 2.7 on Mac OS X):
        self.allow_reuse_address = True
        ## with Python 3 we would use something like:
        #super( FakeNetio230aServer, self ).__init__(server_address, RequestHandlerClass)
        ## instead we have to call the constructor of TCPServer explicitly using Python 2.X
        socketserver.TCPServer.__init__(self, server_address, RequestHandlerClass)

        if logfile_name != "":
            self.logfile = open(logfile_name,'a')
            self.logging = True

    def log(self,message):
        if self.logging: self.logfile.write(message)


import socket, signal
class NetcatClientConnectionClosed(Exception):
    pass
class AlarmException(Exception):
    pass
def alarmHandler(signum, frame):
    raise AlarmException
CLIENT_LINE_ENDING = "\n"
CLIENT_POLL_TIME = 1 # must be an integer value (1 is the smallest)
class NetcatClient(object):
    def interactive(self,host,port):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.connect( (host, port) )
        self.connected = True
        read_thread = threading.Thread(target=self.read)
        read_thread.daemon = True
        read_thread.start()
        signal.signal(signal.SIGALRM, alarmHandler)
        while True:
            try:
                signal.alarm(CLIENT_POLL_TIME)
                user_input = input()
                self.client.send((user_input+CLIENT_LINE_ENDING).encode('ascii'))
                signal.alarm(0) # cancel alarm
            except AlarmException:
                if not self.connected: break
        raise NetcatClientConnectionClosed
    def read(self):
        while True:
            server_response = self.client.recv(8192).decode('ascii')
            if not server_response: break
            print(server_response, end="")
        self.connected = False

def start_fakeserver(tcp_port, start_client, logfile):
    global fake_server
    FakeNetio230aServer(("", tcp_port), FakeNetio230aServerHandler,logfile)
    fake_server_ip, fake_server_port = fake_server.server_address
    print("Fake Netio230A server reachable on 'localhost' on port %i" % fake_server_port)
    if start_client:
        # If we want a client to show up, we have to put the server to a background thread:
        server_thread = threading.Thread(target=fake_server.serve_forever,args=(0.3,))
        server_thread.daemon = True
        server_thread.start()
        try:
            nc = NetcatClient()
            nc.interactive(fake_server_ip, fake_server_port)
        except NetcatClientConnectionClosed:
            print("The client is now disconnected from the server.")
        except KeyboardInterrupt:
            print("  [CTRL]-[C] catched, exiting.")
    else:
        try:
            fake_server.serve_forever(0.3)
        except KeyboardInterrupt:
            print("  [CTRL]-[C] catched, exiting.")
            sys.exit(1)
    sys.exit(0)

