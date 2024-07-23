import socket
import threading
import random
import time
import struct

# Constants
PACKET_SIZE = 1024
WINDOW_SIZE = 5
TIMEOUT = 0.5
LOSS_RATE = 0.1
ERROR_RATE = 0.1

# Packet structure: [seq_num, ack_num, flags, data]
def create_packet(seq_num, ack_num, flags, data):
    header = struct.pack('!IIB', seq_num, ack_num, flags)
    return header + data

def parse_packet(packet):
    header = packet[:9]
    data = packet[9:]
    seq_num, ack_num, flags = struct.unpack('!IIB', header)
    return seq_num, ack_num, flags, data


class Sender:
    def __init__(self, ip, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(TIMEOUT)
        self.addr = (ip, port)
        self.base = 0
        self.next_seq_num = 0
        self.window = []
        self.lock = threading.Lock()
        self.ack_received = threading.Event()

    def send_packet(self, packet):
        if random.random() < LOSS_RATE:
            print("Packet lost")
            return
        if random.random() < ERROR_RATE:
            packet = self.corrupt_packet(packet)
            print("Packet corrupted")
        self.sock.sendto(packet, self.addr)

    def corrupt_packet(self, packet):
        return packet[:-1] + bytes([packet[-1] ^ 0xFF])

    def send(self, data):
        self.next_seq_num = 0
        self.base = 0
        self.window = []
        thread = threading.Thread(target=self.receive_acks)
        thread.start()

        while self.next_seq_num < len(data) or self.base < self.next_seq_num:
            with self.lock:
                while self.next_seq_num < self.base + WINDOW_SIZE and self.next_seq_num < len(data):
                    packet = create_packet(self.next_seq_num, 0, 0, data[self.next_seq_num].encode())
                    self.send_packet(packet)
                    self.window.append(packet)
                    self.next_seq_num += 1

            self.ack_received.wait(TIMEOUT)
            self.ack_received.clear()

        thread.join()

    def receive_acks(self):
        while True:
            try:
                packet, _ = self.sock.recvfrom(PACKET_SIZE)
                seq_num, ack_num, flags, data = parse_packet(packet)
                with self.lock:
                    if ack_num >= self.base:
                        self.base = ack_num + 1
                        self.window = self.window[1:]
                        self.ack_received.set()
            except socket.timeout:
                with self.lock:
                    for packet in self.window:
                        self.send_packet(packet)

    def close(self):
        self.sock.close()

class Receiver:
    def __init__(self, ip, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((ip, port))
        self.expected_seq_num = 0
        self.received_data = []

    def receive(self):
        while True:
            packet, addr = self.sock.recvfrom(PACKET_SIZE)
            seq_num, ack_num, flags, data = parse_packet(packet)

            if random.random() < LOSS_RATE:
                print("ACK lost")
                continue

            if seq_num == self.expected_seq_num:
                self.received_data.append(data.decode())
                self.expected_seq_num += 1

            ack_packet = create_packet(0, self.expected_seq_num - 1, 1, b'')
            self.sock.sendto(ack_packet, addr)

    def close(self):
        self.sock.close()

    def get_data(self):
        return ''.join(self.received_data)
    
def main():
    sender = Sender('localhost', 10000)
    receiver = Receiver('localhost', 10000)

    receiver_thread = threading.Thread(target=receiver.receive)
    receiver_thread.start()

    data = "Hello, this is a test message for our reliable transfer protocol."
    sender.send(data)

    time.sleep(2)
    sender.close()
    receiver.close()

    print("Received data:", receiver.get_data())

if __name__ == "__main__":
    main()