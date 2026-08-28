# Orbiqo optimization profile

**Scope:** Local digital reference path; no format or printing claim

The first normalized gate reported 571 bytes because its capacity search assumed clean-decode success was monotonic with payload length. The boundary probe disproved that assumption: 572 bytes failed while 573, 650, 700, 750, and 762 bytes decoded. XL showed the same pattern; 800 bytes failed while 900, 1,000, and 1,100 bytes decoded. Capacity search now separates the monotonic generation/pitch ceiling from content-dependent decode and walks downward from that ceiling.

## Measured hotspots

| Stage | Small / 64 B | Large / 571 B | Interpretation |
| --- | ---: | ---: | --- |
| Framing | 0.02 ms | 0.10 ms | Negligible |
| Geometry construction | 2.39 ms | 10.83 ms | Cacheable by version |
| Reed–Solomon encoding | 1.56 ms | 6.31 ms | Secondary cost |
| Interleaving | 0.02 ms | 0.09 ms | Negligible |
| COLOR4 channel + eight masks | 22.58 ms | 101.19 ms | Main encoder hotspot |
| Full encode | 31.51 ms | 145.07 ms | Dominated by masks and geometry |
| SVG creation | 5.13 ms | 17.58 ms | Acceptable for vector export |
| PNG through CairoSVG | 225.43 ms | 745.98 ms | Dominant generation hotspot |
| Vision decode | 125.99 ms | 343.12 ms | Dominated by per-cell sampling and COLOR4 classification |

The function profile shows CairoSVG parsing and drawing more than one thousand independent SVG paths as the primary PNG cost. Decode spends most time in `_color_payload_samples`, then in one NumPy-heavy `ColorModel.classify` call per cell. The masking stage rebuilds the same geometry-dependent address, neighbor, and mask layout for every payload.

## Capacity ceiling

| Geometry | Nominal capacity | Normalized pitch |
| --- | ---: | ---: |
| Small | 183 B | 18.93 px |
| Medium | 410 B | 12.62 px |
| Large | 762 B | 9.46 px |
| XL | 1,252 B | 7.57 px |

All four geometries remain above the seven-pixel floor. The previous 571-byte result was therefore an implementation and methodology ceiling, not the format ceiling.

## Pose correction experiment

The fast connected-component hypothesis occasionally selected plausible but slightly misplaced guard notches. Applying a full projective transform amplified those small errors across dense Large/XL payload rings. The decoder now tries a full-affine hypothesis after projective failure. The boundary probe moved Large from intermittent failures to clean success through 762 bytes and recovered multiple XL payloads through 1,250 bytes. XL remains content-dependent at a few lengths, so the result is not yet treated as a frozen guarantee.

## Next optimizations

The highest-return compatible work is direct raster rendering for PNG, cached geometry/mask layouts for encoding, batched sampling/classification for decode, and a deterministic clean-image affine path before considering any Draft 0.4 capacity change. Visual variants will be benchmarked as renderer profiles rather than assumed to be harmless.

The masking and geometry optimizations preserve the normative encoded bytes, selected mask, and `cell_states`; dedicated tests compare the optimized path against the original scoring implementation. The Pillow PNG path is **decode-equivalent rather than file-byte-identical** to CairoSVG. SVG remains the normative vector export, while the fast PNG is an interactive raster artifact with its own explicit round-trip tests.

The canonical decoder was benchmarked separately on valid canonical PNG inputs. Small remains intentionally on the scalar sampler and was effectively unchanged at 65.97 ms versus 65.41 ms. Large fell from 280.65 ms to 99.66 ms (**2.82× faster**) and XL from 472.47 ms to 162.22 ms (**2.91× faster**), with exact payload equality in every measured run. The general image path also added a guarded frontal fast path; its latest profile measured 94.96 ms for Small, 160.60 ms for Large, and 203–207 ms for the tested XL payloads.
