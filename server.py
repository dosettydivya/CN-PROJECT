#!/usr/bin/env python3
"""server.py - multi-client TCP exam server (runs on host 'server', port 5000).

Protocol (one text line per message, fields separated by '|'):
  client -> HELLO|<student_id>        server -> WELCOME|<num_questions>|<seconds>
  client -> GET|<index>               server -> Q|<index>|<text>|<options>|<secs_left>
  client -> ANS|<index>|<A-D>         server -> ACK|<index>|<secs_left>
  client -> SUBMIT                    server -> RESULT|<score>|<total>|<secs_used>
  (time runs out)                     server -> TIMEUP|<score>|<total>|<secs_used>
Run:  python3 server.py        (EXAM_TIME=30 python3 server.py  for a short test)
"""
import csv
import logging
import os
import socket
import threading
import time

HOST = '0.0.0.0'
PORT = 5000                       # DO NOT CHANGE: the SDN controller prioritises 5000
EXAM_DURATION = int(os.environ.get('EXAM_TIME', 120))   # seconds per student
RESULTS_FILE = 'results.csv'

QUESTIONS = [
    {'text': 'Which OSI layer does TCP work at?',
     'options': ['A) Network', 'B) Transport', 'C) Session', 'D) Application'], 'answer': 'B'},
    {'text': 'How many steps are in the TCP connection setup?',
     'options': ['A) 2', 'B) 3', 'C) 4', 'D) 5'], 'answer': 'B'},
    {'text': 'What is the default port of HTTP?',
     'options': ['A) 21', 'B) 25', 'C) 80', 'D) 443'], 'answer': 'C'},
    {'text': 'Which of these protocols is connectionless?',
     'options': ['A) TCP', 'B) UDP', 'C) FTP', 'D) SMTP'], 'answer': 'B'},
    {'text': 'Which device forwards packets between networks using IP addresses?',
     'options': ['A) Hub', 'B) Switch', 'C) Router', 'D) Repeater'], 'answer': 'C'},
    {'text': 'In SDN, which component makes the forwarding decisions?',
     'options': ['A) Controller', 'B) Cable', 'C) NIC', 'D) Modem'], 'answer': 'A'},
    {'text': 'Which protocol connects an SDN controller to a switch?',
     'options': ['A) OpenFlow', 'B) SMTP', 'C) DNS', 'D) POP3'], 'answer': 'A'},
    {'text': 'Which TCP flag is used to close a connection?',
     'options': ['A) SYN', 'B) ACK', 'C) FIN', 'D) PSH'], 'answer': 'C'},
    {'text': 'How many bits are in an IPv4 address?',
     'options': ['A) 16', 'B) 32', 'C) 64', 'D) 128'], 'answer': 'B'},
    {'text': 'Which command tests whether a host is reachable?',
     'options': ['A) ping', 'B) cd', 'C) ls', 'D) cat'], 'answer': 'A'},
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s  %(message)s')
file_lock = threading.Lock()


def send(conn, msg):
    conn.sendall((msg + '\n').encode('utf-8'))


def score_of(answers):
    return sum(1 for i, q in enumerate(QUESTIONS) if answers.get(i) == q['answer'])


def finish(conn, student, answers, start, status):
    """Calculate the result, save it, send it to the client."""
    score, total = score_of(answers), len(QUESTIONS)
    used = time.time() - start
    with file_lock:
        new_file = not os.path.exists(RESULTS_FILE)
        with open(RESULTS_FILE, 'a', newline='') as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(['student', 'score', 'total', 'seconds_used', 'status'])
            w.writerow([student, score, total, round(used, 1), status])
    send(conn, '%s|%d|%d|%.1f' % ('TIMEUP' if status == 'timeup' else 'RESULT',
                                  score, total, used))
    logging.info('%s finished: %d/%d (%s)', student, score, total, status)


def handle_client(conn, addr):
    student, answers, start = '?', {}, time.time()
    try:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        reader = conn.makefile('r', encoding='utf-8', newline='\n')
        parts = reader.readline().strip().split('|')
        if parts[0] != 'HELLO' or len(parts) < 2:
            send(conn, 'ERR|expected HELLO|<student_id>')
            return
        student = parts[1]
        start = time.time()
        deadline = start + EXAM_DURATION            # the exam timer
        send(conn, 'WELCOME|%d|%d' % (len(QUESTIONS), EXAM_DURATION))
        logging.info('%s connected from %s', student, addr[0])

        while True:
            left = deadline - time.time()
            if left <= 0:
                finish(conn, student, answers, start, 'timeup')
                return
            conn.settimeout(left)                   # wake up when time is over
            try:
                line = reader.readline()
            except socket.timeout:
                finish(conn, student, answers, start, 'timeup')
                return
            if not line:                            # client disconnected
                logging.info('%s disconnected early', student)
                return
            parts = line.strip().split('|')
            cmd, left = parts[0], max(0, int(deadline - time.time()))
            if cmd == 'GET' and len(parts) == 2 and parts[1].isdigit() \
                    and int(parts[1]) < len(QUESTIONS):
                i = int(parts[1])
                q = QUESTIONS[i]
                send(conn, 'Q|%d|%s|%s|%d' % (i, q['text'], ';'.join(q['options']), left))
            elif cmd == 'ANS' and len(parts) == 3 and parts[1].isdigit():
                answers[int(parts[1])] = parts[2].upper()
                send(conn, 'ACK|%s|%d' % (parts[1], left))
            elif cmd == 'SUBMIT':
                finish(conn, student, answers, start, 'submitted')
                return
            else:
                send(conn, 'ERR|unknown command')
    except (ConnectionError, OSError) as e:
        logging.info('%s connection problem: %s', student, e)
    finally:
        conn.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(50)
    logging.info('Exam server listening on port %d (exam time %d s)', PORT, EXAM_DURATION)
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()


if __name__ == '__main__':
    main()
