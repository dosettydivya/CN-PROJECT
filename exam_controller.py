"""exam_controller.py - Ryu SDN controller for the Online Examination project.
(docstring unchanged)
"""
import os
import time
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, tcp
from ryu.ofproto import ofproto_v1_3

EXAM_PORT = 5000                 # TCP port used by the exam application
SERVER_IP = '10.0.0.100'         # the exam server
QOS_ENABLED = os.environ.get('QOS', '0') == '1'
Q_EXAM, Q_OTHER = 1, 2           # queue ids created by setup_qos.sh
POLL_INTERVAL = 2                # seconds between statistics requests
CSV_FILE = 'port_stats.csv'


class ExamController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ExamController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.prev_bytes = {}
        with open(CSV_FILE, 'w') as f:
            f.write('time,dpid,port,rx_bytes,tx_bytes,mbps\n')
        self.monitor_thread = hub.spawn(self._monitor)
        self.logger.info('QoS mode: %s', 'ON' if QOS_ENABLED else 'OFF')

    # ---------- helpers ----------
    def add_flow(self, dp, priority, match, actions, idle=0):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority,
                                      match=match, instructions=inst,
                                      idle_timeout=idle))

    # ---------- switch connects ----------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        self.datapaths[dp.id] = dp
        to_ctrl = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                          ofp.OFPCML_NO_BUFFER)]
        # priority 0: anything unknown -> controller
        self.add_flow(dp, 0, parser.OFPMatch(), to_ctrl)
        # priority 20: every new TCP packet -> controller (so we can classify)
        self.add_flow(dp, 20,
                      parser.OFPMatch(eth_type=0x0800, ip_proto=6), to_ctrl)
        self.logger.info('Switch s%s connected', dp.id)

    # ---------- packet arrives at controller ----------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        self.mac_to_port.setdefault(dp.id, {})
        self.mac_to_port[dp.id][eth.src] = in_port          # learn source
        out_port = self.mac_to_port[dp.id].get(eth.dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        ip = pkt.get_protocol(ipv4.ipv4)
        t = pkt.get_protocol(tcp.tcp)

        if out_port != ofp.OFPP_FLOOD:
            if ip and t:
                is_exam = EXAM_PORT in (t.src_port, t.dst_port)
                if QOS_ENABLED and ip.dst == SERVER_IP:
                    q = Q_EXAM if is_exam else Q_OTHER
                    actions = [parser.OFPActionSetQueue(q),
                               parser.OFPActionOutput(out_port)]
                match = parser.OFPMatch(
                    in_port=in_port, eth_type=0x0800, ip_proto=6,
                    ipv4_src=ip.src, ipv4_dst=ip.dst,
                    tcp_src=t.src_port, tcp_dst=t.dst_port)
                self.add_flow(dp, 100 if is_exam else 50, match, actions,
                              idle=30)
            else:
                # ARP, ICMP, etc. -> simple MAC based rule
                match = parser.OFPMatch(in_port=in_port, eth_dst=eth.dst,
                                        eth_src=eth.src)
                self.add_flow(dp, 1, match, actions, idle=30)

        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                        in_port=in_port, actions=actions,
                                        data=data))
            # ---------- monitoring ----------
    def _monitor(self):
        while True:
            for dp in list(self.datapaths.values()):
                parser = dp.ofproto_parser
                dp.send_msg(parser.OFPPortStatsRequest(
                    dp, 0, dp.ofproto.OFPP_ANY))
                dp.send_msg(parser.OFPFlowStatsRequest(dp))
            hub.sleep(POLL_INTERVAL)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_handler(self, ev):
        dpid = ev.msg.datapath.id
        self.logger.info('--- PORT STATS s%s ---', dpid)
        self.logger.info('port\trx_bytes\ttx_bytes\tMbps')
        now = time.time()
        with open(CSV_FILE, 'a') as f:
            for st in sorted(ev.msg.body, key=lambda s: s.port_no):
                if st.port_no > 0xffffff00:      # skip the LOCAL port
                    continue
                total = st.rx_bytes + st.tx_bytes
                prev = self.prev_bytes.get((dpid, st.port_no), total)
                mbps = (total - prev) * 8.0 / POLL_INTERVAL / 1e6
                self.prev_bytes[(dpid, st.port_no)] = total
                self.logger.info('%4s %10d %10d %7.2f', st.port_no,
                                 st.rx_bytes, st.tx_bytes, mbps)
                f.write('%.2f,%s,%s,%d,%d,%.3f\n' % (now, dpid, st.port_no, st.rx_bytes, st.tx_bytes, mbps))

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_handler(self, ev):
        dpid = ev.msg.datapath.id
        self.logger.info('--- FLOW STATS s%s ---', dpid)
        # only the per-connection rules (priority 50 = other, 100 = exam)
        for st in sorted(ev.msg.body, key=lambda s: -s.priority):
            if st.priority < 50:
                continue
            m = st.match
            self.logger.info('prio=%-3d %s:%s -> %s:%s  pkts=%d bytes=%d',
                             st.priority,
                             m.get('ipv4_src'), m.get('tcp_src'),
                             m.get('ipv4_dst'), m.get('tcp_dst'),
                             st.packet_count, st.byte_count)

            f.write('%.1f,%s,%s,%d,%d,%.3f\n' % (now, dpid, st.port_no, st.rx_bytes, st.tx_bytes, mbps))

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_handler(self, ev):
        dpid = ev.msg.datapath.id
        for st in ev.msg.body:
            if st.priority >= 50:                # only per-connection flows
                m = st.match
                self.logger.info('flow s%s %s:%s -> %s:%s pkts=%d bytes=%d',
                                 dpid, m.get('ipv4_src'), m.get('tcp_src'),
                                 m.get('ipv4_dst'), m.get('tcp_dst'),
                                 st.packet_count, st.byte_count)
