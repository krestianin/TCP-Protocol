import socket
import threading
import struct
import time

# Packet flags
SYN = 1
ACK = 2
FIN = 4
DATA = 8

# Packet structure using struct for better control over byte data
def create_packet(seq_num, ack_num, flags, payload):
    header = struct.pack('!IIH', seq_num, ack_num, flags)
    return header + payload

def parse_packet(packet):
    header = packet[:10]
    seq_num, ack_num, flags = struct.unpack('!IIH', header)
    payload = packet[10:]
    return seq_num, ack_num, flags, payload

# Function to print packet details
def print_packet_details(seq_num, ack_num, flags, payload, sender=True):
    role = "Sender" if sender else "Receiver"
    print(f"{role} - Seq: {seq_num}, Ack: {ack_num}, Flags: {flags}, Payload: {payload.decode()}")


# Sender class
class ReliableSender:
    def __init__(self, dest_ip, dest_port):
        self.dest_ip = dest_ip
        self.dest_port = dest_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1)
        self.seq_num = 0
        self.ack_num = 0
        self.window_size = 5
        self.base = 0
        self.lock = threading.Lock()
        self.ack_received = threading.Event()
        self.connected = False

    def connect(self):
        self._send_packet(SYN)
        response = self._wait_for_ack(SYN)
        if response:
            self.connected = True
            print("Sender: Connection established")
        else:
            print("Sender: Connection failed")

    def send(self, data):
        if not self.connected:
            raise Exception("Connection not established")
        segments = [data[i:i+1000] for i in range(0, len(data), 1000)]
        threading.Thread(target=self._receive_ack).start()

        for segment in segments:
            with self.lock:
                if self.seq_num < self.base + self.window_size:
                    self._send_packet(DATA, segment)
                    self.seq_num += 1

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

    def _wait_for_ack(self, flag):
        while True:
            try:
                data, _ = self.sock.recvfrom(1024)
                seq_num, ack_num, flags, _ = parse_packet(data)
                if flags & flag:
                    self.ack_num = ack_num
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
                        self.base = ack_num + 1
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
        self.expected_seq_num = 0
        self.connected = False

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
            elif flags & DATA and seq_num == self.expected_seq_num:
                print(f"Receiver: Received: {payload.decode()}")
                self.expected_seq_num += 1
                self._send_ack(seq_num, addr, DATA)

    def _send_ack(self, seq_num, addr, flag):
        ack_packet = create_packet(0, seq_num, flag | ACK, b'')
        self.sock.sendto(ack_packet, addr)
        print_packet_details(0, seq_num, flag | ACK, b'')

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
