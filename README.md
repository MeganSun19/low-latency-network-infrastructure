# Low-Latency Network Infrastructure

An engineering project for studying market-data delivery, packet loss,
latency boundaries, host/network diagnostics, failure recovery, and automated
evidence in low-latency trading infrastructure.

## Implemented

- Eight-node Containerlab topology: four cEOS routers, two publishers and two receivers; eBGP and PIM-SSM.
- Python UDP multicast workload with per-stream sequence diagnostics.
- [Host-delivery experiments](experiments/host-delivery/README.md): reverse-path filtering, wrong-interface membership, slow consumers and CPU scheduling contention.

Start with [deployment and topology](lab/README.md), then follow the experiment runbooks.
The case studies retain selected observations from manually executed Linux VM experiments. Fresh-clone deployment and independent reproduction remain to be verified.

## Evidence highlights

- A paused consumer exhausted its UDP receive buffer: **78 missing sequences matched 78 socket drops and receive-buffer errors**.
- An in-order buffered message had a **15.63 s application timestamp delta**, exposing stale delivery before the sequence gap.
- A same-vCPU contention trial compared baseline, loaded and recovery scheduling-wait distributions.

These are software fault-localization results. The VM/veth/cEOS setup measures neither physical switch latency nor hardware NIC/PTP performance. Each case states its measurement boundary and limitations.

## Local checks

```sh
python3 -m py_compile workloads/marketdata.py
```

Supply your own authorized cEOS image. Vendor images, credentials and generated lab state are excluded from this repository. Run fault injections only in a disposable lab.
