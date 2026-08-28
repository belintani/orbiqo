# Benchmark toolchain decision

ZXing-C++ is the selected common toolchain for QR Code and Aztec Code. Its official repository documents read and write support for both formats, provides Python bindings, has recent releases and active commits, and exposes the same implementation family for generation and decoding. This reduces toolchain variance in the comparison. Source: [zxing-cpp/zxing-cpp](https://github.com/zxing-cpp/zxing-cpp), reviewed 2026-08-25.

JAB Code remains conditional. The official repository contains a C11 reader and writer and points to ISO/IEC 23634:2022, but its build instructions state Ubuntu 14.04, core source activity is dated 2021, and the repository publishes no tagged releases. A 2026 license-only commit does not establish current runtime compatibility. JAB will enter the benchmark only if the official writer and reader compile and complete a deterministic round trip in the current Ubuntu environment without source patches. Source: [jabcode/jabcode](https://github.com/jabcode/jabcode), reviewed 2026-08-25.

The benchmark will identify library versions, encoding parameters, artifact dimensions, payload bytes, generation time, decode time, and synthetic-degradation outcomes. It will not claim physical-print performance.
