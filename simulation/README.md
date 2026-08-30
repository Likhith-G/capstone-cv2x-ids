# NS-3 simulation module

`cv2xids` is an ns-3 contrib module that generates the C-V2X sidelink traces
this project's detection work is built on. Copy it into an ns-3 tree at
`contrib/cv2xids` and build.

## What it does

Vehicles exchange real ETSI ITS messages over an NR V2X Mode 2 sidelink, some
of them misbehaving, and every receiver logs only what a receiver could
actually observe. The transmitter logs ground truth separately and the two are
joined offline on a message uid, so no label can reach the feature set through
the air interface.

| file | responsibility |
|---|---|
| `model/its-message-header.*` | the ITS message on the wire. Carries only what a real receiver could observe |
| `model/its-station-app.*` | CAM, DENM, CPM and VAM generation to EN 302 637-2/3, TS 103 324 and TS 103 300-3, TS 102 687 reactive DCC gating, and the attack behaviours |
| `model/highway-traffic-model.*` | Intelligent Driver Model car following with three vehicle classes |
| `model/sl-channel-monitor.*` | per-node channel busy ratio and per-transmitter RSRP, neither of which 5G-LENA provides |
| `model/cv2x-trace-store.*` | buffered CSV tables, flushed every second |
| `helper/cv2x-ids-helper.*` | trace wiring and the station register |
| `examples/cv2x-ids-scenario.cc` | the scenario |

## Requirements

ns-3.42 with 5G-LENA `nr` at tag `v2x-1.1`, plus one additive three-file patch
to `contrib/nr`, saved at `docs/patches/nr-sl-rsrp-trace.patch`:

    git -C contrib/nr apply /path/to/docs/patches/nr-sl-rsrp-trace.patch

The patch exposes the per-SCI sidelink RSRP that 5G-LENA computes internally
and never surfaces. Without it the strongest cross-layer feature does not
exist. Make no other change to `contrib/nr`.

**Build with Python 3.12.** The ns3 wrapper does not work under 3.14.

    PY=/opt/homebrew/opt/python@3.12/bin/python3.12
    $PY ./ns3 configure --enable-examples -d optimized --disable-werror
    $PY ./ns3 build

## Running

    ./build/contrib/cv2xids/examples/ns3.42-cv2x-ids-scenario-optimized \
        --numLanesPerDirection=3 --vehiclesPerLane=15 --roadLength=6000 \
        --numRsu=12 --simTime=60s --rngRun=1 --attackerFraction=0.30 \
        --attackMix=1,3,4,5,6,7,8,11,12 \
        --outputDir=OUT --simTag=seed1

`--PrintHelp` lists every option.

Run one simulation at a time on a machine with 8 GB. Six in parallel exhausts
memory and the runs are killed partway, which leaves every table truncated at a
different point.

## Two configurations that are not interchangeable

A short road with no roadside units is fine for a centralised benchmark, but
every observer hears every vehicle, so all federated clients see the same class
mixture and an aggregation comparison on it is meaningless. Anything federated
needs the long road with roadside units. Check the partition before trusting a
federated result.

## Constraints worth knowing before extending it

- **Mode 2 grants in 5G-LENA are data driven.** A reserved resource is used
  only when there is data for it, so an attacker cannot hoard the channel and
  resource-exhaustion style attacks have no effect. This is a property of the
  simulator, not of C-V2X.
- **`resoReselCounter` and `cReselCounter` are always 255.** The code that
  would set them sits inside `#ifdef NOTYET` upstream.
- **Reservation periods** must be a multiple of the physical sidelink pool
  length and must exceed the selection window. Both are asserted with an
  explanatory abort.
- Sidelink transmits only in uplink slots permitted by the pool bitmap, which
  is 45 percent of slots in the default configuration. Channel occupancy must
  be normalised against those slots and not against all of them.
