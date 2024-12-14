"""
 @file: sender_tcp_vegas.py
 @brief: TCP Vegas congestion control protocol implementation
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

# TCP Vegas Tolerances
ALPHA = 20
BETA = 40
DELTA = 1000

GAMMA = 0.85  # timeout calculation
EPSILION = 0.8  # Data rate tolerance

# Globals
seq_id_global = 0
curr_state = None
cwnd = 1 
duplicate_acks = 0
last_ack = -1
timeout = 1
packets_in_transit = 0
duplicate_flag = False
base_RTT = None
estimated_RTT = 0
expected_throughput = None
acutal_throughput = None
distinguished_bytes = 0
distinguished_out = False
distinguished_state = None

# Metrics
total_bytes = 0
packet_delays = []
start_time = None
end_time = None

class DistinguishedState(enum.Enum):
    EVAL = 0
    CHANGE = 1

class State(enum.Enum):
    TIMEOUT = -1
    EVALUATION = 0
    SLOW_START = 1
    CONGESTION_AVOIDANCE = 2
    SENDING_EOF = 3

# Initialize UDP Socket
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
    start_time = time.time()
    udp_socket.bind(("0.0.0.0", 5002))
    udp_socket.settimeout(1)

    with open("../file.mp3", "rb") as fp:
        curr_state = State.SLOW_START
        distinguished_state = DistinguishedState.CHANGE
        packets = deque()
        while True:
            # print(f"\n[INFO] CWND {cwnd} |  State {curr_state}  | DC {distinguished_state}")
            # print("=================================================================================")
            # Fill deque with packets within the size of cwnd
            while len(packets) < cwnd and (curr_state.value < State.SENDING_EOF.value):
                chunk = fp.read(MESSAGE_SIZE)
                packet = seq_id_global.to_bytes(SEQ_ID_SIZE, byteorder="big", signed=True)  # create packet
                if chunk:
                    # add payload
                    packet += chunk
                    # Packets = seq_id, time_sent, message, in_transit, is_distinguished, data_rate
                    packets.append((seq_id_global, None, packet, False, False, None))
                    seq_id_global += len(chunk)
                    total_bytes += len(packet)
                else:
                    curr_state = State.SENDING_EOF  # if no more chunks, move to EOF
                    break
            
            # STEP 1: SEND PACKET
            if packets and int(cwnd) - packets_in_transit > 0:
                for i, (seq_id, send_time, packet, in_transit, distinguished, _) in enumerate(packets):
                    if not in_transit or curr_state == State.TIMEOUT:
                        # == STATE UPDATES == #
                        packet_message = f"Sent Packet {seq_id}, Data Rate {expected_throughput}"
                        # If no distinguished packet out-bound, set next packet to distinguished
                        if not distinguished_out:
                            distinguished = True
                            distinguished_out = True
                            distinguished_state = DistinguishedState.EVAL if distinguished_state == DistinguishedState.CHANGE else DistinguishedState.CHANGE
                        if curr_state == State.TIMEOUT:
                            curr_state = State.SLOW_START
                            distinguished_bytes -= MESSAGE_SIZE  # offset for retransmits 
                        # Reset throughput tracking on start of new distinguished packet
                        if distinguished:
                           distinguished_bytes = MESSAGE_SIZE
                           packet_message += f", Distinguished"
                        else:
                            distinguished_bytes += MESSAGE_SIZE
                        
                        # Send packet and update packet information
                        print(packet_message)
                        udp_socket.sendto(packet, RCV_ADDR)
                        packets_in_transit += 1
                        if send_time is None:
                            send_time = time.time()
                        packets[i] = (seq_id, send_time, packet, True, distinguished, expected_throughput)  # in-transit at time.time()
                    else:
                        print(f"Packet In-Transit {seq_id}")
                    if packets_in_transit == int(cwnd):
                        break
            elif curr_state == State.SENDING_EOF:
                packet = seq_id_global.to_bytes(SEQ_ID_SIZE, byteorder="big", signed=True) + b'==FINACK=='
                udp_socket.sendto(packet, RCV_ADDR)

            # STEP 2: READ NEWEST ACK
            try:
                rcv_packet, _ = udp_socket.recvfrom(PACKET_SIZE)
                ack_id = int.from_bytes(rcv_packet[:SEQ_ID_SIZE], byteorder="big", signed=True)
                print(f"Received ACK {ack_id}")
                if ack_id == last_ack:
                    duplicate_acks += 1
                    print(f"Duplicate ACK ... Need Logic")
                else:
                    # New ACK received
                    last_ack = ack_id
                    duplicate_acks = 0

                    # Metrics and Estimated RTT calculation
                    packet_RTT = time.time() - send_time
                    if base_RTT is None or base_RTT < 0.0001:
                        base_RTT = packet_RTT
                    elif packet_RTT < base_RTT and packet_RTT > 0.0001:
                        base_RTT = packet_RTT
                    expected_throughput = int(cwnd) / base_RTT
                    print(f"[INFO] Expected Throughput {expected_throughput:.4f}, CWND {int(cwnd)}, BaseRTT {base_RTT:.4f}")
                    estimated_RTT = GAMMA * estimated_RTT + (1 - GAMMA) * packet_RTT  # calculate estimated RTT

                    while packets and packets[0][0] < ack_id:
                        # Remove Packets
                        seq_id, send_time, _, _, distinguished, _ = packets.popleft()
                        print_message = f"Removed Packet {seq_id} "
                        if distinguished:
                            print_message += f"| Distinugished Packet"
                        print(print_message)
                        packets_in_transit -= 1
                        packet_delays.append(packet_RTT)

                        # If not in evaluation period, increase intervals
                        # Update CWND
                        if distinguished_state == DistinguishedState.CHANGE:
                            if curr_state == State.SLOW_START:
                                cwnd += 1
                            elif curr_state == State.CONGESTION_AVOIDANCE:
                                delta_throughput = abs(expected_throughput - acutal_throughput)
                                print(f"[INFO] Delta Throughput {delta_throughput}")
                                if delta_throughput < ALPHA:
                                    cwnd += 1 / cwnd + 1/8  # Linear Growth
                                elif delta_throughput > BETA:
                                    cwnd -= 1 / cwnd - 1/8  # Linear Decay
                        
                        if distinguished:
                            distinguished_out = False
                            # Check if in evaluation period
                            if distinguished_state == DistinguishedState.EVAL:
                                # Do evaluation
                                acutal_throughput = distinguished_bytes / packet_RTT
                                print(f"[INFO] Actual Throughput: {acutal_throughput}")
                                if expected_throughput - acutal_throughput > DELTA:
                                    curr_state = State.CONGESTION_AVOIDANCE
                    
                    # Recalculate timeout after removing newest packets
                    timeout = 1

            except socket.timeout:
                print("[INFO] Experienced Socket Timeout")
                if curr_state == State.SENDING_EOF:
                    end_time = time.time()
                    break

            # STEP 3 Check for Timeouts
            if packets:
                (seq_id, send_time, _, _, _, data_rate) = packets[0]
                if send_time is not None and time.time() - send_time >= timeout:
                    print(f"[TIMEOUT] Packet {seq_id}")  # Packet timeout
                    delta_rate = abs(data_rate - expected_throughput)
                    if delta_rate < EPSILION:
                        # Sent within the same data rate
                        cwnd = max(cwnd // 2, 1)  # Cut CWND by 2
                        print(f"[INFO] Delta Rate {delta_rate} Adjusting CWND to {cwnd}")
                        curr_state = State.TIMEOUT
                    else:
                        print(f"[Info] Delta Rate {delta_rate} Ignoring; Mismatched Data Rates")

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
