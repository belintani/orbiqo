#include "orbiqo_codec.hpp"

#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void usage() {
  std::cerr << "usage:\n"
            << "  orbiqo_codec encode <payload_hex> <geometry> <ecc> <payload_type> [compression] [palette] [format]\n"
            << "  orbiqo_codec decode <packed_symbols_hex> <symbol_count> <header_codeword_hex>\n";
}

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

std::uint64_t parse_uint_hex(const std::string& value) {
  std::size_t consumed = 0;
  const std::uint64_t result = std::stoull(value, &consumed, 16);
  if (consumed != value.size()) throw std::invalid_argument("invalid hexadecimal integer");
  return result;
}

void print_encoded(const orbiqo::codec::EncodedSymbol& encoded) {
  std::cout << "payload_hex=" << orbiqo::codec::bytes_to_hex(encoded.payload) << '\n';
  std::cout << "frame_hex=" << orbiqo::codec::bytes_to_hex(encoded.frame) << '\n';
  std::cout << "rs_concatenated_hex=" << orbiqo::codec::bytes_to_hex(encoded.rs_concatenated) << '\n';
  std::cout << "rs_interleaved_hex=" << orbiqo::codec::bytes_to_hex(encoded.rs_interleaved) << '\n';
  std::cout << "channel_symbols_packed_hex=" << encoded.channel_symbols_packed_hex << '\n';
  std::cout << "channel_symbol_count=" << encoded.channel_symbols.size() << '\n';
  std::cout << "format_version=" << encoded.header.format_version << '\n';
  std::cout << "geometry_version=" << encoded.header.geometry_version << '\n';
  std::cout << "mask_id=" << encoded.header.mask_id << '\n';
  std::cout << "header_data_hex=" << orbiqo::codec::uint_to_hex(encoded.header.data, 6) << '\n';
  std::cout << "header_codeword_hex=" << orbiqo::codec::uint_to_hex(encoded.header.codeword, 8) << '\n';
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 2) {
      usage();
      return 2;
    }
    const std::string command = argv[1];
    if (command == "encode") {
      if (argc < 6 || argc > 9) {
        usage();
        return 2;
      }
      orbiqo::codec::EncodeOptions options;
      options.geometry_version = std::stoi(argv[3]);
      options.ecc_level = parse_ecc(argv[4]);
      options.payload_type = parse_type(argv[5]);
      if (argc >= 7) options.compression = parse_compression(argv[6]);
      if (argc == 8) options.palette_id = std::stoi(argv[7]);
      if (argc == 9) options.format_version = std::stoi(argv[8]);
      print_encoded(orbiqo::codec::encode(orbiqo::codec::hex_to_bytes(argv[2]), options));
      return 0;
    }
    if (command == "decode") {
      if (argc != 5) {
        usage();
        return 2;
      }
      const auto packed = orbiqo::codec::hex_to_bytes(argv[2]);
      const int symbol_count = std::stoi(argv[3]);
      const auto decoded = orbiqo::codec::decode(packed, symbol_count, parse_uint_hex(argv[4]));
      std::cout << "payload_hex=" << orbiqo::codec::bytes_to_hex(decoded.payload) << '\n';
      std::cout << "frame_hex=" << orbiqo::codec::bytes_to_hex(decoded.frame) << '\n';
      std::cout << "geometry_version=" << decoded.header.geometry_version << '\n';
      std::cout << "format_version=" << decoded.header.format_version << '\n';
      std::cout << "mask_id=" << decoded.header.mask_id << '\n';
      std::cout << "corrected_rs_symbols=" << decoded.corrected_rs_symbols << '\n';
      return 0;
    }
    usage();
    return 2;
  } catch (const std::exception& error) {
    std::cerr << "orbiqo_codec error: " << error.what() << '\n';
    return 1;
  }
}
