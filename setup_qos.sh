#!/bin/bash
# setup_qos.sh - 10 Mbps bottleneck + 3 queues on the server-facing switch port.
# queue 0 = default traffic (min 1 Mbps)
# queue 1 = exam traffic (min 6 Mbps)
# queue 2 = other/noise traffic (max 3 Mbps)
PORT=${1:-s1-eth1}
sudo ovs-vsctl -- set port $PORT qos=@newqos -- \
--id=@newqos create qos type=linux-htb other-config:max-rate=10000000 \
queues:0=@q0 queues:1=@q1 queues:2=@q2 -- \
--id=@q0 create queue other-config:min-rate=1000000 other-config:max-rate=10000000 -- \
--id=@q1 create queue other-config:min-rate=6000000 other-config:max-rate=10000000 -- \
--id=@q2 create queue other-config:min-rate=1000000 other-config:max-rate=3000000
echo "QoS applied on $PORT"
