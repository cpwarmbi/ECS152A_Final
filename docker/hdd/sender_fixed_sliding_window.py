"""
 @file: sender_sliding_window.py
 @brief: Sliding window congestion control protocol implementation with debugging
 @author: Corbin Warmbier  [cpwarmbier@ucdavis.edu]
          Akhil Sharma     [akhsharma@ucdavis.edu]
 @date: 12.04.2024
"""
import enum
import socket
import time
from collections import deque

# Constants
PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
RCV_ADDR = ("127.0.0.1", 5001)
WINDOW_SIZE = 100

# Globals
seq_id = 0
curr_state = None

# Metrics
total_bytes = 0
packet_delays = []
start_time = None
end_time = None


class State(enum.Enum):
    SENDING_DATA = 1
    SENDING_EOF = 2
    SENDING_FINACK = 3
    COMPLETE = 4


# Initialize UDP Socket
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
    start_time = time.time()
    udp_socket.bind(("0.0.0.0", 5002))
    udp_socket.settimeout(1)

    with open("../file.mp3", "rb") as fp:
        curr_state = State.SENDING_DATA
        packets = deque()  # Sliding window: unacknowledged packets

        while True:
            # Fill the sliding window
            while len(packets) < WINDOW_SIZE and curr_state == State.SENDING_DATA:
                chunk = fp.read(MESSAGE_SIZE)
                packet = seq_id.to_bytes(SEQ_ID_SIZE, byteorder="big", signed=True)  # create packet
                if chunk:
                    # add payload (if any) and send
                    packet += chunk
                    udp_socket.sendto(packet, RCV_ADDR)
                    packets.append((seq_id, time.time(), packet))  # Append seq_id, time_sent, and packet (for easy retransmission)
                    print(f"Sent Packet {seq_id}")
                    seq_id += len(chunk)
                    total_bytes += len(packet)
                else:
                    curr_state = State.SENDING_EOF  # if no more chunks, move to EOF
                    break
            

            # Process ACKs
            try:
                rcv_packet, _ = udp_socket.recvfrom(PACKET_SIZE)
                ack_id = int.from_bytes(rcv_packet[:SEQ_ID_SIZE], byteorder="big", signed=True)
                print(f"Received ACK {ack_id}")
                # Remove ACK'd packets, can assume that any packet under ACK_ID has been ack'd since receiver will send the ACK of the
                # received packeted or expected packeted
                while packets and packets[0][0] < ack_id:
                    seq_id_r, send_time, _ = packets.popleft()
                    packet_delays.append(time.time() - send_time)
                    print(f"Removed Packet {seq_id_r}")

                # Keep pushing FINACK until timeout is received to denote file transfer
                if (curr_state == State.SENDING_EOF and not packets) or curr_state == State.SENDING_FINACK:
                    curr_state = State.SENDING_FINACK
                    packet = seq_id.to_bytes(SEQ_ID_SIZE, byteorder="big", signed=True) + b'==FINACK=='
                    udp_socket.sendto(packet, RCV_ADDR)

            except socket.timeout:
                if curr_state == State.SENDING_FINACK:
                    end_time = time.time()
                    curr_state = State.COMPLETE
                    break
                print("Retransmit All Packets")
                # Retransmit all packets in window
                for seq_id, _, packet in packets:
                    udp_socket.sendto(packet, RCV_ADDR)


# Metric calculations
throughput = 0
average_delay = 0
average_jitter = 0
metric = 0

# Calculate Throughput
elapsed_time = end_time - start_time
if elapsed_time > 0:
    throughput = total_bytes / elapsed_time

# Calculate Avg Packet Delay
if len(packet_delays) > 0:
    average_delay = sum(packet_delays) / len(packet_delays)

# Calculate Jitter
jitter_vals = []
for i in range(1, len(packet_delays)):
    jitter_vals.append(abs(packet_delays[i] - packet_delays[i - 1]))

# Calculate Avg Jitter
if len(jitter_vals) > 0:
    average_jitter = sum(jitter_vals) / len(jitter_vals)

# Calculate Performance Metric
if average_jitter > 0 and average_delay > 0:
    metric = 0.2 * (throughput / 2000) + 0.1 / average_jitter + 0.8 / average_delay

# Report Metrics
print(f"{throughput:.7f},{average_delay:.7f},{average_jitter:.7f},{metric:.7f}")