# Real-camera corpus

This directory defines the reproducible intake for real-camera evidence. The images themselves are intentionally **not committed**: they may contain people, locations, device metadata, or other private information.

## Capture protocol

Use the Orbiqo Lab to generate the same payload for every case. Keep the generated symbol visible on a screen at native scale and capture it with a phone or webcam. Record the capture conditions in the manifest, but avoid names, faces, addresses, or other personal information.

For each geometry, collect at least:

- one frontal capture under neutral light;
- one mild perspective capture;
- one stronger perspective capture;
- one low-light capture;
- one capture with a bright reflection or glare;
- one capture after a small physical obstruction, such as a rounded sticker or fingertip at the edge.

Do not resize or enhance the original camera files before the runner. Preserve the original file separately and record only a relative path in the manifest. If an image came from a messaging app, mark that in `capture.compression` because the app may have recompressed it.

## Manifest

Copy `manifest.example.json` to a private working directory, put the images under its `images/` directory, and fill `expected_payload_sha256` with the SHA-256 of the original payload bytes. The runner also accepts `expected_payload_hex` for local smoke tests, but payload hex should not be committed when it contains private data.

Run from the repository root:

```bash
python3 benchmark/run_camera_corpus.py \
  --root /path/to/private-camera-corpus \
  --manifest manifest.json \
  --output /path/to/private-camera-corpus/report.json \
  --require-exact
```

The report stores image hashes, dimensions, formats, decode hashes, exact-match flags, errors, and timings. It does **not** store the image bytes or decoded payload. The native result is obtained directly from `orbiqo_native`; the Python process is used only as the compatibility oracle.

## Interpretation

A passing report means that the supplied files were decoded exactly in this local corpus. It is not a claim about all cameras, lighting, distances, devices, printing conditions, or viewing angles. Keep real-camera evidence separate from the synthetic digital matrices under `benchmark/results/`.
