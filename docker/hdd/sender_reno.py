"""
@file: sender_reno.py
@brief: TCP Reno congestion control protocol implementation
@author: Corbin Warmbier  [cpwarmbier@ucdavis.edu]
         Akhil Sharma     [akhsharma@ucdavis.edu]
@date: 12.04.2024
"""
import enum
import select
import socket
import time
from itertools import islice
from collections import deque

# Constants
PACKET_SIZE = 1024
SEQ_ID_SIZE = 4
MESSAGE_SIZE = PACKET_SIZE - SEQ_ID_SIZE
RCV_ADDR = ("127.0.0.1", 5001)
ALPHA = 0.85

# Globals
seq_id_global = 0
curr_state = None
cwnd = 1
ssthresh = 64
duplicate_acks = 0
last_ack = -1
timeout = 1
estimated_RTT = 0
packets_in_transit = 0

# Metrics
total_bytes = 0
packet_delays = []
start_time = None
end_time = None

class State(enum.Enum):
   TIMEOUT = -1
   SLOW_START = 1
   CONGESTION_AVOIDANCE = 2
   SENDING_EOF = 3

def timeout_reset():
   global curr_state, packets_in_transit, cwnd, ssthresh
   curr_state = State.TIMEOUT
   packets_in_transit = 0
   ssthresh = max(cwnd // 2, 1)
   cwnd = 1

# Initialize UDP Socket
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
   start_time = time.time()
   udp_socket.bind(("0.0.0.0", 5002))
   udp_socket.settimeout(1)

   with open("file.mp3", "rb") as fp:
       curr_state = State.SLOW_START
       packets = deque()

       while True:
           while len(packets) < cwnd and (curr_state.value < State.SENDING_EOF.value):
               chunk = fp.read(MESSAGE_SIZE)
               packet = seq_id_global.to_bytes(SEQ_ID_SIZE, byteorder="big", signed=True)  # create packet
               if chunk:
                   # add payload
                   packet += chunk
                   packets.append((seq_id_global, None, packet, False))   # Append seq_id, time_sent, and packet (for easy retransmission)
                   seq_id_global += len(chunk)
                   total_bytes += len(packet)
               else:
                   curr_state = State.SENDING_EOF  # if no more chunks, move to EOF
                   break
            
            # STEP 1: SEND PACKET
           if packets and int(cwnd) - packets_in_transit > 0:
                for i, (seq_id, send_time, packet, in_transit) in enumerate(packets):
                    if not in_transit or curr_state == State.TIMEOUT:
                        if curr_state == State.TIMEOUT:
                            curr_state = State.SLOW_START
                        udp_socket.sendto(packet, RCV_ADDR)
                        packets_in_transit += 1
                        if send_time is None:
                            send_time = time.time()
                        packets[i] = (seq_id, send_time, packet, True)  # in-transit at time.time()
                    if packets_in_transit == int(cwnd):
                        break
           elif curr_state == State.SENDING_EOF:
                packet = seq_id.to_bytes(SEQ_ID_SIZE, byteorder="big", signed=True) + b'==FINACK=='
                udp_socket.sendto(packet, RCV_ADDR)

          
           # STEP 2: READ NEWEST ACK
           try:
               rcv_packet, _ = udp_socket.recvfrom(PACKET_SIZE)
               ack_id = int.from_bytes(rcv_packet[:SEQ_ID_SIZE], byteorder="big", signed=True)

               if ack_id == last_ack:
                   duplicate_acks += 1
                   if duplicate_acks == 3:
                       timeout_reset()
                       duplicate_acks = 0
                       ssthresh = max(cwnd // 2, 1)
                       cwnd = ssthresh
                       curr_state = State.CONGESTION_AVOIDANCE
				       # Clearing ACKs
                       while True:
                           readable, _, _ = select.select([udp_socket], [], [], 0.05)
                           if not readable:
                               # No more ACKs available
                               break
                           udp_socket.recvfrom(PACKET_SIZE)  # discard output
                       for i, (seq_id, send_time, packet, in_transit) in enumerate(packets):
                           if in_transit:
                               packets[i] = (seq_id, send_time, packet, False)
                           else:
                               break
                       packets_in_transit = 0
                       continue
               else:
                   # New ACK received
                   last_ack = ack_id
                   duplicate_acks = 0

                   # Metrics and Estimated RTT calculation
                   sample_RTT = time.time() - send_time
                   estimated_RTT = ALPHA * estimated_RTT + (1 - ALPHA) * sample_RTT  # calculate estimated RTT
                  
                   while packets and packets[0][0] < ack_id:
                       # Remove Packets
                       seq_id, send_time, _, _ = packets.popleft()
                       packets_in_transit -= 1
                       packet_delays.append(sample_RTT)

                       # Update CWND
                       if curr_state == State.SLOW_START:
                           cwnd += 1
                       elif curr_state == State.CONGESTION_AVOIDANCE:
                           cwnd += 1 / cwnd + 1/8  # To acheive linear growth use eqn: MSS^2 / CWND,  actual implementation of TCP (see Stevens - Volume 2) + MSS/8

                   # Recalculate timeout after removing newest packets
                   timeout = 100 * estimated_RTT
           except socket.timeout:
               if curr_state == State.SENDING_EOF:
                   end_time = time.time()
                   break
               timeout_reset()
               continue


           # STEP 3: Check Timeout for Packet 0
           if packets:
               (seq_id, send_time, _, _) = packets[0]
               if send_time is not None and time.time() - send_time >= timeout:
                   timeout_reset()

           # STEP 4: Clean CWND
           # Round CWND up if within 0.1
           if int(cwnd + 0.1) > int(cwnd):
               cwnd = int(cwnd + 0.1)
          
           # Enter Congestion Avoidance
           if curr_state == State.SLOW_START and cwnd >= ssthresh:
               cwnd = ssthresh
               curr_state = State.CONGESTION_AVOIDANCE


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
