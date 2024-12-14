#!/bin/bash

bandwidth=100000
pl=0

# Initial setup
tc qdisc add dev eth0 root handle 1: htb default 1
tc class add dev eth0 parent 1: classid 1:1 htb rate $bandwidth ceil $bandwidth
tc qdisc add dev eth0 parent 1:1 handle 10: netem delay 100ms reorder 7% 40% limit 1000 loss "$pl%"

while true; do
    random_number=$((1 + RANDOM % 10))

    if [ "$random_number" -ge 1 ] && [ "$random_number" -lt 7 ]; then
        bandwidth=$((bandwidth / 2))
        pl=$((pl + 2))
    else
        bandwidth=$((bandwidth / 3))
        pl=$((pl + 3))
    fi

    if [ $bandwidth -lt 2000 ]; then
        bandwidth=100000
    fi
    if [ $pl -gt 20 ]; then
        pl=0
    fi

    tc class change dev eth0 parent 1: classid 1:1 htb rate $bandwidth ceil $bandwidth
    tc qdisc change dev eth0 parent 1:1 handle 10: netem delay 100ms reorder 7% 40% limit 1000 loss "$pl%"
    sleep 1
done
