# Orbiqo Lab — Digital Benchmark Gate Report

**Owner:** Orbiqo Project  
**Scope:** Local, digital-only engineering gate  
**Reference format:** RadialCode Design Draft 0.3, with Draft 0.2 compatibility records

> This gate does not measure or predict printed-symbol performance. It covers digital generation, digital raster decoding, deterministic synthetic degradation, adversarial inputs, and synthetic perspective scenes.

The local Orbiqo Lab now connects its Node.js and tRPC layer to the real Python COLOR4 reference implementation. The generator supports text, URL, and binary inputs; geometry, diameter, ECC, and center-mark controls; and SVG/PNG export. The reader supports image upload, explicit camera permission, explicit screen-capture permission, manual or periodic capture, and separate permission, detection, decode-failure, decoded-content, and diagnostic states.

## Gate status

| Area | Result | Gate interpretation |
| --- | ---: | --- |
| Python reference suite | 113 passed, 2 strict expected failures | Core, vectors, vision, simulation, CLI, and adversarial tests pass; extreme foreshortening remains explicit |
| Web/server suite | 10/10 passed | Real bridge, validation, benchmark artifact, and adversarial paths pass |
| TypeScript | Passed | No type errors |
| Production build | Passed | Vite client and bundled Express server completed |
| Runtime logs | Clean | No browser, network, or development-server errors in the reviewed workspaces |
| Visual review | Completed | Create, Read, and Benchmarks reviewed on desktop and mobile |
| Git state | Uncommitted | Only the initial scaffold commit exists; all project work remains local |

## Comparative results

The timing workload uses the same deterministic 64-byte binary payload and ten repetitions per operation. QR and Aztec use ZXing-C++ 3.1.1, whose official repository documents Python bindings and read/write support for both formats.[1] JAB uses the official C11 writer and reader after they compiled on the current Ubuntu environment and passed a deterministic round trip; the writer and reader are part of the official JAB repository.[2]

| Format | Median generation | Median decode | Timing qualification |
| --- | ---: | ---: | --- |
| Orbiqo | 247.90 ms | 107.17 ms | Python reference path, including COLOR4 rendering and full visual detection |
| QR | 0.78 ms | 4.53 ms | Optimized native ZXing-C++ path |
| Aztec | 0.47 ms | 5.07 ms | Optimized native ZXing-C++ path |
| JAB | 8.11 ms | 138.27 ms | Official CLI path; includes process startup |

These numbers show that the current Orbiqo reference implementation prioritizes inspectability and correctness over throughput. They are not evidence that the format itself requires these runtimes; the implementations and invocation models differ.

## Fixed-profile capacity

| Format | Fixed profile | Maximum binary payload |
| --- | --- | ---: |
| Orbiqo | Small, COLOR4, Balanced | 183 bytes |
| QR | Version-1 raster size, ZXing default ECC | 15 bytes |
| Aztec | Version-1 raster size, ZXing default ECC | 3 bytes |
| JAB | One 1×1 symbol, COLOR4, ECC level 3 | 43 bytes |

This is a descriptive profile table, not a density ranking. Geometry, physical pitch, finder overhead, and ECC strength are not normalized across the four formats.

## Digital degradation and perspective

Across 128 format/profile/trial combinations, **111 decoded to exact byte equality (87%)**. All formats passed clean, blur, noise, JPEG, and downsampling cases in this matrix. All four formats failed the synthetic 6% occlusion placement used by the common corpus, and Orbiqo passed three of four combined-degradation trials. This result indicates that the common occlusion case is too coarse to differentiate ECC behavior reliably and should not be interpreted as a universal 6% damage threshold.

The separate Orbiqo perspective matrix remains **14/16**. The two failures are the clean and camera-like variants of the same extreme foreshortened pose. Diagnostic work localized the failure to selection of incorrect clear components around the guard; the resulting homography is numerically valid for the wrong four points, causing all BCH header copies to be sampled incorrectly. The two cases are now strict expected-failure regressions, so an unexpected pass or behavior change becomes visible to the suite.

## Adversarial coverage

The deterministic corpus validates 1,000 seeded header words, every single-byte mutation of a valid frame, 257 arbitrary frame lengths, blank and black images, a checkerboard, concentric rings, eight seeded RGB noise fields, malformed Base64, non-image byte streams, the 64 KiB payload boundary, and the 12 MiB bridge-request boundary. The corpus requires controlled rejection and treats any false decoded payload as a failure.

## Decision requested

The digital benchmark gate is ready for owner review. Approval should distinguish two decisions: whether the current transparent alpha results are sufficient to create the first authored commit, and whether the unresolved extreme-foreshortening correction must block that commit or may remain an explicitly documented alpha limitation.

## Artifacts

| Artifact | Path |
| --- | --- |
| Raw benchmark rows | `benchmark/results/comparison_raw.csv` |
| Machine-readable summary | `benchmark/results/comparison_summary.json` |
| Reproducible benchmark runner | `benchmark/run_comparison.py` |
| Methodology | `docs/BENCHMARK_METHODOLOGY.md` |
| Adversarial methodology | `docs/ADVERSARIAL_TESTING.md` |
| Foreshortening analysis | `/home/ubuntu/radialcode/docs/FORESHORTENING_ANALYSIS.md` |

## References

[1]: https://github.com/zxing-cpp/zxing-cpp "ZXing-C++ official repository"
[2]: https://github.com/jabcode/jabcode "JAB Code official repository"
