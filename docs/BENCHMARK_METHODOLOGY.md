# Orbiqo Lab benchmark methodology

> Scope: digital-only generation, digital raster decode, and deterministic synthetic degradation. No result in this suite measures or predicts print performance.

The primary workload is a deterministic 64-byte binary payload. Each encoder uses its native auto-sizing behavior for timing and degradation runs, after which the output is centered on a 1024×1024 white canvas with nearest-neighbor scaling. Orbiqo runs through the RadialCode COLOR4 reference implementation, QR and Aztec run through ZXing-C++ 3.1.1, and JAB is included only after its official writer and reader complete a deterministic round trip.

| Measurement | Repetitions | Definition |
| --- | ---: | --- |
| Generation time | 10 | Encode plus raster generation; JAB includes CLI process startup |
| Clean decode time | 10 | End-to-end detection and payload recovery on the normalized canvas |
| Degradation success | 4 per profile | Exact byte equality after deterministic blur, noise, JPEG, downsampling, occlusion, and combined profiles |
| Capacity | One deterministic sweep | Orbiqo exact model; QR/Aztec largest binary payload retaining the version-1 raster size |

Raw rows are stored in `benchmark/results/comparison_raw.csv`; the dashboard consumes `benchmark/results/comparison_summary.json`. Environment versions, seeds, payload hash, parameters, and limitations are embedded in the summary.

## Toolchain sources

ZXing-C++ documents QR and Aztec read/write support, Python bindings, and the create/write/read APIs in its official repository.[1] The JAB repository provides the C11 writer/reader used here and identifies ISO/IEC 23634:2022 as its technical specification.[2]

## References

[1]: https://github.com/zxing-cpp/zxing-cpp "ZXing-C++ official repository"
[2]: https://github.com/jabcode/jabcode "JAB Code official repository"
