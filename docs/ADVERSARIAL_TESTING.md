# Adversarial and fuzz testing

The Orbiqo gate uses deterministic fuzz corpora so every failure is reproducible. One thousand seeded 45-bit header words exercise semantic validation. Every byte in a valid framed payload is mutated independently to verify CRC32C rejection, and 257 seeded arbitrary frame lengths exercise truncation, invalid enums, malformed compression, and length mismatches.

The false-positive corpus contains blank fields, a dense checkerboard, concentric rings designed to resemble the guard, and eight seeded RGB noise fields. A passing result requires every image to end in a controlled `DetectionError`; silently returning bytes is a failure. The Node-to-Python boundary separately verifies invalid Base64, non-image streams, the 64 KiB payload limit, and the 12 MiB request limit.

The suite is a defensive regression corpus, not a proof of security. It does not replace continuous coverage-guided native fuzzing of OpenCV, Pillow, ZXing-C++, libpng, libtiff, or the JAB C implementation.
