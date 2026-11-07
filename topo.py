#!/usr/bin/env python3
"""topo.py - Mininet network for the Online Examination project.
Layout: 1 switch (s1), 1 exam server, 5 student hosts, 2 'noise' hosts.
The server is linked FIRST, so s1-eth1 is always the server-facing port.
Run: sudo python3 topo.py
"""
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
NUM_STUDENTS = 5
def build():
    net = Mininet(controller=None, switch=OVSSwitch, autoSetMacs=True)
    info('*** Adding remote controller (Ryu)\n')
    net.addController('c0', controller=RemoteController,
    ip='127.0.0.1', port=6653)
    info('*** Adding switch\n')
    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    info('*** Adding hosts\n')
    server = net.addHost('server', ip='10.0.0.100/24')
    students = [net.addHost('h%d' % i, ip='10.0.0.%d/24' % i) for i in range(1, NUM_STUDENTS + 1)]
    noise = [net.addHost('n1', ip='10.0.0.201/24'),
    net.addHost('n2', ip='10.0.0.202/24')]
    info('*** Adding links (server first -> s1-eth1)\n')
    net.addLink(server, s1)
    for host in students + noise:
        net.addLink(host, s1)
    net.start()
    info('\n*** Network is up. Server = 10.0.0.100, exam port = 5000\n')
    info('*** Next: mininet> sh bash setup_qos.sh\n\n')
    CLI(net)
    net.stop()
if __name__ == '__main__':
    setLogLevel('info')
    build()
