#!/usr/bin/env python3
"""run_experiment.py - runs ONE experiment automatically and saves all data.

Run from ~/exam_project with sudo (the Ryu controller must already be running):
    sudo python3 run_experiment.py A --run 1     # no congestion
    sudo python3 run_experiment.py B --run 1     # congestion, controller QoS OFF
    sudo python3 run_experiment.py C --run 1     # congestion, controller QoS ON (QOS=1)

It builds the same network as topo.py, applies the 10 Mbps bottleneck, starts the
exam server, optional iperf noise, and the students, waits until every exam is
finished, then stores everything in results/<scenario>_run<N>/.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.log import setLogLevel

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_IP = '10.0.0.100'
SCENARIOS = {
    'A': {'noise': False, 'desc': 'baseline, no congestion (controller QoS OFF)'},
    'B': {'noise': True, 'desc': 'congestion, controller QoS OFF'},
    'C': {'noise': True, 'desc': 'congestion, controller QoS ON (start ryu with QOS=1)'},
}


def build_network(num_students):
    """Same topology as topo.py: server first, so its switch port is s1-eth1."""
    net = Mininet(controller=None, switch=OVSSwitch, autoSetMacs=True)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    server = net.addHost('server', ip='10.0.0.100/24')
    students = [net.addHost('h%d' % i, ip='10.0.0.%d/24' % i)
                for i in range(1, num_students + 1)]
    noise = [net.addHost('n1', ip='10.0.0.201/24'),
             net.addHost('n2', ip='10.0.0.202/24')]
    net.addLink(server, s1)
    for host in students + noise:
        net.addLink(host, s1)
    return net, server, students, noise


def count_finished(path):
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return max(0, sum(1 for _ in f) - 1)        # minus the header line


def fix_owner(path):
    """Give the result files back to the normal user (we run as root)."""
    uid, gid = os.environ.get('SUDO_UID'), os.environ.get('SUDO_GID')
    if uid is None:
        return
    uid, gid = int(uid), int(gid)
    os.chown(path, uid, gid)
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            os.chown(os.path.join(root, name), uid, gid)


def run_script(name):
    return subprocess.call(['bash', os.path.join(HERE, name)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('scenario', choices=sorted(SCENARIOS))
    ap.add_argument('--run', type=int, default=1, help='run number (default 1)')
    ap.add_argument('--students', type=int, default=5)
    ap.add_argument('--exams', type=int, default=3, help='exams per student per run')
    ap.add_argument('--noise-streams', type=int, default=2, help='iperf streams per noise host')
    ap.add_argument('--exam-time', type=int, default=60, help='seconds allowed per exam')
    args = ap.parse_args()

    if os.geteuid() != 0:
        sys.exit('Please run with sudo:  sudo python3 run_experiment.py %s' % args.scenario)
    sc = SCENARIOS[args.scenario]
    results_root = os.path.join(HERE, 'results')
    outdir = os.path.join(results_root, '%s_run%d' % (args.scenario, args.run))
    if os.path.exists(outdir):
        shutil.rmtree(outdir)
    os.makedirs(outdir)
    print('=== Experiment %s run %d: %s' % (args.scenario, args.run, sc['desc']))
    if args.scenario == 'C':
        print('    (Ryu must have been started with:  QOS=1 ryu-manager exam_controller.py)')
    else:
        print('    (Ryu must have been started WITHOUT QOS=1)')

    setLogLevel('warning')
    net, server, students, noise = build_network(args.students)
    net.start()
    info = {}
    try:
        try:
            if not net.waitConnected(timeout=20):
                sys.exit('Switch could not reach the controller. Is ryu-manager running?')
        except AttributeError:                       # very old Mininet
            time.sleep(3)

        run_script('reset_qos.sh')
        if run_script('setup_qos.sh') != 0:
            sys.exit('setup_qos.sh failed (is port s1-eth1 present?)')
        loss = net.pingAll()
        if loss > 0:
            loss = net.pingAll()
        print('    pingall loss: %s%%' % loss)

        srv_py = os.path.join(HERE, 'server.py')
        cli_py = os.path.join(HERE, 'client.py')
        server.cmd('cd %s && EXAM_TIME=%d python3 %s > server.log 2>&1 &'
                   % (outdir, args.exam_time, srv_py))
        time.sleep(1)

        if sc['noise']:
            server.cmd('cd %s && iperf -s -p 5001 > iperf_server.log 2>&1 &' % outdir)
            time.sleep(1)
            noise_time = args.exams * 25 + 20
            for h in noise:
                h.cmd('cd %s && iperf -c %s -p 5001 -t %d -P %d > noise_%s.txt 2>&1 &'
                      % (outdir, SERVER_IP, noise_time, args.noise_streams, h.name))
            print('    noise started, waiting 5 s for the link to fill up')
            time.sleep(5)

        start = time.time()
        for h in students:
            h.cmd('cd %s && (for k in $(seq 1 %d); do python3 %s %s %s_$k --auto; done)'
                  ' > out_%s.txt 2>&1 &'
                  % (outdir, args.exams, cli_py, SERVER_IP, h.name, h.name))
        print('    %d students started (%d exams each)' % (len(students), args.exams))

        expected = args.students * args.exams
        results_file = os.path.join(outdir, 'results.csv')
        limit = time.time() + args.exams * (args.exam_time + 5) + 30
        done = 0
        while time.time() < limit:
            done = count_finished(results_file)
            if done >= expected:
                break
            time.sleep(1)
        end = time.time()
        print('    finished exams: %d of %d  (%.0f s)' % (done, expected, end - start))

        server.cmd('pkill -x iperf; pkill -f "python3 .*server.py"; pkill -f "python3 .*client.py"')
        port_stats = os.path.join(HERE, 'port_stats.csv')
        if os.path.exists(port_stats):
            shutil.copy(port_stats, os.path.join(outdir, 'port_stats.csv'))
        info = {'scenario': args.scenario, 'run': args.run, 'desc': sc['desc'],
                'start': start, 'end': end, 'students': args.students,
                'exams_per_student': args.exams, 'expected': expected, 'finished': done,
                'noise': sc['noise'], 'noise_streams': args.noise_streams}
        with open(os.path.join(outdir, 'run_info.json'), 'w') as f:
            json.dump(info, f, indent=2)
    finally:
        net.stop()
        run_script('reset_qos.sh')
        fix_owner(results_root)
    print('    saved to', outdir)


if __name__ == '__main__':
    main()
