import socket
import threading
import time
import struct

# Constants
MSS = 4096  # Maximum Segment Size
TIMEOUT = 20  # Retransmission timeout in seconds

# Packet format: SEQ_NUM (4 bytes) | ACK_NUM (4 bytes) | FLAGS (1 byte) | WINDOW (4 bytes) | DATA
PACKET_FORMAT = '!II?I'

class ReliableUDP:
    def __init__(self, local_port, remote_address, remote_port):
        self.local_address = ('', local_port)
        self.remote_address = (remote_address, remote_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.local_address)
        self.send_base = 0
        self.next_seq_num = 0
        self.lock = threading.Lock()
        self.timer = None
        self.unacked_packets = {}  # Store unacknowledged packets for retransmission
        self.expected_seq_num = 0  # Expected sequence number for receiver
        self.connected = False
        # self.fin_sent = False  # To indicate if FIN has been sent

    def start_timer(self):
        if self.timer is not None:
            self.timer.cancel()
        self.timer = threading.Timer(TIMEOUT, self.timeout)
        self.timer.start()

    def stop_timer(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None

    def timeout(self):
        with self.lock:
            print(f"Timeout, retransmitting from seq {self.send_base}")
            self.start_timer()
            for seq in range(self.send_base, self.next_seq_num, MSS):
                packet = self.unacked_packets.get(seq)
                if packet:
                    print(f"Client: Resending packet: seq_num={seq}")
                    self.sock.sendto(packet, self.remote_address)

    def send(self, data):
        data_chunks = [data[i:i+MSS] for i in range(0, len(data), MSS)]
        for chunk in data_chunks:
            packet = self.create_packet(chunk, seq_num=self.next_seq_num)
            print(packet)
            with self.lock:
                print(f"Client: Sending packet: seq_num={self.next_seq_num}")
                self.sock.sendto(packet, self.remote_address)
                self.unacked_packets[self.next_seq_num] = packet
                self.next_seq_num += len(chunk)  # Increment by the length of the chunk
                if self.send_base == self.next_seq_num - len(chunk):
                    self.start_timer()

    def receive_ack(self):
        while self.connected:
            try:
                packet, _ = self.sock.recvfrom(2048)
                ack_num, new_window_size = self.process_ack(packet)
                with self.lock:
                    if ack_num >= self.send_base:
                        print(f"Client: Received ACK: ack_num={ack_num}, window_size={new_window_size}")
                        self.send_base = ack_num + 1
                        if self.send_base == self.next_seq_num:
                            self.stop_timer()
                            # if self.fin_sent:
                            #     break
                        else:
                            self.start_timer()
                        self.unacked_packets.pop(ack_num, None)
            except ConnectionResetError:
                print("Connection reset by peer")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                break

    def create_packet(self, data, seq_num=None, ack_num=None, ack_flag=False, fin_flag=False, window_size=None):
        if seq_num is None:
            seq_num = self.next_seq_num
        if ack_num is None:
            ack_num = 0
        if window_size is None:
            window_size = 0  # Commented out congestion window size
        flags = ack_flag | (fin_flag << 1)
        header = struct.pack(PACKET_FORMAT, seq_num, ack_num, flags, window_size)
        return header + data

    def process_ack(self, packet):
        header = packet[:13]
        seq_num, ack_num, flags, window_size = struct.unpack(PACKET_FORMAT, header)
        ack_flag = flags & 1
        # Process acknowledgment
        if ack_flag:
            return ack_num, window_size
        return -1, window_size

    def connect(self):
        syn_packet = self.create_packet(b'', ack_flag=True)
        self.sock.sendto(syn_packet, self.remote_address)
        print("Client: Sending SYN")
        # Wait for SYN-ACK
        syn_ack_packet, _ = self.sock.recvfrom(2048)
        _, ack_num, ack_flag, _ = struct.unpack(PACKET_FORMAT, syn_ack_packet[:13])
        if ack_flag and ack_num == 0:
            # Send ACK
            ack_packet = self.create_packet(b'', ack_num=1, ack_flag=True)
            self.sock.sendto(ack_packet, self.remote_address)
            self.connected = True
            print("Client: Received SYN-ACK, sending ACK, connection established")

    def accept(self):
        while True:
            syn_packet, addr = self.sock.recvfrom(2048)
            _, _, ack_flag, _ = struct.unpack(PACKET_FORMAT, syn_packet[:13])
            if ack_flag:
                print("Server: Received SYN")
                # Send SYN-ACK
                syn_ack_packet = self.create_packet(b'', ack_num=0, ack_flag=True)
                self.sock.sendto(syn_ack_packet, addr)
                print("Server: Sending SYN-ACK")
                # Wait for ACK
                ack_packet, _ = self.sock.recvfrom(2048)
                _, ack_num, ack_flag, _ = struct.unpack(PACKET_FORMAT, ack_packet[:13])
                if ack_flag and ack_num == 1:
                    print("Server: Received ACK, connection established")
                    self.remote_address = addr
                    self.connected = True
                    return

    # def close(self):
    #     # Client sending FIN
    #     fin_packet = self.create_packet(b'', fin_flag=True)
    #     self.sock.sendto(fin_packet, self.remote_address)
    #     print("Client: Sending FIN")
    #     self.fin_sent = True

    #     # Wait for ACK
    #     try:
    #         ack_packet, _ = self.sock.recvfrom(2048)
    #         _, ack_num, ack_flag, _ = struct.unpack(PACKET_FORMAT, ack_packet[:13])
    #         if ack_flag:
    #             print(f"Client: Received ACK for FIN: ack_num={ack_num}")

    #         # Wait for FIN from server
    #         fin_packet, _ = self.sock.recvfrom(2048)
    #         seq_num, _, fin_flag, _ = struct.unpack(PACKET_FORMAT, fin_packet[:13])
    #         if fin_flag:
    #             print(f"Client: Received FIN from server: seq_num={seq_num}")

    #             # Send ACK for FIN
    #             ack_packet = self.create_packet(b'', ack_num=seq_num, ack_flag=True)
    #             self.sock.sendto(ack_packet, self.remote_address)
    #             print(f"Client: Sending ACK for server FIN: ack_num={seq_num}")

    #     except ConnectionResetError:
    #         print("Connection closed by peer")
    #     except Exception as e:
    #         print(f"Unexpected error: {e}")
    #     finally:
    #         self.connected = False
    #         self.sock.close()

    def receive_data(self):
        while self.connected:
            try:
                packet, addr = self.sock.recvfrom(2048)
                print(packet)
                seq_num, data = self.process_packet(packet)
                if seq_num == self.expected_seq_num:
                    print(f"Server: Data received: seq_num={seq_num}, data={data}...")  # Print data
                    ack_packet = self.create_packet(b'', ack_num=seq_num + len(data), ack_flag=True)
                    self.sock.sendto(ack_packet, addr)
                    print(f"Server: Sending ACK: ack_num={seq_num + len(data)}")
                    self.expected_seq_num += len(data)  # Increment expected_seq_num by the length of the data received
                    print(f"Server: Expected_seq_num: expected_seq_num={self.expected_seq_num}")
                else:
                    # Send ACK for the last correctly received packet
                    ack_packet = self.create_packet(b'', ack_num=self.expected_seq_num, ack_flag=True)
                    self.sock.sendto(ack_packet, addr)
                    print(f"Server: Sending duplicate ACK: ack_num={self.expected_seq_num}")
            except ConnectionResetError:
                print("Connection reset by peer")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                break

    def process_packet(self, packet):
        header = packet[:13]
        seq_num, ack_num, flags, window_size = struct.unpack(PACKET_FORMAT, header)
        data = packet[13:]
        return seq_num, data

    # def handle_server_fin(self):
    #     while self.connected:
    #         try:
    #             # Wait for FIN from client
    #             fin_packet, addr = self.sock.recvfrom(2048)
    #             seq_num, _, flags, _ = struct.unpack(PACKET_FORMAT, fin_packet[:13])
    #             fin_flag = flags & 2
    #             if fin_flag:
    #                 print(f"Server: Received FIN from client: seq_num={seq_num}")

    #                 # Send ACK for FIN
    #                 ack_packet = self.create_packet(b'', ack_num=seq_num, ack_flag=True)
    #                 self.sock.sendto(ack_packet, addr)
    #                 print(f"Server: Sending ACK for client FIN: ack_num={seq_num}")

    #                 # Send FIN
    #                 fin_packet = self.create_packet(b'', fin_flag=True)
    #                 self.sock.sendto(fin_packet, addr)
    #                 print("Server: Sending FIN")

    #                 # Wait for ACK
    #                 ack_packet, _ = self.sock.recvfrom(2048)
    #                 ack_num, _, ack_flag, _ = struct.unpack(PACKET_FORMAT, ack_packet[:13])
    #                 if ack_flag:
    #                     print(f"Server: Received ACK for FIN: ack_num={ack_num}")

    #                 self.connected = False
    #                 break

    #         except ConnectionResetError:
    #             print("Connection reset by peer")
    #             break
    #         except Exception as e:
    #             print(f"Unexpected error: {e}")
    #             break
    #     self.sock.close()

def sender_main():
    local_port = 8000
    remote_address = 'localhost'
    remote_port = 8080

    reliable_sender = ReliableUDP(local_port, remote_address, remote_port)
    reliable_sender.connect()

    receiver_thread = threading.Thread(target=reliable_sender.receive_ack)
    receiver_thread.start()

    # Send multiple packets of different sizes to test
    messages = [
        b'one',
        b'four',
        b'crash',
        b'someone',
        b'greatest'
    ]
    for msg in messages:
        reliable_sender.send(msg)
        time.sleep(3)  # Add a small delay between sends for clarity

    # reliable_sender.close()
    receiver_thread.join()

def receiver_main():
    local_port = 8080
    remote_address = 'localhost'
    remote_port = 8000

    reliable_receiver = ReliableUDP(local_port, remote_address, remote_port)
    reliable_receiver.accept()

    data_thread = threading.Thread(target=reliable_receiver.receive_data)
    # fin_thread = threading.Thread(target=reliable_receiver.handle_server_fin)

    data_thread.start()
    # fin_thread.start()

    data_thread.join()
    # fin_thread.join()

if __name__ == '__main__':
    receiver_thread = threading.Thread(target=receiver_main)
    sender_thread = threading.Thread(target=sender_main)
    
    receiver_thread.start()
    time.sleep(3)  # Ensures the receiver is ready before the sender starts
    sender_thread.start()

    receiver_thread.join()
    sender_thread.join()
