import socket
import threading
import time
import struct
import sys
import random
from scapy.all import IP, UDP, Raw

MSS = 5
TIMEOUT = 5
WINDOW_SIZE = 27
INITIAL_CWND = 1
SSTHRESH = 4

# seq_num (4 bytes) | ack_num (4 bytes) | flags (1 byte) | window (4 bytes) | data
PACKET_FORMAT = '!IIBI'

class ReliableUDP:
    def __init__(self, local_port, remote_address, remote_port):
        self.local_address = ('', local_port)
        self.remote_address = (remote_address, remote_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.local_address)

        # First unacked packet
        self.send_base = 0
        # Next paccket to be sent
        self.next_seq_num = 0
        # Maximum window for flow control
        self.window_size = WINDOW_SIZE
        self.lock = threading.Condition()
        self.timer = None
        # Store unacknowledged packets for retransmission
        self.unacked_packets = {}  
        # Congestion window size
        self.cwnd = INITIAL_CWND  
        # Slow start threshold
        self.ssthresh = SSTHRESH  
        # Expected sequence number for receiver
        self.expected_seq_num = 0 
        # Connection variable 
        self.connected = False
        # Testing flag to imitate package loss
        self.flag = False
        # To indicate if FIN has been sent
        self.fin_sent = False 
        self.fin_timer = None

        self.counter = 0



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
                    print(F"self.next_seq_num {self.next_seq_num}")
                    print(f"self.send_base {self.send_base}")
                    print(f"self.window_size {self.window_size}")
                    self.lock.wait()
                    time.sleep(5)

                print(f"Client: Sending packet: seq_num={self.next_seq_num}")


                # if chunk == b'A3333' and not self.flag:
                #     self.flag = True
                # else:
                #     self.sock.sendto(bytes(packet), self.remote_address)

                # if chunk == b'A3333' and not self.flag:
                #     packet = IP(dst=self.remote_address[0]) / UDP(sport=8001, dport=self.remote_address[1], chksum=0xFFFF) / Raw(load=chunk)
                #     self.sock.sendto((packet), self.remote_address)
                #     self.flag = True
                # else:
                #     self.sock.sendto((packet), self.remote_address)
                
                self.sock.sendto((packet), self.remote_address)
                
                self.unacked_packets[self.next_seq_num] = packet
                self.next_seq_num += len(chunk)
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

                if ack_flag and self.fin_sent:
                    # print(f"Client: Received ACK: ack_num={ack_num}, window_size={new_window_size}")
                    if ack_num == self.next_seq_num + 1:
                        print(f"Client: Received ACK for FIN: ack_num={ack_num}")
                        self.stop_fin_timer()
                        self.connected = False
                        self.sock.close()
                        break

                # if fin_flag:
                #     print(f"Client: Received FIN: seq_num={seq_num}")
                #     ack_packet = self.create_packet(b'', ack_num=seq_num + 1, ack_flag=True)
                #     self.sock.sendto(ack_packet, self.remote_address)
                #     print(f"Client: Sending ACK for server FIN: ack_num={seq_num + 1}")
                #     self.stop_fin_timer()
                #     self.connected = False
                #     self.sock.close()
                #     break
                
                with self.lock:
                    if ack_num > self.send_base:
                        duplicate_ack_count = 0  # Reset duplicate ACK count if new ACK is received
                        print(f"Client: Received ACK: ack_num={ack_num}, window_size={new_window_size}")
                        while self.send_base < ack_num:
                            self.unacked_packets.pop(self.send_base, None)
                            self.send_base += 1
                        self.update_cwnd()  # Update congestion window
                        if self.send_base == self.next_seq_num:
                            self.stop_timer()
                        else:
                            self.start_timer()
                        last_ack_num = ack_num

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
        seq_num_proposed = random.randint(0, 1000)
        self.send_base = seq_num_proposed
        self.next_seq_num = seq_num_proposed

        while not self.connected:
            syn_packet = self.create_packet(data=b'', seq_num=seq_num_proposed, ack_num=0, syn_flag=True, ack_flag=False)
            self.sock.sendto(syn_packet, self.remote_address)
            print(f"Client: Sending SYN with seq_num={seq_num_proposed}")

            self.sock.settimeout(5)

            try:
                # Wait for SYN-ACK
                packet, _ = self.sock.recvfrom(2048)
                seq_num, ack_num, flags, window_size = struct.unpack(PACKET_FORMAT, packet[:13])
                syn_flag = (flags >> 2) & 1
                ack_flag = flags & 1

                if syn_flag and ack_flag and ack_num == seq_num_proposed + 1:
                    # Received SYN-ACK, send ACK
                    self.expected_seq_num = seq_num + 1
                    self.send_base = seq_num_proposed + 1
                    self.next_seq_num = seq_num_proposed + 1
                    ack_packet = self.create_packet(data=b'', seq_num=self.next_seq_num, ack_num=seq_num + 1, ack_flag=True, syn_flag=False)
                    self.sock.sendto(ack_packet, self.remote_address)
                    with self.lock:
                        self.connected = True
                        self.lock.notify_all()
                    print(f"Client: Received SYN-ACK with seq_num={seq_num}, sending ACK, connection established")
                    break
            except socket.timeout:
                print("Client: SYN-ACK not received, waiting to check connection status")

            if not self.connected:
                start_time = time.time()
                while time.time() - start_time < 10:
                    if self.connected:
                        return
                    time.sleep(0.1)
                if not self.connected:
                    print("Client: Connection not established, resending SYN")
        self.sock.settimeout(None)





    def accept(self):
        packet, _ = self.sock.recvfrom(2048)
        seq_num, ack_num, flags, window_size = struct.unpack(PACKET_FORMAT, packet[:13])
        syn_flag = (flags >> 2) & 1
        ack_flag = flags & 1

        if syn_flag and not ack_flag:
            print(f"Server: Received SYN with seq_num={seq_num}")
            # Send SYN-ACK
            seq_num_proposed_this = random.randint(0, 1000)
            seq_num_proposed_other = seq_num
            self.expected_seq_num = seq_num_proposed_other + 1

            syn_ack_packet = self.create_packet(data=b'', seq_num=seq_num_proposed_this, ack_num=seq_num_proposed_other + 1, ack_flag=True, syn_flag=True)
            self.sock.sendto(syn_ack_packet, self.remote_address)
            print(f"Server: Sending SYN-ACK with seq_num={seq_num_proposed_this}")

            # Wait for ACK
            ack_packet, _ = self.sock.recvfrom(2048)
            seq_num, ack_num, flags, _ = struct.unpack(PACKET_FORMAT, ack_packet[:13])
            syn_flag = (flags >> 2) & 1
            ack_flag = flags & 1
            # print ("expected seq", self.expected_seq_num, "received seq", ack_num)
            if ack_flag and not syn_flag and seq_num == self.expected_seq_num:
                self.send_base = seq_num_proposed_this + 1
                self.next_seq_num = seq_num_proposed_this + 1
                self.expected_seq_num = seq_num
                with self.lock:
                    self.connected = True
                    self.lock.notify_all()
                print(f"Server: Received ACK with seq_num={seq_num}, connection established")
                return




    def close(self):
        # Client sending FIN
        fin_packet = self.create_packet(b'', fin_flag=True)
        self.sock.sendto(fin_packet, self.remote_address)
        print("Client: Sending FIN")
        self.fin_sent = True

        # Start the FIN retransmission timer
        self.start_fin_timer(fin_packet)

        # Wait for ACK
        try:
            # while self.connected:
                # self.sock.settimeout(5)
            try:
                ack_packet, _ = self.sock.recvfrom(2048)
                _, ack_num, flags, _ = struct.unpack(PACKET_FORMAT, ack_packet[:13])
                ack_flag = flags & 0x01
                fin_flag = (flags >> 1) & 1

                if ack_flag and ack_num == self.next_seq_num + 1:
                    print(f"Client: Received ACK for FINdfsdfdsfsd: ack_num={ack_num}")
                    self.stop_fin_timer()
                    return

                # if fin_flag:
                #     print(f"Client: Received FIN from server: seq_num={ack_num}")

                #     # Send ACK for FIN
                #     ack_packet = self.create_packet(b'', ack_num=ack_num + 1, ack_flag=True)
                #     self.sock.sendto(ack_packet, self.remote_address)
                #     print(f"Client: Sending ACK for server FIN: ack_num={ack_num + 1}")
                #     self.stop_fin_timer()
                #     break
            except socket.timeout:
                if(not self.fin_sent):
                    print("Client: FIN-ACK not received, retransmitting FIN")
                    self.sock.sendto(fin_packet, self.remote_address)
                else:
                    print("Connection closed")


        except ConnectionResetError:
            print("Connection closed by peer")
        except OSError as e:
            print(f"Connection closed")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            self.connected = False
            self.sock.close()

    def start_fin_timer(self, fin_packet):
        if self.fin_timer is not None:
            self.fin_timer.cancel()
        self.fin_timer = threading.Timer(TIMEOUT, self.retransmit_fin, [fin_packet])
        self.fin_timer.start()

    def stop_fin_timer(self):
        if self.fin_timer is not None:
            self.fin_timer.cancel()
            self.fin_timer = None

    def retransmit_fin(self, fin_packet):
        with self.lock:
            print("Timeout, retransmitting FIN")
            self.sock.sendto(fin_packet, self.remote_address)
            self.start_fin_timer(fin_packet)  # Restart the timer for the next retransmission


    def receive_data(self):
        while self.connected:
            try:    
                packet, addr = self.sock.recvfrom(2048)
                seq_num, ack_num, flags, window_size = struct.unpack(PACKET_FORMAT, packet[:13])
                ack_flag = flags & 0x01
                fin_flag = (flags >> 1) & 1
                data = packet[13:]

                if fin_flag:
                    if not self.flag:
                        self.flag = True
                    else:
                        print(f"Server: Received FIN: seq_num={seq_num}")
                        # Send ACK for FIN
                        ack_packet = self.create_packet(b'', ack_num=seq_num + 1, ack_flag=True)
                        self.sock.sendto(ack_packet, addr)
                        print(f"Server: Sending ACK for FIN: ack_num={seq_num + 1}")
                        self.connected = False
                        return
                elif seq_num == self.expected_seq_num:
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



def sender_main():
    local_port = 8000
    remote_address = 'localhost'
    remote_port = 8001

    reliable_sender = ReliableUDP(local_port, remote_address, remote_port)
    reliable_sender.connect()
    print("Connect function ended")

    receiver_thread = threading.Thread(target=reliable_sender.receive_ack)
    receiver_thread.start()

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
    remote_address = 'localhost'
    remote_port = 8000

    reliable_receiver = ReliableUDP(local_port, remote_address, remote_port)
    reliable_receiver.accept()
    reliable_receiver.receive_data()



if __name__ == '__main__':
    receiver_thread = threading.Thread(target=receiver_main)
    sender_thread = threading.Thread(target=sender_main)
    
    receiver_thread.start()
    time.sleep(3)
    sender_thread.start()

    receiver_thread.join()
    sender_thread.join()


## simulate the loss for congestion avoidance
