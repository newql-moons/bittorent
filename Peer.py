from collections import deque
import socket
import struct
from bitstring import BitArray

MAX_REQUESTS = 2
MSG_TYPES = ['choke', 'unchoke', 'interested', 'not_interested', 'have', 'bitfield', 'request', 'piece', 'cancel', 'port']

class Peer():

    def __init__(self, torrent, ip, port, peer_id = None):
        self.torrent = torrent
        self.ip = ip
        self.port = port
        self.peer_id = peer_id
        self.sock = None
        self.handshake = ''

        self.handshake_sent = False
        self.connected = False
        self.choked = True
        self.interested = False
        self.msg_queue = deque()

        self.pieces = BitArray(bin='0'*self.torrent.num_pieces)
        self.reply = ''

        self.requests = [] #array of tuples: piece, offset
        self.requested_pieces = [] #array of tuples representing pieces currently in work: (piece index, BitArray of blocks)
        self.MAX_REQUESTS = MAX_REQUESTS

    def fileno(self):
        """
        makes Peer object behave like i/o object that can be handled by select
        will only work once self.sock has been created
        """
        return self.sock.fileno()

    def send_msg(self):
        try:
            if not self.handshake_sent:
                self.sock.sendall(self.torrent.handshake)
                self.handshake_sent = True
                print 'Sent Handshake'
            elif self.connected and self.choked:
                self.sock.sendall(self.encode_msg('interested'))
                print('Sent interested')
            elif not self.choked:
                new_request = self.torrent.get_next_request(self)
                self.request(new_request)
                print 'Requested', new_request
            return True
        except:
            return False

    def encode_msg(self, msg_type, payload=''):
        if msg_type == 'keep alive':
            msg = ''
        else:
            msg = struct.pack('B', MSG_TYPES.index(msg_type))+payload
        return struct.pack('>I', len(msg))+msg

    def update_connected(self, handshake):
        #TODO: verify peer_handshake
        print 'Received handshake', handshake
        #update peer's status:
        self.connected = True

    def request(self, piece):
        #send request
        index, begin, length = piece
        self.sock.sendall(self.encode_msg('request', struct.pack('>I I I', index, begin, length)))
        #update self.requests
        self.requests.append((index, begin))

    def update_reply(self):
        """receive a reply from peer"""
        try:
            self.reply += self.sock.recv(1024)
            print 'Updated reply', self.reply
        except socket.error:
            print socket.error
    def process_reply(self):
        print 'processing reply'
        while self.reply:
            msg_len = struct.unpack('>I', self.reply[:4])[0]
            if msg_len == 0:
                print 'Keep alive'
                #TODO: keep alive: reset the timeout; update self.reply
                self.reply = self.reply[:4]
            elif msg_len == 19 and self.reply[4:23] == 'BitTorrent protocol':
                self.update_connected(self.reply[:68])
                self.reply = self.reply[68:]
            elif len(self.reply) >= (msg_len + 4):
                self.msg_processor(self.reply[4:4+msg_len])
                self.reply = self.reply[4+msg_len:]
            else:
                try:
                    self.reply += self.sock.recv(max(1024, msg_len - 4))
                except:
                    break

    def msg_processor(self, msg_str):
        print msg_str
        msg = struct.unpack('B', msg_str[0])[0]
        print MSG_TYPES[msg]
        #choke
        if msg == 0:
            self.choked = True

        #unchoke
        elif msg == 1:
            self.choked = False

        #peer is interested
        elif msg == 2:
            self.sock.sendall(self.encode_msg('unchoke'))

        #peer is not interested
        elif msg == 3:
            pass

        #peer has piece #x
        elif msg == 4:
            #update info about peer's pieces
            piece_idx = struct.unpack('>I', msg_str[1:])[0]
            self.pieces[piece_idx] = True

        #bitfield msg
        elif msg == 5:
            self.pieces = BitArray(bytes=msg_str[1:])
            del self.pieces[self.torrent.num_pieces:] #cut out unnecessary bits

        #request for a piece
        elif msg == 6:
            pass #TODO: implement sending a piece
            #locate requested piece, send it; update uploaded, advertise it other peers

        #piece
        elif msg == 7:
            index, begin = struct.unpack('>I I', msg_str[1:9])
            #write the file
            self.torrent.write(index, begin, msg_str[9:])
            #update the peer's queue
            self.requests.remove((index, begin))

        #cancel piece
        elif msg == 8:
            pass

        #port msg
        elif msg == 9:
            pass

        else:
            print 'unknown message:', msg, msg_str