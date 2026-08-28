# Orbiqo normalized digital benchmark methodology

**Owner:** Orbiqo Project  
**Scope:** Digital-only comparison; no printing claims

> The normalized gate compares implementations on one digital canvas and one occupied bounding box. It does not claim that different ECC families, finder structures, or color channels become equivalent merely because their outer dimensions match.

## Controlled workload

All adapters encode the same deterministic 64-byte binary payload. Every generated symbol is converted to RGB, scaled with nearest-neighbor sampling into a 900×900-pixel occupied square, and centered on a 1024×1024 white canvas. Generation timing includes encoding, native raster creation, normalization, and canvas placement. Decode timing starts from that same normalized canvas and ends after exact payload recovery or controlled failure.

Orbiqo capacity discovery uses the Draft 0.3 normative SVG/Cairo raster so a presentation renderer cannot cap the format. Orbiqo latency and degradation use the direct Pillow PNG renderer shipped in the laboratory. This split is explicit in the summary artifact: capacity characterizes the format/reference renderer, while timing and synthetic robustness characterize the current product path.

| Controlled variable | Value | Reason |
| --- | ---: | --- |
| Canvas | 1024×1024 px | Same decoder input dimensions |
| Occupied bounding box | 900×900 px | Same maximum visual footprint and quiet exterior |
| Timing payload | 64 deterministic bytes | Identical content and hash across formats |
| Timing repetitions | 10 | Median, mean, and p95 reporting |
| Degradation trials | 4 per profile | Fixed seeds and exact-byte success criterion |
| Capacity floor | 7 nominal pixels per smallest logical feature | Prevents capacity from increasing solely by making cells arbitrarily small |

## Capacity under equal digital area

Capacity is the largest deterministic binary payload that satisfies all three conditions: the adapter generates successfully, the normalized symbol retains at least seven nominal pixels per smallest logical feature, and the normalized clean image decodes to exact byte equality. The search is bounded, deterministic, and uses exponential discovery followed by binary search.

For QR, Aztec, and JAB, nominal feature pitch is the 900-pixel occupied width divided by the logical raster width at one pixel per module. For Orbiqo, nominal feature pitch is the radial pitch of the selected geometry projected into the 900-pixel occupied image. Because Orbiqo cells have intentional radial and angular gutters, the reported nominal pitch is not the same as painted stroke width; both the rule and this limitation are published.

The summary reports maximum payload bytes, nominal pitch, logical dimensions or geometry version, and bytes per 100,000 occupied pixels. Since the occupied area is fixed, the last metric makes the normalization explicit rather than implying physical print density.

## ECC profiles

ECC families are not fully normalizable. The primary suite therefore fixes one documented profile per implementation and forbids an overall “winner” claim based only on capacity.

| Format | Profile used | Published interpretation |
| --- | --- | --- |
| Orbiqo | Balanced, RS(255,191) shortened blocks | Code rate 74.9%; 64 parity bytes per full block |
| QR | Q through ZXing-C++ | QR Q is conventionally described as approximately 25% restoration capability.[1] |
| Aztec | ZXing-C++ writer profile | The generated 64-byte artifact reports 33%; this reported value is stored per run |
| JAB | Official CLI default level 3 | The official CLI describes level 3 as 6%; process startup remains included in timing.[2] |

The suite does not transform these values into a common damage percentage. Reed–Solomon, Aztec ECC, and JAB LDPC operate over different structures, and color classification errors do not map directly to monochrome module damage.

## Identical digital degradations

Blur radius, Gaussian noise, JPEG quality, downsampling factor, exposure/saturation changes, and deterministic occlusion are applied after every symbol has the same 900×900 occupied area on the same canvas. Success requires exact equality with the original 64-byte payload. Results remain a synthetic software baseline rather than a camera-device or print benchmark.

## Interpretation rules

Timing compares the current implementations, not theoretical format limits. ZXing-C++ runs as optimized native code, Orbiqo runs through its inspectable Python reference path, and JAB uses command-line processes. Capacity under the feature-pitch floor is more comparable than the previous version-1 profile table, but finder overhead, cell shape, color alphabet, and ECC strength still differ and remain visible in the report.

## References

[1]: https://www.qrcode.com/en/about/error_correction.html "DENSO WAVE — Error correction feature"
[2]: https://github.com/jabcode/jabcode "JAB Code official repository"
