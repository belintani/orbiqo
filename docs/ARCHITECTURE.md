# Orbiqo Lab — Local Architecture

Orbiqo is the local product and demonstration identity. The encoding format remains the RadialCode Design Draft lineage, and the repository retains the Draft 0.2 and Draft 0.3 specifications, Apache-2.0 license, notice, attribution policy, and citation metadata.

| Layer | Responsibility | Trust boundary |
| --- | --- | --- |
| React client | Collect generator inputs, request explicit camera or screen permission, resize captured frames, display symbols and diagnostics, and export returned artifacts | Never claims a decode before the backend confirms payload integrity |
| tRPC contracts | Validate payload type, geometry, diameter, ECC, file size, image MIME type, and request timeouts | Rejects malformed or oversized requests before invoking Python |
| Node bridge | Starts one bounded Python process per operation, passes one JSON document over stdin, captures stdout/stderr, and enforces timeout and output limits | Does not implement encoding or decoding logic |
| Python bridge | Converts validated JSON to the public RadialCode reference API and serializes results and diagnostics back to JSON | Imports the reference package from the local sibling project; no mock fallback exists |
| RadialCode reference | Performs framing, BCH, Reed–Solomon, interleaving, COLOR4 mapping, rendering, detection, homography, calibration, and decode | Source of truth for symbols and benchmark behavior |

## Local integration contract

The backend invokes `python3 server/python/orbiqo_bridge.py` with `PYTHONPATH` pointing to `/home/ubuntu/radialcode/src` by default. The path can be overridden with `ORBIQO_RADIALCODE_ROOT`. Requests and responses use JSON over standard input and output so payloads do not appear in shell arguments. Each call is bounded by a timeout, maximum input size, maximum decoded dimensions, and maximum child-process output size.

The bridge exposes four operations. `generate` returns a real SVG, PNG, header metadata, capacity information, and renderer attribution. `decode` accepts PNG or JPEG bytes and returns payload, header, confidence, ECC corrections, erasures, color references, and optional homography diagnostics. `capacity` reports exact reference capacities. `health` reports the imported package version and supported Draft versions.

## Reader states

The client state machine is explicit: `idle → requesting-permission → stream-ready → capturing → detecting → decoded` or `decode-failed`. Permission denial, absent devices, unsupported screen capture, oversized frames, detection failure, invalid header, integrity failure, and timeout remain distinguishable. Stopping or leaving the reader always stops every media track.

## Benchmark gate

All benchmark inputs, deterministic seeds, library versions, environment details, raw rows, and aggregation rules are published locally. Claims are limited to digital generation, digital capture, and synthetic degradations. No result is presented as evidence of print performance. GitHub creation, commits, and pushes remain blocked until the benchmark gate is reviewed by the project owner.
