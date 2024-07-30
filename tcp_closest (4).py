#Version with manual SYN
import socket
import threading
import time
import struct
import sys
import random
# Constants
MSS = 5  # Maximum Segment Size
TIMEOUT = 1000  # Retransmission timeout in seconds
WINDOW_SIZE = 27  # Example window size
INITIAL_CWND = 1  # Initial congestion window size
SSTHRESH = 4  # Slow start threshold


# Packet format: SEQ_NUM (4 bytes) | ACK_NUM (4 bytes) | FLAGS (1 byte) | WINDOW (4 bytes) | DATA
PACKET_FORMAT = '!IIBI'

class ReliableUDP:
    def __init__(self, local_port, remote_address, remote_port):
        self.local_address = ('', local_port)
        self.remote_address = (remote_address, remote_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.local_address)
        self.send_base = 0
        self.next_seq_num = 0
        self.window_size = WINDOW_SIZE
        self.lock = threading.Condition()
        self.timer = None
        self.unacked_packets = {}  # Store unacknowledged packets for retransmission
        self.cwnd = INITIAL_CWND  # Congestion window size
        self.ssthresh = SSTHRESH  # Slow start threshold
        self.expected_seq_num = 0  # Expected sequence number for receiver
        self.connected = False
        self.flag = True
        self.counter = 0
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
            self.ssthresh = max(self.cwnd // 2, 1)
            self.cwnd = INITIAL_CWND
            self.start_timer()
            for seq in sorted(self.unacked_packets.keys()):
                packet = self.unacked_packets.get(seq)
                if packet:
                    print(f"Client: Resending packet: seq_num={seq}")
                    self.sock.sendto(packet, self.remote_address)




    def send(self, data):
        data_chunks = [data[i:i+MSS] for i in range(0, len(data), MSS)]
        for chunk in data_chunks:
            packet = self.create_packet(chunk, seq_num=self.next_seq_num)
            # print(packet)
            with self.lock:
                while self.next_seq_num >= self.send_base + min(self.window_size, self.cwnd) * MSS:
                    # print("\n")
                    # print(min(self.window_size, self.cwnd))
                    # print("\n")
                    print(F"self.next_seq_num {self.next_seq_num}")
                    print(f"self.send_base {self.send_base}")
                    print(f"self.window_size {self.window_size}")
                    self.lock.wait()
                    # time.sleep(5)

                # if self.next_seq_num < self.send_base + min(self.window_size, self.cwnd) * MSS:
                print(f"Client: Sending packet: seq_num={self.next_seq_num}")


                if chunk == b'four' and not self.flag:
                    self.flag = True
                else:
                    self.sock.sendto(packet, self.remote_address)


                self.unacked_packets[self.next_seq_num] = packet
                self.next_seq_num += len(chunk)  # Increment by the length of the chunk
                if self.send_base == self.next_seq_num - len(chunk):
                    self.start_timer()

    def receive_ack(self):
        duplicate_ack_count = 0
        last_ack_num = -1
        while self.connected:
            try:
                packet, _ = self.sock.recvfrom(2048)
                seq_num, ack_num, flags, new_window_size = struct.unpack(PACKET_FORMAT, packet[:13])
                ack_flag = flags & 0x01
                fin_flag = (flags >> 1) & 1
                print(fin_flag)
                if fin_flag and ack_flag:
                    print(f"Client: Received ACK for FIN: ack_num={ack_num}")
                    self.connected = False
                    self.sock.close()
                    break

                with self.lock:
                    if ack_num > self.send_base:
                        duplicate_ack_count = 0  # Reset duplicate ACK count if new ACK is received
                        print(f"Client: Received ACK: ack_num={ack_num}, window_size={self.window_size}")
                        while self.send_base < ack_num:
                            self.unacked_packets.pop(self.send_base, None)
                            self.send_base += 1
                        self.update_cwnd()  # Update congestion window
                        if self.send_base == self.next_seq_num:
                            self.stop_timer()
                        else:
                            self.start_timer()
                        last_ack_num = ack_num

                        # print("Notifying threads")
                        self.lock.notify_all()  # Notify the sender that window space is available
                        
                    elif ack_num == last_ack_num:
                        duplicate_ack_count += 1
                        if duplicate_ack_count >= 3:
                            print(f"Client: Fast retransmit due to 3 duplicate ACKs for seq_num={self.send_base}")
                            self.ssthresh = max(self.cwnd // 2, 1)
                            self.cwnd = INITIAL_CWND
                            if self.send_base in self.unacked_packets:
                                self.sock.sendto(self.unacked_packets[self.send_base], self.remote_address)
                            duplicate_ack_count = 0  # Reset duplicate ACK count after fast retransmit
                    else:
                        print(f"Client: Received duplicate ACK: ack_num={ack_num}")
                sys.stdout.flush()
            except ConnectionResetError:
                print("Connection reset by peer")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                break


    def update_cwnd(self):
        if self.cwnd < self.ssthresh:
            # Slow start phase
            self.cwnd += 1
            print(f"Slow start: cwnd increased to {self.cwnd}, ssthresh={self.ssthresh}")

        else:
            # Congestion avoidance phase
            self.counter += 1
            if self.counter == self.cwnd - 1:
                self.cwnd += 1
                self.counter = 0
            print(f"Congestion avoidance: cwnd increased to {self.cwnd}, ssthresh={self.ssthresh}")
 
        # print(self.cwnd)

    def create_packet(self, data, seq_num=None, ack_num=None, ack_flag=False, fin_flag=False, syn_flag=False, window_size=None):
        if seq_num is None:
            seq_num = self.next_seq_num
        if ack_num is None:
            ack_num = 0
        if window_size is None:
            window_size = self.window_size
        flags = ack_flag | (fin_flag << 1) | (syn_flag << 2)
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
        seq_num_proposed = 0
        self.send_base = seq_num_proposed
        self.next_seq_num = seq_num_proposed

        while not self.connected:
            syn_packet = self.create_packet(data=b'', seq_num=seq_num_proposed, ack_num=0, syn_flag=True, ack_flag=False)
            self.sock.sendto(syn_packet, self.remote_address)
            print("Client: Sending SYN")

            self.sock.settimeout(5)

            try:
                # Wait for SYN-ACK
                packet, _ = self.sock.recvfrom(2048)
                seq_num, ack_num, flags, window_size = struct.unpack(PACKET_FORMAT, packet[:13])
                syn_flag = (flags >> 2) & 1
                ack_flag = flags & 1

                if syn_flag and ack_flag and ack_num == seq_num_proposed + 1:
                    # Received SYN-ACK, send ACK
                    self.expected_seq_num = seq_num
                    self.send_base += 1
                    self.next_seq_num += 1
                    ack_packet = self.create_packet(data=b'', seq_num=ack_num, ack_num=seq_num + 1, ack_flag=True, syn_flag=False)
                    self.sock.sendto(ack_packet, self.remote_address)
                    self.connected = True
                    print("Client: Received SYN-ACK, sending ACK, connection established")
                    break
            except socket.timeout:
                print("Client: SYN-ACK not received, waiting to check connection status")

            # Second wait cycle to check self.connected
            if not self.connected:
                start_time = time.time()
                while time.time() - start_time < 10:
                    if self.connected:
                        break
                    time.sleep(0.1)  # Check every 100ms
                if self.connected:
                    break
                if not self.connected:
                    print("Client: Connection not established, resending SYN")

        # Reset the socket to blocking mode
        self.sock.settimeout(None)

    def accept(self):
            packet, _ = self.sock.recvfrom(2048)
            seq_num, ack_num, flags, window_size = struct.unpack(PACKET_FORMAT, packet[:13])
            syn_flag = (flags >> 2) & 1
            ack_flag = flags & 1

            if syn_flag and not ack_flag:

                print("Server: Received SYN")
                # Send SYN-ACK
                seq_num_proposed_other = seq_num
                self.expected_seq_num = seq_num_proposed_other + 1

                syn_ack_packet = self.create_packet(data=b'', seq_num=ack_num, ack_num=seq_num_proposed_other+1, ack_flag=True, syn_flag=True)
                self.sock.sendto(syn_ack_packet, self.remote_address)
                print("Server: Sending SYN-ACK")

                # Wait for ACK
                ack_packet, _ = self.sock.recvfrom(2048)
                seq_num, ack_num, flags, _ = struct.unpack(PACKET_FORMAT, ack_packet[:13])
                syn_flag = (flags >> 2) & 1
                ack_flag = flags & 1

                if ack_flag and not syn_flag and ack_num == seq_num_proposed_other+1:
                    self.send_base += 1
                    self.next_seq_num += 1
                    print("Server: Received ACK, connection established")
                    # self.remote_address = addr
                    self.connected = True
                    return
                


    # def close(self):
    def close(self):
        # Client sending FIN
        fin_packet = self.create_packet(b'', fin_flag=True)
        self.sock.sendto(fin_packet, self.remote_address)
        print("Client: Sending FIN")
        self.fin_sent = True

        # Wait for ACK
        try:
            ack_packet, _ = self.sock.recvfrom(2048)
            _, ack_num, ack_flag, _ = struct.unpack(PACKET_FORMAT, ack_packet[:13])
            if ack_flag:
                print(f"Client: Received ACK for FIN: ack_num={ack_num}")

            # Wait for FIN from server
            fin_packet, _ = self.sock.recvfrom(2048)
            seq_num, _, fin_flag, _ = struct.unpack(PACKET_FORMAT, fin_packet[:13])
            if fin_flag:
                print(f"Client: Received FIN from server: seq_num={seq_num}")

                # Send ACK for FIN
                ack_packet = self.create_packet(b'', ack_num=seq_num, ack_flag=True)
                self.sock.sendto(ack_packet, self.remote_address)
                print(f"Client: Sending ACK for server FIN: ack_num={seq_num}")

        except ConnectionResetError:
            print("Connection closed by peer")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            self.connected = False
            self.sock.close()

    def receive_data(self):
        while self.connected:
            try:
                packet, addr = self.sock.recvfrom(2048)
                seq_num, ack_num, flags, window_size = struct.unpack(PACKET_FORMAT, packet[:13])
                ack_flag = flags & 0x01
                fin_flag = (flags & 0x02) >> 1
                # print(f'{flags:08b}')
                data = packet[13:]

                if fin_flag:
                    print(f"Server: Received FIN: seq_num={seq_num}")
                    # Send ACK for FIN
                    ack_packet = self.create_packet(b'', ack_num=seq_num + 1, ack_flag=True, fin_flag=True)
                    self.sock.sendto(ack_packet, addr)
                    print(f"Server: Sending ACK for FIN: ack_num={seq_num + 1}")
                    self.connected = False
                    break
                if seq_num == self.expected_seq_num:
                    print(f"Server: Data received: seq_num={seq_num}, data={data}...")  # Print data
                    ack_packet = self.create_packet(b'', ack_num=seq_num + len(data), ack_flag=True, window_size=self.window_size)
                    self.sock.sendto(ack_packet, addr)
                    print(f"Server: Sending ACK: ack_num={seq_num + len(data)}")
                    self.expected_seq_num += len(data)  # Increment expected_seq_num by the length of the data received
                else:
                    # Send ACK for the last correctly received packet
                    ack_packet = self.create_packet(b'', ack_num=self.expected_seq_num, ack_flag=True, window_size=self.window_size)
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
    #                 self.sock.close()
    #                 break

    #         except ConnectionResetError:
    #             print("Connection reset by peer")
    #             break
    #         except Exception as e:
    #             print(f"Unexpected error: {e}")
    #             break


def sender_main():
    local_port = 8000
    remote_address = '207.23.216.87'
    remote_port = 8000

    reliable_sender = ReliableUDP(local_port, remote_address, remote_port)
    reliable_sender.connect()
    print("Connect function ended")

    receiver_thread = threading.Thread(target=reliable_sender.receive_ack)
    receiver_thread.start()

    # Send multiple packets of different sizes to test
    messages = [
        b'twoss',
        # b'fours',
        # b'crash',
        # b'someo',
        # b'great',
        # b'111',
        # b'22222',
        # b'33333',
        # b'44444',
        # b'55555',
        # b'66666',
        # b'77777',
        # b'88888',
        # b'99999',
        # b'A0000',
        # b'A1111',
        # b'A2222',
        # b'A3333',
        # b'A4444',
        # b'A5555',
        # b'A6666',
        # b'A7777',
        # b'A8888',
        # b'A9999',
        # b'B0000',
        # b'B1111',
        # b'B2222',
        # b'B3333',
        # b'B4444',
        # b'B5555',
        # b'B5555',
        # b'B5555',
        # b'B5555',
        # b'B5555',
        # b'B0000',
        # b'B1111',
        # b'B2222',
        # b'B3333',
        # b'B4444',
        # b'B5555',
        # b'B5555',
        # b'B5555',
        # b'B5555',
        # b'B5555',
    ]

    for msg in messages:
        reliable_sender.send(msg)

    reliable_sender.close()
    receiver_thread.join()

def receiver_main():
    local_port = 8001
    #142.58.83.132
    remote_address = '207.23.216.87'
    remote_port = 8001

    reliable_receiver = ReliableUDP(local_port, remote_address, remote_port)
    reliable_receiver.accept()
    reliable_receiver.receive_data()

    # data_thread = threading.Thread(target=reliable_receiver.receive_data)
    # fin_thread = threading.Thread(target=reliable_receiver.handle_server_fin)

    # data_thread.start()
    # fin_thread.start()

    # data_thread.join()
    # fin_thread.join()

if __name__ == '__main__':
    receiver_thread = threading.Thread(target=receiver_main)
    sender_thread = threading.Thread(target=sender_main)
    
    receiver_thread.start()
    time.sleep(3)
    sender_thread.start()

    receiver_thread.join()
    sender_thread.join()



## if sender has recieved a FinBit = 1 it should finish sending and close the connection by .
## simulate the loss for congestion avoidance
## Fast retransmit due to 3 duplicate ACKs
## Client: Sending SYN
## Client: Sending packet: seq_num=0