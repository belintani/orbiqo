# Native Renderer Evaluation

## Decision

**A C++17 raster-core prototype exists as an explicit, opt-in experiment; it is not the default renderer.** RadialCode remains the Python reference implementation and the source of truth for encoding, geometry, colors, headers, error protection and decoding.

The current normalized external figure of 170.6 ms for Orbiqo is **full PNG-ready raster production**, not the core encoder. In the internal profile study, the same 64-byte Balanced payload spends a median 8.34 ms in framing, protection coding and placement. The rest of the external timing includes direct Pillow drawing, 2x supersampling, Lanczos downsampling, PNG serialization and normalization to the 1024 px comparison canvas.

The dedicated stage profile, run on the vendored 0.1.0a6 reference with the same 64-byte Balanced payload, 725 DPI and 2x supersampling, found these median sequential costs: 8.88 ms for the encoder core, **152.29 ms for the direct PNG renderer**, 13.48 ms to open/convert the PNG and 3.03 ms to normalize its canvas. Its 177.80 ms sequential total corroborates the normalized benchmark while showing that the renderer is the main target for any optimization. The measurements are machine-specific and are not a device guarantee.

## Prototype contract and measured result

The prototype uses a versioned, line-oriented `ORBIQO_RASTER_V1` draw list. Python first encodes a complete symbol, then serializes the geometry, cell states, registered palette, guard, clock/header arcs and center boundary to a short-lived C++ command-line process. The native program rasterizes through libpng and returns a PNG. It does not implement framing, error protection, masks or decoding.

Its supported scope is deliberately narrow: an **empty reserved center**, standard registered identity fills and the Draft 0.6 raster core. If an operator requests `native-experimental` with center text or a central remote image, the bridge falls back explicitly to `python-reference-fallback`; it never substitutes a different image silently. SVG always remains the Python reference output.

On the same 67-byte Balanced fixture, 600 DPI, ten runs and with C++ process launch included, the result was:

| Geometry | Python reference median | C++ prototype median | Change | Exact canonical decode |
|---|---:|---:|---:|---|
| Micro 4, 18 mm | 71.57 ms | 68.62 ms | −4.13% | Yes |
| Small, 30 mm | 152.67 ms | 73.06 ms | −52.15% | Yes |
| Medium, 42 mm | 302.46 ms | 142.11 ms | −53.02% | Yes |

The result is machine-specific and covers PNG-ready raster production only. It does not claim a device guarantee or a replacement of the Python encoder. An additional exact-decode validation passed for all seven current Draft 0.6 geometries: Micro 1, Micro 2, Micro 4, Small, Medium, Large and XL.

## What the native renderer can improve

The current fast renderer executes thousands of drawing operations from Python, particularly for data cells, clock/header arcs and Micro polygons. It also downsamples a supersampled image and serializes it as PNG. A C++17 renderer built with a native raster library and PNG encoder could reduce interpreter and per-draw-call overhead.

This is an **implementation opportunity**, not a protocol claim. It cannot change raw capacity, correction strength, payload framing or decode tolerance by itself. It also does not establish a target such as “2 ms”: rasterization, antialiasing and PNG compression still have real costs.

## Compatibility contract before any promotion

| Contract | Requirement |
|---|---|
| Protocol input | Receive the already encoded symbol: geometry, cell states, registered palette, bootstrap bits and rendering options. The C++ layer must not reimplement framing or protection coding in phase one. |
| Output | Produce decode-equivalent PNG output at a declared DPI and supersampling factor. Byte-identical files are not required. |
| Reference | Python `render_png_fast()` remains available as the deterministic fallback and visual reference. |
| Validation | The experiment must pass the current Draft 0.6 geometry matrix with exact bytes. The unmodified Python reference must separately continue to pass every golden vector from Draft 0.2–0.6. |
| Visual checks | Sample cell centers, guard, clock, headers, quiet zone and center-reservation boundaries against documented tolerances. |
| Benchmark | Report core encode, native raster production and Python raster production as separate measurements on the same payload, geometry, DPI and output dimensions. |

## Implemented and remaining phases

1. **Complete:** define and use a versioned draw-list input after Python encoding.
2. **Complete:** implement guard, clock, headers, data cells, quiet zone and center boundary in C++17; retain text and center images on Python.
3. **Complete:** expose an explicit `native-experimental` option with a visible fallback reason; Python remains the default.
4. **Complete for this prototype:** run exact-decode coverage of every Draft 0.6 geometry, an integration test, the reference golden suite and a three-geometry timing comparison.
5. **Open:** add pixel-level tolerance tests, perspective/occlusion comparison of the two raster outputs and center text/image parity before considering a default change.

## Deployment implications

The Docker image now installs `libpng-dev` and compiles `server/python/native/orbiqo_renderer` during the existing native-toolchain build. A command-line renderer is isolated and easy to disable, but retains process-start cost. A future in-process extension could remove that overhead, but would create a materially more complex Python ABI and deployment contract; it is not part of this prototype.

## Non-goals

This evaluation does not migrate the encoder, decoder, vision pipeline or protocol to C++. It does not alter Constant Columns, supported format versions, registered palettes, golden vectors, benchmark methodology or the product claim. It also does not replace the real Python reference pipeline used by the Lab.
