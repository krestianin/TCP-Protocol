import socket
import threading
import struct
import time
import random

# Packet flags
SYN = 1
ACK = 2
FIN = 4
PSH = 8

# Packet structure using struct for better control over byte data
def create_packet(seq_num, ack_num, flags, payload):
    header = struct.pack('!IIH', seq_num, ack_num, flags)
    return header + payload

def parse_packet(packet):
    header = packet[:10]
    seq_num, ack_num, flags = struct.unpack('!IIH', header)
    payload = packet[10:]
    return seq_num, ack_num, flags, payload

# Function to print packet details with individual flags
def print_packet_details(seq_num, ack_num, flags, payload, sender=True):
    role = "Sender" if sender else "Receiver"
    flags_str = f"SYN: {int(bool(flags & SYN))}, ACK: {int(bool(flags & ACK))}, FIN: {int(bool(flags & FIN))}"
    print(f"{role} - Seq: {seq_num}, Ack: {ack_num}, Flags: {flags_str}, Payload: {payload.decode()}")

# Sender class
class ReliableSender:
    def __init__(self, dest_ip, dest_port, window_size=5, payload_size=1000):
        self.dest_ip = dest_ip
        self.dest_port = dest_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1)
        self.seq_num = random.randint(0, 10000)
        self.ack_num = 0
        self.window_size = window_size
        self.payload_size = payload_size
        self.base = self.seq_num
        self.lock = threading.Lock()
        self.ack_received = threading.Event()
        self.connected = False

    def connect(self):
        self._send_packet(SYN)
        response = self._wait_for_ack(SYN | ACK)
        if response:
            self.connected = True
            print("Sender: Connection established")
        else:
            print("Sender: Connection failed")

    def send(self, data):
        if not self.connected:
            raise Exception("Connection not established")
        segments = [data[i:i + self.payload_size] for i in range(0, len(data), self.payload_size)]
        threading.Thread(target=self._receive_ack).start()

        for segment in segments:
            with self.lock:
                if self.seq_num < self.base + self.window_size:
                    self._send_packet(PSH | ACK, segment)
                    self.seq_num += len(segment)

            if not self.ack_received.wait(timeout=2):
                print(f"Sender: Timeout, resending from {self.base}")
                with self.lock:
                    self.seq_num = self.base

    def close(self):
        self._send_packet(FIN)
        response = self._wait_for_ack(FIN)
        if response:
            self.connected = False
            print("Sender: Connection closed")
        else:
            print("Sender: Failed to close connection")

    def _send_packet(self, flags, payload=b''):
        packet = create_packet(self.seq_num, self.ack_num, flags, payload)
        self.sock.sendto(packet, (self.dest_ip, self.dest_port))
        print_packet_details(self.seq_num, self.ack_num, flags, payload)

    def _wait_for_ack(self, flag):
        while True:
            try:
                data, _ = self.sock.recvfrom(1024)
                seq_num, ack_num, flags, _ = parse_packet(data)
                if flags & ACK and (flags & flag):
                    self.ack_num = ack_num
                    print_packet_details(seq_num, ack_num, flags, b'', sender=False)
                    return True
            except socket.timeout:
                continue
            return False

    def _receive_ack(self):
        while self.connected:
            try:
                data, _ = self.sock.recvfrom(1024)
                seq_num, ack_num, flags, _ = parse_packet(data)
                if flags & ACK:
                    with self.lock:
                        self.base = ack_num
                        print_packet_details(seq_num, ack_num, flags, b'', sender=False)
                        if self.base == self.seq_num:
                            self.ack_received.set()
                        else:
                            self.ack_received.clear()
            except socket.timeout:
                continue

# Receiver class
class ReliableReceiver:
    def __init__(self, local_port):
        self.local_port = local_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', local_port))
        self.expected_seq_num = random.randint(0, 10000)
        self.received_data = {}  # Buffer to store out-of-order packets
        self.connected = False

    def _send_ack(self, seq_num, addr, flag, payload_len=0):
        ack_num = seq_num + payload_len
        ack_packet = create_packet(self.expected_seq_num, ack_num, flag | ACK, b'')
        self.sock.sendto(ack_packet, addr)
        print_packet_details(self.expected_seq_num, ack_num, flag | ACK, b'')

    def listen(self):
        while True:
            data, addr = self.sock.recvfrom(1024)
            seq_num, ack_num, flags, payload = parse_packet(data)
            print_packet_details(seq_num, ack_num, flags, payload, sender=False)

            if flags & SYN:
                self.connected = True
                self._send_ack(seq_num, addr, SYN)
                print("Receiver: Connection established")
            elif flags & FIN:
                self._send_ack(seq_num, addr, FIN)
                self.connected = False
                print("Receiver: Connection closed")
                break
            elif flags & PSH:
                if seq_num == self.expected_seq_num:
                    print(f"Receiver: Received: {payload.decode()}")
                    self.expected_seq_num += len(payload)
                    self._send_ack(seq_num, addr, PSH, payload_len=len(payload))
                    # Deliver buffered packets in order
                    while self.expected_seq_num in self.received_data:
                        next_payload = self.received_data.pop(self.expected_seq_num)
                        print(f"Receiver: Delivered buffered data: {next_payload.decode()}")
                        self.expected_seq_num += len(next_payload)
                else:
                    print(f"Receiver: Out-of-order packet received: Seq {seq_num}, expected {self.expected_seq_num}")
                    self.received_data[seq_num] = payload
                    self._send_ack(seq_num, addr, PSH, payload_len=len(payload))

# Main function to run both sender and receiver
def main():
    receiver = ReliableReceiver(8080)
    sender = ReliableSender('localhost', 8080)

    receiver_thread = threading.Thread(target=receiver.listen)
    receiver_thread.start()

    time.sleep(1)  # Ensure the receiver is ready

    sender.connect()
    sender.send(b"Hello, this is a test message to demonstrate reliable data transfer!")
    sender.close()

if __name__ == "__main__":
    main()
