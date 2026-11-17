#!/usr/bin/env python3
"""analyze.py - turns the experiment data into tables and graphs.

Usage (normal user, no sudo):   python3 analyze.py            (reads ./results)
Output goes to ./analysis_output : summary tables (csv) and graphs (png).

Response time = round-trip time of every GET and ANS request (milliseconds).
Fairness      = Jain's index over the students' mean response times:
                J = (sum x)^2 / (n * sum x^2).  1.0 = every student had the same
                experience; lower values = some students were treated worse.
"""
import csv
import glob
import json
import math
import os
import statistics
import sys
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

RESULTS_DIR = sys.argv[1] if len(sys.argv) > 1 else 'results'
OUT_DIR = 'analysis_output'
LABEL = {'A': 'A: no congestion', 'B': 'B: congestion, no QoS', 'C': 'C: congestion + QoS'}
COLOR = {'A': '#378ADD', 'B': '#D85A30', 'C': '#0F6E56'}


def percentile(vals, p):
    v = sorted(vals)
    k = (len(v) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return v[int(k)] if lo == hi else v[lo] + (v[hi] - v[lo]) * (k - lo)


def jain(xs):
    sq = sum(x * x for x in xs)
    return (sum(xs) ** 2) / (len(xs) * sq) if xs and sq > 0 else float('nan')


def load_run(run_dir):
    per_student = defaultdict(list)
    for path in glob.glob(os.path.join(run_dir, 'latency_*.csv')):
        with open(path) as f:
            for row in csv.DictReader(f):
                if row['request'] in ('GET', 'ANS'):
                    per_student[row['student'].split('_')[0]].append(float(row['rtt_ms']))
    submitted = timeup = 0
    res = os.path.join(run_dir, 'results.csv')
    if os.path.exists(res):
        with open(res) as f:
            for row in csv.DictReader(f):
                if row['status'] == 'timeup':
                    timeup += 1
                else:
                    submitted += 1
    info = {}
    if os.path.exists(os.path.join(run_dir, 'run_info.json')):
        with open(os.path.join(run_dir, 'run_info.json')) as f:
            info = json.load(f)
    return per_student, submitted, timeup, info


def main():
    run_dirs = sorted(d for d in glob.glob(os.path.join(RESULTS_DIR, '*_run*'))
                      if os.path.isdir(d))
    if not run_dirs:
        sys.exit('No run folders found in %s/. Run run_experiment.py first.' % RESULTS_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)

    runs = []                                    # one dict per run
    for d in run_dirs:
        per_student, ok, late, info = load_run(d)
        allv = [x for v in per_student.values() for x in v]
        if not allv:
            print('skipping %s (no latency data)' % d)
            continue
        means = {s: statistics.mean(v) for s, v in per_student.items()}
        runs.append({'scenario': os.path.basename(d).split('_')[0], 'name': os.path.basename(d),
                     'dir': d, 'all': allv, 'means': means, 'info': info,
                     'mean': statistics.mean(allv), 'median': statistics.median(allv),
                     'p95': percentile(allv, 95), 'max': max(allv),
                     'jain': jain(list(means.values())), 'ok': ok, 'late': late})

    with open(os.path.join(OUT_DIR, 'summary_runs.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['run', 'requests', 'mean_ms', 'median_ms', 'p95_ms', 'max_ms',
                    'jain_fairness', 'exams_submitted', 'exams_timeup'])
        for r in runs:
            w.writerow([r['name'], len(r['all']), round(r['mean'], 2),
                        round(r['median'], 2), round(r['p95'], 2), round(r['max'], 2),
                        round(r['jain'], 4), r['ok'], r['late']])

    scen = defaultdict(list)
    for r in runs:
        scen[r['scenario']].append(r)
    order = sorted(scen)

    def avg(key, rs):
        return statistics.mean(r[key] for r in rs)

    def sd(key, rs):
        return statistics.pstdev(r[key] for r in rs) if len(rs) > 1 else 0.0

    print('\n%-24s %5s %9s %9s %9s %9s %8s' % (
        'Scenario', 'runs', 'mean ms', 'median', 'p95', 'max', 'fairness'))
    with open(os.path.join(OUT_DIR, 'summary_scenarios.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['scenario', 'runs', 'mean_ms', 'mean_ms_sd', 'median_ms', 'p95_ms', 'max_ms',
                    'jain_fairness', 'exams_timeup'])
        for s in order:
            rs = scen[s]
            w.writerow([LABEL.get(s, s), len(rs),
                        round(avg('mean', rs), 2), round(sd('mean', rs), 2),
                        round(avg('median', rs), 2), round(avg('p95', rs), 2),
                        round(avg('max', rs), 2), round(avg('jain', rs), 4),
                        sum(r['late'] for r in rs)])
            print('%-24s %5d %9.2f %9.2f %9.2f %9.2f %8.4f' % (
                LABEL.get(s, s), len(rs), avg('mean', rs), avg('median', rs),
                avg('p95', rs), avg('max', rs), avg('jain', rs)))

    # ---- Figure 1: average and 95th percentile response time ----
    fig, ax = plt.subplots(figsize=(7, 4.2))
    xs = range(len(order))
    ax.bar([x - 0.2 for x in xs], [avg('mean', scen[s]) for s in order], 0.4,
           yerr=[sd('mean', scen[s]) for s in order], capsize=4,
           color=[COLOR.get(s, '#888') for s in order], label='mean')
    ax.bar([x + 0.2 for x in xs], [avg('p95', scen[s]) for s in order], 0.4,
           color=[COLOR.get(s, '#888') for s in order], alpha=0.45, label='95th percentile')
    ax.set_xticks(list(xs))
    ax.set_xticklabels([LABEL.get(s, s) for s in order], fontsize=8)
    ax.set_ylabel('Response time (ms)')
    ax.set_title('Exam response time by scenario')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'fig1_response_time.png'), dpi=150)
    plt.close(fig)

    # ---- Figure 2: distribution of all requests ----
    fig, ax = plt.subplots(figsize=(7, 4.2))
    data = [[x for r in scen[s] for x in r['all']] for s in order]
    ax.boxplot(data, showfliers=True)
    ax.set_xticklabels([LABEL.get(s, s) for s in order])
    ax.set_yscale('log')
    ax.set_ylabel('Response time (ms, log scale)')
    ax.set_title('Distribution of response times')
    ax.tick_params(axis='x', labelsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'fig2_distribution.png'), dpi=150)
    plt.close(fig)

    # ---- Figure 3: mean response time of each student ----
    students = sorted({s for r in runs for s in r['means']})
    fig, ax = plt.subplots(figsize=(7, 4.2))
    width = 0.8 / max(1, len(order))
    for i, s in enumerate(order):
        vals = []
        for st in students:
            v = [r['means'][st] for r in scen[s] if st in r['means']]
            vals.append(statistics.mean(v) if v else 0)
        ax.bar([j + i * width for j in range(len(students))], vals, width,
               label=LABEL.get(s, s), color=COLOR.get(s, '#888'))
    ax.set_xticks([j + width * (len(order) - 1) / 2 for j in range(len(students))])
    ax.set_xticklabels(students)
    ax.set_ylabel('Mean response time (ms)')
    ax.set_title('Per-student response time (fairness view)')
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'fig3_per_student.png'), dpi=150)
    plt.close(fig)

    # ---- Figure 4: Jain's fairness index ----
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar([LABEL.get(s, s) for s in order], [avg('jain', scen[s]) for s in order],
           color=[COLOR.get(s, '#888') for s in order])
    ax.set_ylim(0, 1.05)
    ax.axhline(1.0, color='grey', linewidth=0.8, linestyle='--')
    ax.set_ylabel("Jain's fairness index (1.0 = perfectly fair)")
    ax.set_title('Fairness between students')
    ax.tick_params(axis='x', labelsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'fig4_fairness.png'), dpi=150)
    plt.close(fig)

    # ---- Figure 5: traffic on the server port over time (needs controller stats) ----
    fig, ax = plt.subplots(figsize=(7, 4.2))
    drawn = False
    for s in order:
        for r in scen[s]:
            ps = os.path.join(r['dir'], 'port_stats.csv')
            info = r['info']
            if not (os.path.exists(ps) and 'start' in info):
                continue
            t, y = [], []
            with open(ps) as f:
                for row in csv.DictReader(f):
                    ts = float(row['time'])
                    if row['port'] == '1' and info['start'] - 2 <= ts <= info['end'] + 2:
                        t.append(ts - info['start'])
                        y.append(float(row['mbps']))
            if t:
                ax.plot(t, y, label=LABEL.get(s, s), color=COLOR.get(s, '#888'))
                drawn = True
            break
    if drawn:
        ax.set_xlabel('Seconds since students started')
        ax.set_ylabel('Server port traffic (Mbps, both directions)')
        ax.set_title('Traffic on the server-facing switch port')
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, 'fig5_server_port_traffic.png'), dpi=150)
    plt.close(fig)

    print('\nSaved tables and graphs in %s/' % OUT_DIR)


if __name__ == '__main__':
    main()
