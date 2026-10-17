# Routed multicast environment

## Environment used

I used an Ubuntu 24.04 VM, Linux 6.8.0-110-generic, 12 vCPUs,
one NUMA node, approximately 16 GiB RAM; Containerlab 0.76.0 and cEOS 4.36.2F.
The host had Docker, Containerlab, Python 3, iproute2, tcpdump,
util-linux (`nsenter`, `taskset`) and, for scheduling analysis, BCC's
`runqlat-bpfcc` and sysstat's `mpstat`. Run host commands as root in the lab.

Import an authorized cEOS image and tag it `ceos:4.36.2F`, or deliberately
change the image reference to a compatible version and record the change.
The Linux endpoint image is pinned by digest in the topology.

From the repository root, I deployed and inspected the topology with:

```sh
containerlab deploy --topo lab/ceos.clab.yml
containerlab inspect --topo lab/ceos.clab.yml
```

The topology and startup files are the ones used in my running lab. Avoid
`--reconfigure` if an existing lab's state must be retained.

## Physical links and addressing

Each spine connects to both leaves. Both receivers subscribe to Feed A during
the host-delivery experiments. Publisher B is available for separate feed-path
experiments; Feed A/B arbitration is outside this workload.

| Endpoint | Address | Peer | Address |
| --- | --- | --- | --- |
| spine1 Ethernet1 | 10.0.0.0/31 | leaf1 Ethernet1 | 10.0.0.1/31 |
| spine1 Ethernet2 | 10.0.0.2/31 | leaf2 Ethernet1 | 10.0.0.3/31 |
| spine2 Ethernet1 | 10.0.0.4/31 | leaf1 Ethernet2 | 10.0.0.5/31 |
| spine2 Ethernet2 | 10.0.0.6/31 | leaf2 Ethernet2 | 10.0.0.7/31 |
| spine1 Ethernet3 | 172.16.1.1/30 | publisher-a eth1 | 172.16.1.2/30 |
| spine2 Ethernet3 | 172.16.2.1/30 | publisher-b eth1 | 172.16.2.2/30 |
| leaf1 Ethernet4 | 172.16.101.1/30 | receiver-a eth1 | 172.16.101.2/30 |
| leaf2 Ethernet4 | 172.16.102.1/30 | receiver-b eth1 | 172.16.102.2/30 |

Loopbacks: spine1/2 = 10.255.0.1/2; leaf1/2 = 10.255.0.11/12, all /32.
ASNs: spine1 65101, spine2 65102, leaf1 65201, leaf2 65202.
SSM uses 232.0.0.0/8. Management uses 172.31.250.0/24; endpoint management
addresses are assigned at deployment and must be discovered rather than assumed.

## Start the diagnostic workload

Use four terminals: receiver A, receiver B, publisher A, and diagnostics.
First query the container-init PIDs:

```sh
docker inspect --format '{{.State.Pid}}' clab-marketdata-ceos-receiver-a
docker inspect --format '{{.State.Pid}}' clab-marketdata-ceos-receiver-b
docker inspect --format '{{.State.Pid}}' clab-marketdata-ceos-publisher-a
```

Replace each uppercase PID placeholder below with its current numeric value.
`nsenter --net` uses the host Python and repository files inside the selected
network namespace; the Python process remains visible in the host PID namespace.
Start both receivers before the publisher. Use new log names on repeated runs.

Receiver A:

```sh
nsenter --target RECEIVER_A_CONTAINER_PID --net python3 -u workloads/marketdata.py receive \
  --interface 172.16.101.2 --port 20001 \
  --subscription 1,172.16.1.2,232.10.1.1 --duration 7200 \
  | tee /tmp/e04-receiver-a.log
```

Receiver B:

```sh
nsenter --target RECEIVER_B_CONTAINER_PID --net python3 -u workloads/marketdata.py receive \
  --interface 172.16.102.2 --port 20001 \
  --subscription 1,172.16.1.2,232.10.1.1 --duration 7200 \
  | tee /tmp/e04-receiver-b.log
```

Publisher A:

```sh
nsenter --target PUBLISHER_A_CONTAINER_PID --net python3 -u workloads/marketdata.py publish \
  --source 172.16.1.2 --group 232.10.1.1 --port 20001 \
  --feed-id 1 --channel-id 1 --count 36000 --pps 5 \
  --start-sequence 1 --payload-bytes 64 --ttl 32
```

The custom 30-byte header plus 64-byte payload produces 94-byte UDP payloads.
One datagram carries one sequence. The publisher prints a summary on completion.
Keep the publisher and control receiver continuous within an experiment.
Check that their two-hour lifetimes have not expired.

Baseline diagnostics:

```sh
docker exec -it clab-marketdata-ceos-receiver-a sh
ip addr show eth1
ip route get 172.16.1.2
ip maddr show dev eth1
ss -uanm
nstat -asz UdpInDatagrams UdpInErrors UdpRcvbufErrors
exit
tail -n 3 /tmp/e04-receiver-a.log
tail -n 3 /tmp/e04-receiver-b.log
```

Expect membership on eth1, a source route through eth1 and advancing sequences
at both receivers. Record initial counters and rp_filter values before injection.

## Workload semantics

`marketdata.py` is a low-rate diagnostic workload. The receiver tracks the
highest sequence per `(feed_id, channel_id)`: a forward jump reports a gap;
the same highest sequence reports duplicate; a lower value reports reordered.
Missing counts describe observed forward jumps. Sequence state resets on
receiver restart. The workload reports delivery order; it does not implement
retransmission, replay, order-book building, epoch handling or A/B merging.
Feed IDs are diagnostic labels, not authentication.

`send_ns` is sampled during encoding before `sendto`; `arrival_ns` after
`recvfrom`. Both use `time.time_ns()` on the same VM. Their difference includes
application, scheduling, network and buffering effects, and can be affected by
wall-clock adjustments. Per-packet JSON output adds overhead. I used these
values to inspect delivery and host delay, not as wire-latency measurements.

## Cleanup

First restore each injection as directed in its case study. Stop the workload
processes using Ctrl-C in their own terminals. When the lab is no longer needed:

```sh
containerlab destroy --topo lab/ceos.clab.yml
```

This stops/removes the lab containers and links. Preserve required results first;
avoid `--cleanup` when generated lab files are still needed.
