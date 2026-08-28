# Orbiqo Profile Comparison Method

This artifact compares **Orbiqo’s own protection profiles before any external format comparison**. It is intended to answer a practical product question: which profile trades encoding time, decoding time, geometry and measured digital-occlusion resilience in a useful way for the same payload.

The runner uses a deterministic 64-byte binary payload and evaluates `Fast`, `Balanced`, `Robust` and `Extreme`. Each profile receives the same payload, chooses its smallest compatible Orbiqo geometry through Auto fit, and records the resulting geometry. The comparison is therefore a **practical configuration comparison**, not a claim that all profiles use equal geometry or have equivalent code rates.

Encode timing measures framing, protection-code generation and placement through the reference encoder. Direct PNG rendering is excluded. Decode timing measures the complete vision and decoding path from the same normalized 1024 px digital raster. Each timing metric has ten runs; the dashboard reports the median and retains raw values in `benchmark/results/ecc_profile_comparison_raw.csv`.

Occlusion uses the same 6% digital overlay profile for every internal profile. It tests three deterministic 64-byte payload patterns (`benchmark`, `counter`, and `periodic`) at four deterministic placements/seeds (101–104). A trial passes only when recovered bytes exactly equal the original payload. The dashboard presents the minimum success count across patterns so a strong result cannot hide a weak pattern.

> This is digital-only evidence. It does not represent print, camera-device, arbitrary-logo, or physical-overlay behavior. More redundancy is not assumed to improve every measured outcome; results are reported as observed.

The external QR, Aztec and JAB benchmark remains a distinct equal-area comparison. It uses Orbiqo Balanced by design for capacity and latency context, while the Robust oclusion result stays labeled as a separate resilience profile.
