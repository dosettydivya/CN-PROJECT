# Online Examination Network (Problem 18, Group 13)

A multi-user online exam over TCP, running on a software-defined network (SDN).
Students connect to an exam server through TCP sockets; an SDN controller monitors
and manages the exam traffic; the system is tested under congestion.

| Member | Part | Files |
|---|---|---|
| Diya G S | SDN network, controller, QoS | `topo.py`, `exam_controller.py`, `setup_qos.sh`, `reset_qos.sh` |
| Emmidi Sreeshanth | Exam application | `server.py`, `client.py` |
| Dosetty Divya Shree Dutta | Experiments, analysis, report | `run_experiment.py`, `analyze.py`, `README.md` |

Each member has a PDF work guide in the `guides/` folder.

## Architecture
```
            Ryu controller (exam_controller.py)  127.0.0.1:6653
                         | OpenFlow 1.3
     server --- s1-eth1 [ OVS switch s1 ] --- h1..h5 (students), n1, n2 (noise)
   10.0.0.100  (10 Mbps bottleneck)
```
Exam traffic = TCP port **5000** (the controller prioritises it). Noise = iperf on port 5001.

## Requirements (Ubuntu, in a VM with 30 GB+ disk)
- Mininet, Open vSwitch, iperf, xterm: `sudo apt install -y mininet openvswitch-switch iperf xterm`
- Ryu in a Python 3.9 environment (`~/ryu-env`, see Diya's guide)
- matplotlib for the analysis: `sudo apt install -y python3-matplotlib`

## Quick start (manual demo)
```
# Terminal 1 - controller (with the Ryu environment)
source ~/ryu-env/bin/activate
cd ~/exam_project
QOS=1 ryu-manager exam_controller.py        # leave out QOS=1 for the baseline

# Terminal 2 - network (no virtual environment)
cd ~/exam_project
sudo mn -c
sudo python3 topo.py
mininet> sh bash setup_qos.sh
mininet> pingall
mininet> server python3 server.py > server.log 2>&1 &
mininet> xterm h1 h2 h3            # then in each: python3 client.py 10.0.0.100 <name>
```

## Run the experiments (automatic)
Controller in baseline mode (no `QOS=1`):
```
for r in 1 2 3; do sudo python3 run_experiment.py A --run $r; done
for r in 1 2 3; do sudo python3 run_experiment.py B --run $r; done
```
Stop the controller, restart it with `QOS=1`, then:
```
for r in 1 2 3; do sudo python3 run_experiment.py C --run $r; done
python3 analyze.py
```
Results are stored in `results/<scenario>_run<N>/`, tables and graphs in `analysis_output/`.

| Scenario | Controller | Traffic |
|---|---|---|
| A | QoS off | exam only |
| B | QoS off | exam + iperf noise |
| C | `QOS=1` | exam + iperf noise |

## Output files
- `results.csv` - one line per finished exam (score, time used, submitted or timeup)
- `latency_<student>.csv` - round-trip time of every request
- `port_stats.csv` - traffic per switch port, written by the controller every 2 s
- `analysis_output/*.png`, `summary_*.csv` - graphs and tables for the report

## Rules shared by everyone
- Server address `10.0.0.100`, exam port `5000` - do not change.
- Always start the controller before the network.
- Run `sudo mn -c` if Mininet behaves strangely.
