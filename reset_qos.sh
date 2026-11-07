#!/bin/bash
# reset_qos.sh - remove all QoS settings (use before re-running setup_qos.sh)
sudo ovs-vsctl clear port ${1:-s1-eth1} qos
sudo ovs-vsctl --all destroy qos -- --all destroy queue
echo "QoS cleared"
