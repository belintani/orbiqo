#include "orbiqo_codec.hpp"

#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

orbiqo::codec::EccLevel parse_ecc(const std::string& value) {
  if (value == "fast") return orbiqo::codec::EccLevel::Fast;
  if (value == "balanced") return orbiqo::codec::EccLevel::Balanced;
  if (value == "robust") return orbiqo::codec::EccLevel::Robust;
  if (value == "extreme") return orbiqo::codec::EccLevel::Extreme;
  throw std::invalid_argument("unsupported ECC level");
}

orbiqo::codec::PayloadType parse_type(const std::string& value) {
  if (value == "binary") return orbiqo::codec::PayloadType::Binary;
  if (value == "utf8") return orbiqo::codec::PayloadType::Utf8;
  if (value == "url") return orbiqo::codec::PayloadType::Url;
  throw std::invalid_argument("unsupported payload type");
}

orbiqo::codec::Compression parse_compression(const std::string& value) {
  if (value == "auto") return orbiqo::codec::Compression::Auto;
  if (value == "none") return orbiqo::codec::Compression::None;
  if (value == "deflate") return orbiqo::codec::Compression::Deflate;
  throw std::invalid_argument("unsupported compression");
}

void usage() {
  std::cerr << "usage: orbiqo_codec_bench <payload_hex> <geometry> <ecc> <payload_type> <compression> <palette> <format> [repeats]\n";
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 8 || argc > 9) {
      usage();
      return 2;
    }
    const auto payload = orbiqo::codec::hex_to_bytes(argv[1]);
    orbiqo::codec::EncodeOptions options;
    options.geometry_version = std::stoi(argv[2]);
    options.ecc_level = parse_ecc(argv[3]);
    options.payload_type = parse_type(argv[4]);
    options.compression = parse_compression(argv[5]);
    options.palette_id = std::stoi(argv[6]);
    options.format_version = std::stoi(argv[7]);
    const int repeats = argc == 9 ? std::stoi(argv[8]) : 1000;
    if (repeats <= 0) throw std::invalid_argument("repeats must be positive");

    std::uint64_t sink = 0;
    orbiqo::codec::EncodedSymbol encoded;
    const auto encode_start = std::chrono::steady_clock::now();
    for (int index = 0; index < repeats; ++index) {
      encoded = orbiqo::codec::encode(payload, options);
      sink ^= encoded.header.codeword + static_cast<std::uint64_t>(encoded.channel_symbols.size());
    }
    const auto encode_end = std::chrono::steady_clock::now();

    const auto packed = orbiqo::codec::hex_to_bytes(encoded.channel_symbols_packed_hex);
    const auto decode_start = std::chrono::steady_clock::now();
    for (int index = 0; index < repeats; ++index) {
      const auto decoded = orbiqo::codec::decode(
          packed,
          static_cast<int>(encoded.channel_symbols.size()),
          encoded.header.codeword);
      sink ^= decoded.header.codeword + static_cast<std::uint64_t>(decoded.payload.size());
    }
    const auto decode_end = std::chrono::steady_clock::now();

    const auto encode_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(encode_end - encode_start).count();
    const auto decode_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(decode_end - decode_start).count();
    std::cout << "format_version=" << options.format_version << '\n';
    std::cout << "geometry_version=" << options.geometry_version << '\n';
    std::cout << "repeats=" << repeats << '\n';
    std::cout << "encode_mean_ms=" << (static_cast<double>(encode_ns) / repeats / 1'000'000.0) << '\n';
    std::cout << "decode_mean_ms=" << (static_cast<double>(decode_ns) / repeats / 1'000'000.0) << '\n';
    std::cout << "sink=" << sink << '\n';
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "orbiqo_codec_bench error: " << error.what() << '\n';
    return 1;
  }
}
