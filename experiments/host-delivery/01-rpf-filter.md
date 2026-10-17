# 01 — Local reverse-path filtering

## Purpose

Follow a multicast packet from the receiver's ingress interface through Linux
source validation to the application. The controlled change is a host route:
the packet continues to arrive on eth1 while the return lookup for its source is
made to select management eth0.

Start the [shared lab](../../lab/README.md). Keep receiver-a, receiver-b and
publisher-a running continuously. Run the following commands inside
`clab-marketdata-ceos-receiver-a`; replace the management gateway if your
`ip route` output differs.

## Baseline and controlled change

```sh
# Commands
ip route
cat /proc/sys/net/ipv4/conf/all/rp_filter
cat /proc/sys/net/ipv4/conf/eth0/rp_filter
cat /proc/sys/net/ipv4/conf/eth1/rp_filter
sysctl -w net.ipv4.conf.eth1.rp_filter=1
ip route get 172.16.1.2

# Observed baseline and output
# all, eth0 and eth1 rp_filter values: 0
# sysctl: net.ipv4.conf.eth1.rp_filter = 1
# 172.16.1.2 via 172.16.101.1 dev eth1 src 172.16.101.2
```

With strict validation enabled and the source route using eth1, both receivers
continued to report in-order messages. Confirm no existing source /32 route
before injecting the fault:

```sh
# Commands
ip route show exact 172.16.1.2/32
ip route add 172.16.1.2/32 via 172.31.250.1 dev eth0
ip route get 172.16.1.2
tcpdump -pni eth1 -c 5 \
  'udp and src host 172.16.1.2 and dst host 232.10.1.1 and dst port 20001'
nstat -asz TcpExtIPReversePathFilter UdpRcvbufErrors

# Observed output (summary)
# Initial exact /32 query: no route
# 172.16.1.2 via 172.31.250.1 dev eth0 src 172.31.250.3
# tcpdump: 5 packets captured; UDP payload 94 bytes; 0 capture drops
# TcpExtIPReversePathFilter: 50 -> 523; UdpRcvbufErrors: 0 -> 0
```

On Ubuntu1, check that receiver-a stops advancing while receiver-b continues:

```sh
# Commands
tail -n 3 /tmp/e04-receiver-a.log
tail -n 3 /tmp/e04-receiver-b.log

# Observed sequence values
# receiver-a stopped at 2467
# receiver-b advanced 3010 -> 3073 -> 3198
```

Packets remained visible on eth1 while receiver-a stopped advancing, and the
reverse-path filter counter increased. Together these observations locate the
drop at receiver-a's source-validation stage. The counter increase covers only
the sampled interval, not the full application gap.

## Restore and verify

Inside receiver-a, remove only the injected route and restore the saved
`rp_filter` value. The observed original value was 0:

```sh
# Commands
ip route del 172.16.1.2/32 via 172.31.250.1 dev eth0
ip route get 172.16.1.2
sysctl -w net.ipv4.conf.eth1.rp_filter=0
cat /proc/sys/net/ipv4/conf/eth1/rp_filter

# Expected final state
# source route returns to eth1; eth1 rp_filter is operator-confirmed as 0
```

On Ubuntu1, inspect the continuing receiver process:

```sh
# Commands
grep -B 1 '"classification": "gap"' /tmp/e04-receiver-a.log
tail -n 3 /tmp/e04-receiver-a.log

# Observed recovery summary
# Last before interruption: 2467
# First after interruption: 3391, classification=gap
# Missing: 2468-3390, count = 3391 - 2467 - 1 = 923
# Later samples advanced in order through 10167
```

The gap count comes from application sequence values. Receiver-b's gap query
returned no entries. The operator confirmed that the original `rp_filter`
value was restored.
