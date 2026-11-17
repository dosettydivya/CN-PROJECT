#!/usr/bin/env python3
"""client.py - exam client.

Usage:  python3 client.py <server_ip> <student_id> [--auto]
  --auto  answers randomly with a short 'thinking' pause (for automated tests).
Every request's round-trip time is saved to latency_<student_id>.csv
"""
import csv
import random
import socket
import sys
import time

PORT = 5000


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    server_ip, student = sys.argv[1], sys.argv[2]
    auto = '--auto' in sys.argv
    rows = []                                   # (student, request, rtt_ms, timestamp)

    t = time.perf_counter()
    s = socket.create_connection((server_ip, PORT), timeout=60)
    rows.append((student, 'CONNECT', round((time.perf_counter() - t) * 1000, 2),
                 round(time.time(), 3)))
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    reader = s.makefile('r', encoding='utf-8', newline='\n')

    def request(msg, label):
        t0 = time.perf_counter()
        s.sendall((msg + '\n').encode('utf-8'))
        reply = reader.readline().strip()
        rtt = (time.perf_counter() - t0) * 1000
        rows.append((student, label, round(rtt, 2), round(time.time(), 3)))
        return reply

    final = None
    reply = request('HELLO|%s' % student, 'HELLO')
    parts = reply.split('|')
    if parts[0] != 'WELCOME':
        print('Server said:', reply)
        sys.exit(1)
    total, seconds = int(parts[1]), int(parts[2])
    print('Connected. %d questions, %d seconds.' % (total, seconds))

    for i in range(total):
        reply = request('GET|%d' % i, 'GET')
        parts = reply.split('|')
        if parts[0] != 'Q':                     # TIMEUP or connection closed
            final = reply
            break
        print('\nQ%d. %s   (time left: %s s)' % (i + 1, parts[2], parts[4]))
        for opt in parts[3].split(';'):
            print('   ' + opt)
        if auto:
            time.sleep(random.uniform(0.3, 1.5))        # pretend to think
            choice = random.choice('ABCD')
            print('   [auto] answer:', choice)
        else:
            choice = input('Your answer (A/B/C/D): ').strip().upper()[:1] or 'A'
        reply = request('ANS|%d|%s' % (i, choice), 'ANS')
        if not reply.startswith('ACK'):
            final = reply
            break

    if final is None:
        final = request('SUBMIT', 'SUBMIT')
    parts = final.split('|')
    if parts[0] in ('RESULT', 'TIMEUP'):
        print('\n%s: you scored %s / %s in %s s' % (
            'TIME UP' if parts[0] == 'TIMEUP' else 'RESULT', parts[1], parts[2], parts[3]))
    else:
        print('\nConnection closed by server (time may be up).')
    s.close()

    with open('latency_%s.csv' % student, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['student', 'request', 'rtt_ms', 'timestamp'])
        w.writerows(rows)
    rtts = [r[2] for r in rows if r[1] in ('GET', 'ANS')]
    if rtts:
        print('Average response time: %.2f ms (max %.2f ms) over %d requests' % (
            sum(rtts) / len(rtts), max(rtts), len(rtts)))


if __name__ == '__main__':
    main()
