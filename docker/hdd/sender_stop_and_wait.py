"""
 @file: sender_stop_and_wait.py
 @brief: Stop and wait congestion control protocol implementation
 @author: Corbin Warmbier  [cpwarmbier@ucdavis.edu]
          Akhil Sharma     [akhsharma@ucdavis.edu]
 @date: 12.04.2024
"""
import enum
import socket
import time

# Constants
PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
RCV_ADDR = ("127.0.0.1", 5001)

# Globals
seq_id = 0
curr_state = None
ack_rcv = False

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
    
    with open("file.mp3", "rb") as fp:
        curr_state = State.SENDING_DATA
        while True:
            # Create data packet
            packet = seq_id.to_bytes(SEQ_ID_SIZE, byteorder="big", signed=True)

            # Prepare the packet based on the current state
            if curr_state == State.SENDING_DATA:
                chunk = fp.read(MESSAGE_SIZE)
                if chunk:
                    packet += chunk
                    total_bytes += PACKET_SIZE
                else:
                    curr_state = State.SENDING_EOF

            elif curr_state == State.SENDING_FINACK:
                # Create FINACK packet
                packet += b'==FINACK=='
            
            # else curr_state is EOF => append empty payload b''

            ack_rcv = False
            packet_send_time = time.time()
            while not ack_rcv:
                try:
                    udp_socket.sendto(packet, RCV_ADDR)
                    rcv_packet, _ = udp_socket.recvfrom(PACKET_SIZE)  # wait for response

                    if curr_state == State.SENDING_DATA:
                        ack_id = int.from_bytes(rcv_packet[:SEQ_ID_SIZE], byteorder="big", signed=True)
                        if ack_id == seq_id + len(chunk):
                            packet_delays.append(time.time() - packet_send_time)
                            seq_id += len(chunk)
                            ack_rcv = True

                    elif curr_state == State.SENDING_EOF:
                        if b'fin' in rcv_packet:
                            packet_delays.append(time.time() - packet_send_time)
                            curr_state = State.SENDING_FINACK
                            ack_rcv = True
                    
                    # else curr_state == FINACK and no response should be received
                    # if response is received, send again until a timeout occurs

                except socket.timeout:
                    if curr_state == State.SENDING_FINACK:
                        curr_state = State.COMPLETE
                        ack_rcv = True
                        break
                    # else keep retrying to send packet
            
            if curr_state == State.COMPLETE:
                end_time = time.time()
                break

# Metric calculations
throughput = 0
average_delay = 0
average_jitter = 0
metric = 0

# Calculate Throughput
elapsed_time = end_time - start_time
if elapsed_time > 0:
    throughput = total_bytes / (end_time - start_time)

# Calculate Avg Packet Delay
if len(packet_delays) > 0:
    average_delay = sum(packet_delays) / len(packet_delays)

# Calculate Jitter
jitter_vals = []
for i in range(1, len(packet_delays)):
    jitter_vals.append(abs(packet_delays[i] - packet_delays[i-1]))

# Calculate Avg Jitter
if len(jitter_vals) > 0:
    average_jitter = sum(jitter_vals) / len(jitter_vals)

# Calculate Performance Metric
if average_jitter > 0 and average_delay > 0:
    metric = 0.2 * (throughput / 2000) + 0.1 / average_jitter + 0.8 / average_delay

# Report Metrics
print(f"{throughput:.7f},{average_delay:.7f},{average_jitter:.7f},{metric:.7f}")