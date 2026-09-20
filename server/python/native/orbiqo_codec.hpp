#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace orbiqo::codec {

enum class Alphabet : std::uint8_t { Mono2 = 0, Color4 = 1 };
enum class PayloadType : std::uint8_t { Binary = 0, Utf8 = 1, Url = 2 };
enum class Compression : std::uint8_t { Auto = 255, None = 0, Deflate = 1 };
enum class EccLevel : std::uint8_t { Fast = 0, Balanced = 1, Robust = 2, Extreme = 3 };

struct EncodeOptions {
  int geometry_version = 0;
  int format_version = 5;
  Alphabet alphabet = Alphabet::Color4;
  PayloadType payload_type = PayloadType::Binary;
  Compression compression = Compression::Auto;
  EccLevel ecc_level = EccLevel::Balanced;
  int palette_id = 0;
};

struct Header {
  int format_version = 5;
  int geometry_version = 0;
  Alphabet alphabet = Alphabet::Color4;
  int palette_id = 0;
  EccLevel ecc_level = EccLevel::Balanced;
  int mask_id = 0;
  int encoded_payload_length = 0;
  std::uint64_t data = 0;
  std::uint64_t codeword = 0;
};

struct RenderCell {
  int ring = 0;
  int sector = 0;
  double r_inner = 0.0;
  double r_outer = 0.0;
  double theta_start = 0.0;
  double theta_end = 0.0;
  int state = 0;
  bool payload = false;
};

struct GeometryModel {
  int version = 0;
  int format_version = 5;
  int data_rings = 0;
  double data_inner = 0.0;
  double radial_pitch = 0.0;
  std::vector<int> sector_counts;
  std::vector<RenderCell> cells;
};

struct EncodedSymbol {
  std::vector<std::uint8_t> payload;
  PayloadType payload_type = PayloadType::Binary;
  std::vector<std::uint8_t> frame;
  std::vector<std::uint8_t> rs_concatenated;
  std::vector<std::uint8_t> rs_interleaved;
  std::vector<std::uint8_t> channel_symbols;
  std::string channel_symbols_packed_hex;
  Header header;
  GeometryModel geometry;
  std::vector<RenderCell> cells;
};

struct DecodedSymbol {
  std::vector<std::uint8_t> payload;
  PayloadType payload_type = PayloadType::Binary;
  std::vector<std::uint8_t> frame;
  Header header;
  int corrected_rs_symbols = 0;
};

EncodedSymbol encode(const std::vector<std::uint8_t>& payload, const EncodeOptions& options);
DecodedSymbol decode(const std::vector<std::uint8_t>& channel_symbols,
                     int channel_symbol_count,
                     std::uint64_t header_codeword);
DecodedSymbol decode_with_erasures(const std::vector<std::uint8_t>& channel_symbols,
                                   int channel_symbol_count,
                                   std::uint64_t header_codeword,
                                   const std::vector<int>& erasure_cells);

GeometryModel geometry_model(int geometry_version, int format_version, Alphabet alphabet = Alphabet::Color4);
Header decode_header_codeword(std::uint64_t codeword, int* corrected_bits = nullptr);
std::vector<int> header_physical_bits(const Header& header, int copy_index);
std::vector<int> clock_track_bits();

std::vector<std::uint8_t> hex_to_bytes(const std::string& hex);
std::string bytes_to_hex(const std::vector<std::uint8_t>& bytes);
std::string uint_to_hex(std::uint64_t value, int width_bytes);

}  // namespace orbiqo::codec
