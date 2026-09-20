#include "orbiqo_codec.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <map>
#include <numeric>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <unordered_map>
#include <utility>

#include <zlib.h>

namespace orbiqo::codec {
namespace {

constexpr std::uint8_t kFormatMagic = 0xD7;
constexpr int kCurrentFormat = 5;
constexpr int kBchN = 63;
constexpr int kBchK = 45;
constexpr int kBchParity = 18;
constexpr std::uint64_t kBchGenerator = 0x782CF;
constexpr int kClockSlots = 64;
constexpr int kHeaderPhysicalSlots = 64;
constexpr int kHeaderCodeBits = 63;
constexpr int kHeaderSlotOffsets[4] = {0, 17, 43, 29};
constexpr int kHeaderReservedBits[4] = {1, 0, 1, 0};
constexpr double kTau = 6.283185307179586476925286766559;
constexpr double kDataOuter = 0.91;
constexpr double kConstantDataInner = 0.41;
constexpr double kLegacyDataInner = 0.38;
constexpr int kDataReservedCells = 24;
constexpr int kColorReferenceRepetitions = 4;
constexpr int kRoundSectorMultiple = 8;
constexpr int kMinRingSectors = 24;
constexpr int kBchGfSize = 64;
constexpr int kBchGfOrder = 63;
constexpr int kBchGfPrimitive = 0x43;
constexpr std::uint32_t kCrc32cPolynomial = 0x82F63B78U;

struct EccProfile {
  int data_bytes;
  int parity_bytes;
};

EccProfile profile(EccLevel level) {
  switch (level) {
    case EccLevel::Fast: return {223, 32};
    case EccLevel::Balanced: return {191, 64};
    case EccLevel::Robust: return {159, 96};
    case EccLevel::Extreme: return {127, 128};
  }
  throw std::invalid_argument("unsupported ECC level");
}

int bits_per_cell(Alphabet alphabet) {
  switch (alphabet) {
    case Alphabet::Mono2: return 1;
    case Alphabet::Color4: return 2;
  }
  throw std::invalid_argument("unsupported alphabet");
}

int round_to_multiple(double value, int multiple) {
  return std::max(kMinRingSectors, static_cast<int>(value / multiple + 0.5) * multiple);
}

long long python_round(double value) {
  const double lower = std::floor(value);
  const double fraction = value - lower;
  if (fraction < 0.5) return static_cast<long long>(lower);
  if (fraction > 0.5) return static_cast<long long>(lower + 1.0);
  const auto integral = static_cast<long long>(lower);
  return (integral % 2 == 0) ? integral : integral + 1;
}

std::uint8_t gf64_mul(std::uint8_t a, std::uint8_t b) {
  std::uint8_t result = 0;
  while (b != 0) {
    if (b & 1U) result ^= a;
    b >>= 1U;
    a = static_cast<std::uint8_t>(a << 1U);
    if (a & kBchGfSize) a ^= kBchGfPrimitive;
  }
  return static_cast<std::uint8_t>(result & (kBchGfSize - 1));
}

std::uint8_t bch_alpha(int power) {
  std::uint8_t value = 1;
  int normalized = power % kBchGfOrder;
  if (normalized < 0) normalized += kBchGfOrder;
  for (int index = 0; index < normalized; ++index) value = gf64_mul(value, 2);
  return value;
}

int polynomial_degree(std::uint64_t polynomial) {
  if (polynomial == 0) return -1;
  int degree = 0;
  while (polynomial >>= 1U) ++degree;
  return degree;
}

std::uint64_t polynomial_mod(std::uint64_t dividend, std::uint64_t divisor) {
  const int divisor_degree = polynomial_degree(divisor);
  while (dividend != 0 && polynomial_degree(dividend) >= divisor_degree) {
    dividend ^= divisor << (polynomial_degree(dividend) - divisor_degree);
  }
  return dividend;
}

std::uint8_t bch_polynomial_eval(std::uint64_t polynomial, std::uint8_t x) {
  std::uint8_t result = 0;
  for (int degree = kBchN - 1; degree >= 0; --degree) {
    result = gf64_mul(result, x);
    if ((polynomial >> degree) & 1U) result ^= 1U;
  }
  return result;
}

using BchSyndrome = std::array<std::uint8_t, 6>;

BchSyndrome bch_syndromes(std::uint64_t codeword) {
  if (codeword >= (std::uint64_t{1} << kBchN)) throw std::invalid_argument("BCH codeword must fit in 63 bits");
  BchSyndrome result{};
  for (int index = 0; index < 6; ++index) result[static_cast<std::size_t>(index)] = bch_polynomial_eval(codeword, bch_alpha(index + 1));
  return result;
}

bool all_zero(const BchSyndrome& syndrome) {
  return std::all_of(syndrome.begin(), syndrome.end(), [](std::uint8_t value) { return value == 0; });
}

std::uint64_t bch_encode(std::uint64_t data) {
  if (data >= (std::uint64_t{1} << kBchK)) throw std::invalid_argument("BCH data must fit in 45 bits");
  const std::uint64_t shifted = data << kBchParity;
  const std::uint64_t codeword = shifted | polynomial_mod(shifted, kBchGenerator);
  if (!all_zero(bch_syndromes(codeword))) throw std::runtime_error("internal BCH encoder failure");
  return codeword;
}

std::uint64_t bch_decode(std::uint64_t codeword, int* corrected_bits) {
  const BchSyndrome syndrome = bch_syndromes(codeword);
  if (all_zero(syndrome)) {
    *corrected_bits = 0;
    return codeword >> kBchParity;
  }

  std::array<BchSyndrome, kBchN> single{};
  for (int bit = 0; bit < kBchN; ++bit) single[static_cast<std::size_t>(bit)] = bch_syndromes(std::uint64_t{1} << bit);
  std::uint64_t found_mask = 0;
  int found_weight = 0;
  auto matches = [&](const BchSyndrome& candidate) { return candidate == syndrome; };
  for (int a = 0; a < kBchN; ++a) {
    if (matches(single[static_cast<std::size_t>(a)])) {
      found_mask = std::uint64_t{1} << a;
      found_weight = 1;
      break;
    }
  }
  if (found_weight == 0) {
    for (int a = 0; a < kBchN && found_weight == 0; ++a) {
      for (int b = a + 1; b < kBchN; ++b) {
        BchSyndrome candidate{};
        for (int index = 0; index < 6; ++index) candidate[static_cast<std::size_t>(index)] = single[static_cast<std::size_t>(a)][static_cast<std::size_t>(index)] ^ single[static_cast<std::size_t>(b)][static_cast<std::size_t>(index)];
        if (matches(candidate)) {
          found_mask = (std::uint64_t{1} << a) | (std::uint64_t{1} << b);
          found_weight = 2;
          break;
        }
      }
    }
  }
  if (found_weight == 0) {
    for (int a = 0; a < kBchN && found_weight == 0; ++a) {
      for (int b = a + 1; b < kBchN && found_weight == 0; ++b) {
        for (int c = b + 1; c < kBchN; ++c) {
          BchSyndrome candidate{};
          for (int index = 0; index < 6; ++index) candidate[static_cast<std::size_t>(index)] = single[static_cast<std::size_t>(a)][static_cast<std::size_t>(index)] ^ single[static_cast<std::size_t>(b)][static_cast<std::size_t>(index)] ^ single[static_cast<std::size_t>(c)][static_cast<std::size_t>(index)];
          if (matches(candidate)) {
            found_mask = (std::uint64_t{1} << a) | (std::uint64_t{1} << b) | (std::uint64_t{1} << c);
            found_weight = 3;
            break;
          }
        }
      }
    }
  }
  if (found_weight == 0) throw std::runtime_error("BCH codeword is not correctable within t=3");
  const std::uint64_t corrected = codeword ^ found_mask;
  if (!all_zero(bch_syndromes(corrected))) throw std::runtime_error("BCH correction failed syndrome validation");
  *corrected_bits = found_weight;
  return corrected >> kBchParity;
}

std::uint32_t crc32c(const std::vector<std::uint8_t>& data) {
  static const std::array<std::uint32_t, 256> table = [] {
    std::array<std::uint32_t, 256> values{};
    for (std::uint32_t byte = 0; byte < 256; ++byte) {
      std::uint32_t crc = byte;
      for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1U) ^ ((crc & 1U) ? kCrc32cPolynomial : 0U);
      values[byte] = crc;
    }
    return values;
  }();
  std::uint32_t crc = 0xFFFFFFFFU;
  for (std::uint8_t byte : data) crc = table[(crc ^ byte) & 0xFFU] ^ (crc >> 8U);
  return crc ^ 0xFFFFFFFFU;
}

std::vector<std::uint8_t> deflate_bytes(const std::vector<std::uint8_t>& input) {
  uLongf bound = compressBound(static_cast<uLong>(input.size()));
  std::vector<std::uint8_t> output(static_cast<std::size_t>(bound));
  const int result = compress2(output.data(), &bound, input.data(), static_cast<uLong>(input.size()), 9);
  if (result != Z_OK) throw std::runtime_error("DEFLATE compression failed");
  output.resize(static_cast<std::size_t>(bound));
  return output;
}

std::vector<std::uint8_t> inflate_bytes(const std::vector<std::uint8_t>& input, std::size_t expected_size) {
  std::vector<std::uint8_t> output(expected_size);
  uLongf size = static_cast<uLongf>(expected_size);
  const int result = uncompress(output.data(), &size, input.data(), static_cast<uLong>(input.size()));
  if (result != Z_OK || size != expected_size) throw std::runtime_error("DEFLATE payload is malformed");
  return output;
}

std::uint8_t payload_control(PayloadType type, Compression compression) {
  return static_cast<std::uint8_t>((1U << 6U) | ((static_cast<int>(type) & 0x3) << 4U) | ((static_cast<int>(compression) & 0x3) << 2U));
}

struct FrameData {
  std::vector<std::uint8_t> payload;
  std::vector<std::uint8_t> encoded;
  PayloadType payload_type{};
  Compression compression{};
};

FrameData encode_frame(const std::vector<std::uint8_t>& payload, PayloadType payload_type, Compression requested) {
  if (payload.size() > 0xFFFFFFU) throw std::invalid_argument("payload exceeds the 24-bit frame length");
  Compression selected = requested;
  std::vector<std::uint8_t> stored = payload;
  if (requested == Compression::Auto) {
    const auto compressed = deflate_bytes(payload);
    if (compressed.size() < payload.size()) {
      selected = Compression::Deflate;
      stored = compressed;
    } else {
      selected = Compression::None;
    }
  } else if (requested == Compression::Deflate) {
    stored = deflate_bytes(payload);
  } else if (requested != Compression::None) {
    throw std::invalid_argument("unsupported compression");
  }
  std::vector<std::uint8_t> body;
  body.reserve(4 + stored.size());
  body.push_back(payload_control(payload_type, selected));
  body.push_back(static_cast<std::uint8_t>((payload.size() >> 16U) & 0xFFU));
  body.push_back(static_cast<std::uint8_t>((payload.size() >> 8U) & 0xFFU));
  body.push_back(static_cast<std::uint8_t>(payload.size() & 0xFFU));
  body.insert(body.end(), stored.begin(), stored.end());
  const std::uint32_t checksum = crc32c(body);
  std::vector<std::uint8_t> encoded = body;
  for (int shift = 24; shift >= 0; shift -= 8) encoded.push_back(static_cast<std::uint8_t>((checksum >> shift) & 0xFFU));
  return {payload, std::move(encoded), payload_type, selected};
}

FrameData decode_frame(const std::vector<std::uint8_t>& encoded) {
  if (encoded.size() < 8) throw std::runtime_error("frame is shorter than the fixed overhead");
  const std::size_t body_size = encoded.size() - 4;
  std::vector<std::uint8_t> body(encoded.begin(), encoded.begin() + static_cast<std::ptrdiff_t>(body_size));
  std::uint32_t expected_crc = 0;
  for (std::size_t index = body_size; index < encoded.size(); ++index) expected_crc = (expected_crc << 8U) | encoded[index];
  if (crc32c(body) != expected_crc) throw std::runtime_error("CRC32C mismatch");
  const std::uint8_t control = body[0];
  if (((control >> 6U) & 0x3U) != 1U) throw std::runtime_error("unsupported frame version");
  const int type_value = (control >> 4U) & 0x3U;
  const int compression_value = (control >> 2U) & 0x3U;
  if (type_value > 2 || compression_value > 1) throw std::runtime_error("unsupported frame enum");
  const PayloadType payload_type = static_cast<PayloadType>(type_value);
  const Compression compression = static_cast<Compression>(compression_value);
  const std::size_t original_length = (static_cast<std::size_t>(body[1]) << 16U) | (static_cast<std::size_t>(body[2]) << 8U) | body[3];
  const std::vector<std::uint8_t> stored(body.begin() + 4, body.end());
  std::vector<std::uint8_t> payload = compression == Compression::Deflate ? inflate_bytes(stored, original_length) : stored;
  if (payload.size() != original_length) throw std::runtime_error("original length mismatch");
  return {std::move(payload), encoded, payload_type, compression};
}

struct Galois256 {
  std::array<std::uint8_t, 512> exp{};
  std::array<std::uint8_t, 256> log{};
  Galois256() {
    std::uint16_t value = 1;
    for (int index = 0; index < 255; ++index) {
      exp[static_cast<std::size_t>(index)] = static_cast<std::uint8_t>(value);
      log[static_cast<std::size_t>(value)] = static_cast<std::uint8_t>(index);
      value <<= 1U;
      if (value & 0x100U) value ^= 0x11DU;
    }
    for (int index = 255; index < 512; ++index) exp[static_cast<std::size_t>(index)] = exp[static_cast<std::size_t>(index - 255)];
  }
  std::uint8_t mul(std::uint8_t a, std::uint8_t b) const {
    if (a == 0 || b == 0) return 0;
    return exp[static_cast<std::size_t>(log[a] + log[b])];
  }
  std::uint8_t div(std::uint8_t a, std::uint8_t b) const {
    if (b == 0) throw std::runtime_error("GF division by zero");
    if (a == 0) return 0;
    int power = static_cast<int>(log[a]) - static_cast<int>(log[b]);
    if (power < 0) power += 255;
    return exp[static_cast<std::size_t>(power)];
  }
  std::uint8_t pow(std::uint8_t a, int power) const {
    if (a == 0) return power == 0 ? 1 : 0;
    int normalized = (static_cast<int>(log[a]) * power) % 255;
    if (normalized < 0) normalized += 255;
    return exp[static_cast<std::size_t>(normalized)];
  }
};

const Galois256& gf() {
  static const Galois256 field;
  return field;
}

std::vector<std::uint8_t> poly_add(const std::vector<std::uint8_t>& p, const std::vector<std::uint8_t>& q) {
  std::vector<std::uint8_t> result(std::max(p.size(), q.size()), 0);
  std::copy(p.begin(), p.end(), result.end() - static_cast<std::ptrdiff_t>(p.size()));
  for (std::size_t index = 0; index < q.size(); ++index) result[result.size() - q.size() + index] ^= q[index];
  return result;
}

std::vector<std::uint8_t> poly_mul(const std::vector<std::uint8_t>& p, const std::vector<std::uint8_t>& q) {
  std::vector<std::uint8_t> result(p.size() + q.size() - 1, 0);
  for (std::size_t j = 0; j < q.size(); ++j) {
    if (q[j] == 0) continue;
    for (std::size_t i = 0; i < p.size(); ++i) {
      if (p[i] != 0) result[i + j] ^= gf().mul(p[i], q[j]);
    }
  }
  return result;
}

std::vector<std::uint8_t> poly_scale(const std::vector<std::uint8_t>& p, std::uint8_t scale) {
  std::vector<std::uint8_t> result(p.size(), 0);
  for (std::size_t i = 0; i < p.size(); ++i) result[i] = gf().mul(p[i], scale);
  return result;
}

std::vector<std::uint8_t> poly_div(const std::vector<std::uint8_t>& dividend, const std::vector<std::uint8_t>& divisor) {
  if (divisor.empty()) throw std::invalid_argument("empty polynomial divisor");
  std::vector<std::uint8_t> output = dividend;
  if (output.size() < divisor.size()) return output;
  for (std::size_t i = 0; i <= output.size() - divisor.size(); ++i) {
    const std::uint8_t coefficient = output[i];
    if (coefficient == 0) continue;
    for (std::size_t j = 1; j < divisor.size(); ++j) output[i + j] ^= gf().mul(divisor[j], coefficient);
  }
  return std::vector<std::uint8_t>(output.end() - static_cast<std::ptrdiff_t>(divisor.size() - 1), output.end());
}

std::uint8_t poly_eval(const std::vector<std::uint8_t>& polynomial, std::uint8_t x) {
  std::uint8_t value = polynomial.empty() ? 0 : polynomial[0];
  for (std::size_t index = 1; index < polynomial.size(); ++index) value = gf().mul(value, x) ^ polynomial[index];
  return value;
}

std::vector<std::uint8_t> generator_poly(int parity_bytes) {
  std::vector<std::uint8_t> generator{1};
  for (int index = 0; index < parity_bytes; ++index) generator = poly_mul(generator, {1, gf().pow(2, index)});
  return generator;
}

std::vector<std::uint8_t> rs_encode_block(const std::vector<std::uint8_t>& data, int parity_bytes) {
  if (data.size() + static_cast<std::size_t>(parity_bytes) > 255U) throw std::invalid_argument("RS block is longer than 255 symbols");
  const auto generator = generator_poly(parity_bytes);
  std::vector<std::uint8_t> output = data;
  output.resize(data.size() + static_cast<std::size_t>(parity_bytes), 0);
  for (std::size_t i = 0; i < data.size(); ++i) {
    const std::uint8_t coefficient = output[i];
    if (coefficient == 0) continue;
    for (std::size_t j = 1; j < generator.size(); ++j) output[i + j] ^= gf().mul(generator[j], coefficient);
  }
  std::copy(data.begin(), data.end(), output.begin());
  return output;
}

std::vector<int> block_data_lengths(std::size_t data_length, EccLevel level) {
  const EccProfile p = profile(level);
  std::vector<int> result;
  const std::size_t full = data_length / static_cast<std::size_t>(p.data_bytes);
  const std::size_t remainder = data_length % static_cast<std::size_t>(p.data_bytes);
  result.assign(full, p.data_bytes);
  if (remainder != 0) result.push_back(static_cast<int>(remainder));
  return result;
}

int encoded_length(std::size_t data_length, EccLevel level) {
  const EccProfile p = profile(level);
  const auto lengths = block_data_lengths(data_length, level);
  return static_cast<int>(data_length + lengths.size() * static_cast<std::size_t>(p.parity_bytes));
}

std::vector<std::uint8_t> rs_encode(const std::vector<std::uint8_t>& data, EccLevel level) {
  const EccProfile p = profile(level);
  std::vector<std::uint8_t> output;
  std::size_t offset = 0;
  for (int length : block_data_lengths(data.size(), level)) {
    const std::vector<std::uint8_t> block(data.begin() + static_cast<std::ptrdiff_t>(offset), data.begin() + static_cast<std::ptrdiff_t>(offset + length));
    const auto encoded = rs_encode_block(block, p.parity_bytes);
    output.insert(output.end(), encoded.begin(), encoded.end());
    offset += static_cast<std::size_t>(length);
  }
  return output;
}

std::vector<std::uint8_t> calc_syndromes(const std::vector<std::uint8_t>& message, int parity_bytes) {
  std::vector<std::uint8_t> syndromes{0};
  for (int index = 0; index < parity_bytes; ++index) syndromes.push_back(poly_eval(message, gf().pow(2, index)));
  return syndromes;
}

bool syndromes_zero(const std::vector<std::uint8_t>& syndromes) {
  return std::all_of(syndromes.begin(), syndromes.end(), [](std::uint8_t value) { return value == 0; });
}

std::vector<std::uint8_t> forney_syndromes(const std::vector<std::uint8_t>& syndromes, const std::vector<int>& erase_positions, int message_length) {
  std::vector<std::uint8_t> result(syndromes.begin() + 1, syndromes.end());
  for (int position : erase_positions) {
    const int reversed = message_length - 1 - position;
    const std::uint8_t x = gf().pow(2, reversed);
    for (std::size_t j = 0; j + 1 < result.size(); ++j) result[j] = gf().mul(result[j], x) ^ result[j + 1];
  }
  return result;
}

std::vector<std::uint8_t> find_error_locator(const std::vector<std::uint8_t>& syndromes, int parity_bytes, int erase_count) {
  std::vector<std::uint8_t> error_locator{1};
  std::vector<std::uint8_t> old_locator{1};
  const int syndrome_shift = static_cast<int>(syndromes.size()) - parity_bytes;
  for (int index = 0; index < parity_bytes - erase_count; ++index) {
    const int k = index + syndrome_shift;
    if (k < 0 || k >= static_cast<int>(syndromes.size())) throw std::runtime_error("RS syndrome index out of range");
    std::uint8_t delta = syndromes[static_cast<std::size_t>(k)];
    for (std::size_t j = 1; j < error_locator.size(); ++j) {
      const int syndrome_index = k - static_cast<int>(j);
      if (syndrome_index >= 0) delta ^= gf().mul(error_locator[error_locator.size() - j - 1], syndromes[static_cast<std::size_t>(syndrome_index)]);
    }
    old_locator.push_back(0);
    if (delta != 0) {
      if (old_locator.size() > error_locator.size()) {
        const auto new_locator = poly_scale(old_locator, delta);
        old_locator = poly_scale(error_locator, gf().pow(delta, -1));
        error_locator = new_locator;
      }
      error_locator = poly_add(error_locator, poly_scale(old_locator, delta));
    }
  }
  while (!error_locator.empty() && error_locator.front() == 0) error_locator.erase(error_locator.begin());
  const int errors = static_cast<int>(error_locator.size()) - 1;
  if ((errors - erase_count) * 2 + erase_count > parity_bytes) throw std::runtime_error("too many RS errors to correct");
  return error_locator;
}

std::vector<int> find_errors(const std::vector<std::uint8_t>& locator, int message_length) {
  const int expected = static_cast<int>(locator.size()) - 1;
  std::vector<int> positions;
  for (int index = 0; index < message_length; ++index) {
    if (poly_eval(locator, gf().pow(2, index)) == 0) positions.push_back(message_length - 1 - index);
  }
  if (static_cast<int>(positions.size()) != expected) throw std::runtime_error("RS Chien search found an unexpected number of errors");
  return positions;
}

std::vector<std::uint8_t> errata_locator(const std::vector<int>& coefficient_positions) {
  std::vector<std::uint8_t> locator{1};
  for (int position : coefficient_positions) locator = poly_mul(locator, {gf().pow(2, position), 1});
  return locator;
}

std::vector<std::uint8_t> error_evaluator(const std::vector<std::uint8_t>& syndromes_reversed, const std::vector<std::uint8_t>& locator, int nsym) {
  return poly_div(poly_mul(syndromes_reversed, locator), [&] {
    std::vector<std::uint8_t> divisor(static_cast<std::size_t>(nsym + 2), 0);
    divisor[0] = 1;
    return divisor;
  }());
}

std::vector<std::uint8_t> correct_errata(const std::vector<std::uint8_t>& input, const std::vector<std::uint8_t>& syndromes, const std::vector<int>& positions) {
  std::vector<int> coefficient_positions;
  coefficient_positions.reserve(positions.size());
  for (int position : positions) coefficient_positions.push_back(static_cast<int>(input.size()) - 1 - position);
  const auto locator = errata_locator(coefficient_positions);
  std::vector<std::uint8_t> reversed_syndromes(syndromes.rbegin(), syndromes.rend());
  auto evaluator = error_evaluator(reversed_syndromes, locator, static_cast<int>(locator.size()) - 1);

  std::vector<std::uint8_t> x_values;
  x_values.reserve(coefficient_positions.size());
  for (int coefficient_position : coefficient_positions) x_values.push_back(gf().pow(2, coefficient_position));
  std::vector<std::uint8_t> correction(input.size(), 0);
  for (std::size_t index = 0; index < x_values.size(); ++index) {
    const std::uint8_t x = x_values[index];
    const std::uint8_t x_inverse = gf().pow(x, -1);
    std::uint8_t locator_prime = 1;
    for (std::size_t other = 0; other < x_values.size(); ++other) {
      if (other != index) locator_prime = gf().mul(locator_prime, 1U ^ gf().mul(x_inverse, x_values[other]));
    }
    if (locator_prime == 0) throw std::runtime_error("RS Forney derivative is zero");
    std::uint8_t y = poly_eval(evaluator, x_inverse);
    y = gf().mul(gf().pow(x, 1), y);
    correction[static_cast<std::size_t>(positions[index])] = gf().div(y, locator_prime);
  }
  std::vector<std::uint8_t> output = input;
  for (std::size_t index = 0; index < output.size(); ++index) output[index] ^= correction[index];
  return output;
}

std::pair<std::vector<std::uint8_t>, int> rs_decode_block(const std::vector<std::uint8_t>& input, int parity_bytes, std::vector<int> erase_positions) {
  if (input.size() > 255U) throw std::invalid_argument("RS block is longer than 255 symbols");
  if (erase_positions.size() > static_cast<std::size_t>(parity_bytes)) throw std::runtime_error("too many RS erasures");
  std::sort(erase_positions.begin(), erase_positions.end());
  erase_positions.erase(std::unique(erase_positions.begin(), erase_positions.end()), erase_positions.end());
  for (int position : erase_positions) {
    if (position < 0 || position >= static_cast<int>(input.size())) throw std::invalid_argument("RS erasure position out of range");
  }
  std::vector<std::uint8_t> message = input;
  for (int position : erase_positions) message[static_cast<std::size_t>(position)] = 0;
  const auto syndromes = calc_syndromes(message, parity_bytes);
  if (syndromes_zero(syndromes)) return {std::vector<std::uint8_t>(message.begin(), message.end() - parity_bytes), 0};
  const auto modified = forney_syndromes(syndromes, erase_positions, static_cast<int>(message.size()));
  auto locator = find_error_locator(modified, parity_bytes, static_cast<int>(erase_positions.size()));
  std::reverse(locator.begin(), locator.end());
  auto error_positions = find_errors(locator, static_cast<int>(message.size()));
  std::vector<int> all_positions = erase_positions;
  all_positions.insert(all_positions.end(), error_positions.begin(), error_positions.end());
  message = correct_errata(message, syndromes, all_positions);
  if (!syndromes_zero(calc_syndromes(message, parity_bytes))) throw std::runtime_error("RS correction failed syndrome validation");
  return {std::vector<std::uint8_t>(message.begin(), message.end() - parity_bytes), static_cast<int>(all_positions.size())};
}

std::vector<std::uint8_t> rs_decode(const std::vector<std::uint8_t>& encoded, std::size_t data_length, EccLevel level, int* corrected_symbols) {
  const EccProfile p = profile(level);
  if (encoded.size() != static_cast<std::size_t>(encoded_length(data_length, level))) throw std::runtime_error("RS encoded length mismatch");
  std::vector<std::uint8_t> data;
  std::size_t offset = 0;
  int corrected = 0;
  for (int length : block_data_lengths(data_length, level)) {
    const std::size_t block_length = static_cast<std::size_t>(length + p.parity_bytes);
    const std::vector<std::uint8_t> block(encoded.begin() + static_cast<std::ptrdiff_t>(offset), encoded.begin() + static_cast<std::ptrdiff_t>(offset + block_length));
    const auto result = rs_decode_block(block, p.parity_bytes, {});
    data.insert(data.end(), result.first.begin(), result.first.end());
    corrected += result.second;
    offset += block_length;
  }
  *corrected_symbols = corrected;
  return data;
}

std::vector<std::uint8_t> rs_decode_with_erasures(const std::vector<std::uint8_t>& encoded, std::size_t data_length, EccLevel level, const std::vector<int>& erasure_positions, int* corrected_symbols) {
  const EccProfile p = profile(level);
  if (encoded.size() != static_cast<std::size_t>(encoded_length(data_length, level))) throw std::runtime_error("RS encoded length mismatch");
  std::vector<std::uint8_t> data;
  std::size_t offset = 0;
  int corrected = 0;
  for (int length : block_data_lengths(data_length, level)) {
    const std::size_t block_length = static_cast<std::size_t>(length + p.parity_bytes);
    std::vector<int> local_erasures;
    for (int position : erasure_positions) if (position >= static_cast<int>(offset) && position < static_cast<int>(offset + block_length)) local_erasures.push_back(position - static_cast<int>(offset));
    const std::vector<std::uint8_t> block(encoded.begin() + static_cast<std::ptrdiff_t>(offset), encoded.begin() + static_cast<std::ptrdiff_t>(offset + block_length));
    const auto result = rs_decode_block(block, p.parity_bytes, std::move(local_erasures));
    data.insert(data.end(), result.first.begin(), result.first.end());
    corrected += result.second;
    offset += block_length;
  }
  *corrected_symbols = corrected;
  return data;
}

std::vector<std::uint8_t> interleave(const std::vector<std::uint8_t>& concatenated, std::size_t data_length, EccLevel level) {
  const EccProfile p = profile(level);
  const auto lengths = block_data_lengths(data_length, level);
  std::vector<std::vector<std::uint8_t>> blocks;
  std::size_t offset = 0;
  for (int length : lengths) {
    const std::size_t block_length = static_cast<std::size_t>(length + p.parity_bytes);
    blocks.emplace_back(concatenated.begin() + static_cast<std::ptrdiff_t>(offset), concatenated.begin() + static_cast<std::ptrdiff_t>(offset + block_length));
    offset += block_length;
  }
  std::vector<std::uint8_t> output;
  const std::size_t max_length = blocks.empty() ? 0 : std::max_element(blocks.begin(), blocks.end(), [](const auto& left, const auto& right) { return left.size() < right.size(); })->size();
  for (std::size_t column = 0; column < max_length; ++column) for (const auto& block : blocks) if (column < block.size()) output.push_back(block[column]);
  return output;
}

std::vector<std::uint8_t> deinterleave(const std::vector<std::uint8_t>& interleaved_bytes, std::size_t data_length, EccLevel level) {
  const EccProfile p = profile(level);
  const auto lengths = block_data_lengths(data_length, level);
  std::vector<std::vector<std::uint8_t>> blocks;
  for (int length : lengths) blocks.emplace_back(static_cast<std::size_t>(length + p.parity_bytes), 0);
  std::size_t cursor = 0;
  std::size_t max_length = 0;
  for (const auto& block : blocks) max_length = std::max(max_length, block.size());
  for (std::size_t column = 0; column < max_length; ++column) {
    for (auto& block : blocks) if (column < block.size()) {
      if (cursor >= interleaved_bytes.size()) throw std::runtime_error("RS deinterleaver cursor overflow");
      block[column] = interleaved_bytes[cursor++];
    }
  }
  if (cursor != interleaved_bytes.size()) throw std::runtime_error("RS deinterleaver cursor mismatch");
  std::vector<std::uint8_t> output;
  for (const auto& block : blocks) output.insert(output.end(), block.begin(), block.end());
  return output;
}

std::vector<int> interleaved_to_concatenated_positions(std::size_t data_length, EccLevel level) {
  const EccProfile p = profile(level);
  const auto lengths = block_data_lengths(data_length, level);
  std::vector<std::size_t> offsets;
  std::size_t offset = 0;
  std::size_t max_length = 0;
  for (int length : lengths) {
    offsets.push_back(offset);
    const std::size_t block_length = static_cast<std::size_t>(length + p.parity_bytes);
    max_length = std::max(max_length, block_length);
    offset += block_length;
  }
  std::vector<int> result;
  result.reserve(data_length + lengths.size() * static_cast<std::size_t>(p.parity_bytes));
  for (std::size_t column = 0; column < max_length; ++column) for (std::size_t block = 0; block < lengths.size(); ++block) {
    const std::size_t block_length = static_cast<std::size_t>(lengths[block] + p.parity_bytes);
    if (column < block_length) result.push_back(static_cast<int>(offsets[block] + column));
  }
  return result;
}

struct XorShift32 {
 public:
  explicit XorShift32(std::uint32_t seed) : state_(seed == 0 ? 0x6D2B79F5U : seed) {}
  std::uint32_t next() {
    std::uint32_t value = state_;
    value ^= value << 13U;
    value ^= value >> 17U;
    value ^= value << 5U;
    state_ = value;
    return state_;
  }
  int randbelow(int upper) {
    if (upper <= 0) throw std::invalid_argument("upper must be positive");
    const std::uint64_t limit = (std::uint64_t{1} << 32U) - ((std::uint64_t{1} << 32U) % static_cast<std::uint64_t>(upper));
    while (true) {
      const std::uint32_t value = next();
      if (static_cast<std::uint64_t>(value) < limit) return static_cast<int>(value % static_cast<std::uint32_t>(upper));
    }
  }
 private:
  std::uint32_t state_;
};

struct CellAddress {
  int ring;
  int sector;
  bool operator<(const CellAddress& other) const { return ring != other.ring ? ring < other.ring : sector < other.sector; }
  bool operator==(const CellAddress& other) const { return ring == other.ring && sector == other.sector; }
};

struct Cell {
  CellAddress address;
  double r_inner;
  double r_outer;
  double theta_start;
  double theta_end;
  double theta_center;
};

struct Geometry {
  int version;
  int data_rings;
  int format_version;
  double data_inner;
  double radial_pitch;
  std::vector<int> sector_counts;
  std::vector<Cell> cells;
  std::map<CellAddress, int> index_by_address;
};

int data_rings_for(int version) {
  switch (version) {
    case 0: return 2;
    case 1: return 12;
    case 2: return 18;
    case 3: return 24;
    case 4: return 30;
    case 5: return 4;
    case 6: return 1;
    default: throw std::invalid_argument("unsupported geometry version");
  }
}

int column_count_for(int version) {
  switch (version) {
    case 0: return 216;
    case 1: return 160;
    case 2: return 168;
    case 3: return 168;
    case 4: return 168;
    case 5: return 188;
    case 6: return 266;
    default: throw std::invalid_argument("unsupported geometry version");
  }
}

bool geometry_allowed(int geometry_version, int format_version) {
  if (format_version <= 3) return geometry_version >= 1 && geometry_version <= 4;
  return geometry_version >= 0 && geometry_version <= 6;
}

Geometry make_geometry(int version, int format_version) {
  if (!geometry_allowed(version, format_version)) throw std::invalid_argument("geometry is not registered for this format");
  Geometry geometry;
  geometry.version = version;
  geometry.format_version = format_version;
  geometry.data_rings = data_rings_for(version);
  const bool constant = format_version >= 3;
  geometry.data_inner = constant ? kConstantDataInner : kLegacyDataInner;
  geometry.radial_pitch = (kDataOuter - geometry.data_inner) / geometry.data_rings;
  for (int ring = 0; ring < geometry.data_rings; ++ring) {
    const double radius = geometry.data_inner + (ring + 0.5) * geometry.radial_pitch;
    const double ideal = kTau * radius / geometry.radial_pitch;
    geometry.sector_counts.push_back(constant ? column_count_for(version) : round_to_multiple(ideal, kRoundSectorMultiple));
  }
  for (int ring = 0; ring < geometry.data_rings; ++ring) {
    const int sectors = geometry.sector_counts[static_cast<std::size_t>(ring)];
    const double r_inner = geometry.data_inner + ring * geometry.radial_pitch;
    const double r_outer = r_inner + geometry.radial_pitch;
    const double cell_angle = kTau / sectors;
    const double offset = constant ? 0.0 : ((ring * 3) % 8) / 8.0 * cell_angle;
    for (int sector = 0; sector < sectors; ++sector) {
      const double theta_start = std::fmod(offset + sector * cell_angle, kTau);
      geometry.index_by_address[{ring, sector}] = static_cast<int>(geometry.cells.size());
      geometry.cells.push_back({{ring, sector}, r_inner, r_outer, theta_start, theta_start + cell_angle, theta_start + cell_angle / 2.0});
    }
  }
  return geometry;
}

std::set<CellAddress> calibration_addresses(const Geometry& geometry, Alphabet alphabet) {
  std::set<CellAddress> result;
  if (alphabet == Alphabet::Mono2) return result;
  const int states = 1 << bits_per_cell(alphabet);
  const std::array<int, 4> candidates = {0, std::max(0, geometry.data_rings / 3), std::max(0, 2 * geometry.data_rings / 3), geometry.data_rings - 1};
  for (int repetition = 0; repetition < kColorReferenceRepetitions; ++repetition) {
    const int ring = candidates[static_cast<std::size_t>(repetition)];
    const int sectors = geometry.sector_counts[static_cast<std::size_t>(ring)];
    const int base = static_cast<int>(python_round((static_cast<double>(repetition) / kColorReferenceRepetitions) * sectors)) % sectors;
    for (int state = 0; state < states; ++state) result.insert({ring, (base + state) % sectors});
  }
  return result;
}

std::set<CellAddress> reserved_addresses(const Geometry& geometry) {
  std::set<CellAddress> result;
  for (int index = 0; index < kDataReservedCells; ++index) {
    const int total = static_cast<int>(geometry.cells.size());
    const int flat = std::min(total - 1, static_cast<int>((index + 0.5) * total / kDataReservedCells));
    result.insert(geometry.cells[static_cast<std::size_t>(flat)].address);
  }
  if (static_cast<int>(result.size()) != kDataReservedCells) throw std::runtime_error("reserved address selection is not unique");
  return result;
}

std::vector<CellAddress> payload_addresses(const Geometry& geometry, Alphabet alphabet) {
  const auto reserved = reserved_addresses(geometry);
  const auto calibration = calibration_addresses(geometry, alphabet);
  std::vector<CellAddress> result;
  for (const Cell& cell : geometry.cells) if (!reserved.count(cell.address) && !calibration.count(cell.address)) result.push_back(cell.address);
  return result;
}

std::uint32_t permutation_seed(int geometry_version, Alphabet alphabet, int ecc_level, int frame_length, int format_version) {
  std::uint32_t seed = 0x52414449U;
  seed ^= (static_cast<std::uint32_t>(geometry_version) & 0xFFU) << 24U;
  seed ^= (static_cast<std::uint32_t>(alphabet) & 0x0FU) << 20U;
  seed ^= (static_cast<std::uint32_t>(ecc_level) & 0x0FU) << 16U;
  seed ^= static_cast<std::uint32_t>(frame_length) & 0xFFFFU;
  if (format_version >= 3) seed ^= (static_cast<std::uint32_t>(format_version) & 0x0FU) << 12U;
  return seed;
}

std::vector<int> spatial_permutation(int length, std::uint32_t seed) {
  std::vector<int> result(static_cast<std::size_t>(length));
  std::iota(result.begin(), result.end(), 0);
  XorShift32 rng(seed);
  for (int index = length - 1; index > 0; --index) {
    const int swap = rng.randbelow(index + 1);
    std::swap(result[static_cast<std::size_t>(index)], result[static_cast<std::size_t>(swap)]);
  }
  return result;
}

int mask_value(int mask_id, const CellAddress& address, int bits) {
  int output = 0;
  for (int plane = 0; plane < bits; ++plane) {
    int bit = 0;
    if (mask_id == 0) bit = (address.ring + address.sector + plane) & 1;
    else if (mask_id == 1) bit = (address.ring + plane) & 1;
    else if (mask_id == 2) bit = ((address.sector + plane) % 3 == 0) ? 1 : 0;
    else if (mask_id == 3) bit = ((address.ring + address.sector + plane) % 3 == 0) ? 1 : 0;
    else if (mask_id == 4) bit = ((address.ring / 2 + address.sector / 3 + plane) & 1);
    else if (mask_id == 5) {
      const int product = (address.ring + 1) * (address.sector + 1 + plane);
      bit = ((product % 2) + (product % 3) == 0) ? 1 : 0;
    } else if (mask_id == 6) {
      const int product = (address.ring + 1) * (address.sector + 1 + plane);
      bit = ((product % 2) + (product % 3)) & 1;
    } else {
      const int product = (address.ring + 1) * (address.sector + 1 + plane);
      bit = (((address.ring + address.sector + plane) % 2) + (product % 3)) & 1;
    }
    output = (output << 1) | bit;
  }
  return output;
}

std::vector<int> bytes_to_bits(const std::vector<std::uint8_t>& bytes) {
  std::vector<int> bits;
  bits.reserve(bytes.size() * 8U);
  for (std::uint8_t byte : bytes) for (int shift = 7; shift >= 0; --shift) bits.push_back((byte >> shift) & 1U);
  return bits;
}

std::vector<int> bits_to_symbols(const std::vector<int>& bits, int bits_per_cell_value) {
  std::vector<int> symbols;
  for (std::size_t offset = 0; offset < bits.size(); offset += static_cast<std::size_t>(bits_per_cell_value)) {
    int value = 0;
    for (int index = 0; index < bits_per_cell_value; ++index) {
      value <<= 1;
      const std::size_t position = offset + static_cast<std::size_t>(index);
      if (position < bits.size()) value |= bits[position];
    }
    symbols.push_back(value);
  }
  return symbols;
}

std::vector<std::uint8_t> symbols_to_bytes(const std::vector<int>& symbols, int bits_per_cell_value, std::size_t byte_length) {
  std::vector<int> bits;
  bits.reserve(symbols.size() * static_cast<std::size_t>(bits_per_cell_value));
  for (int symbol : symbols) for (int shift = bits_per_cell_value - 1; shift >= 0; --shift) bits.push_back((symbol >> shift) & 1);
  std::vector<std::uint8_t> bytes;
  bytes.reserve(byte_length);
  for (std::size_t offset = 0; offset < byte_length * 8U; offset += 8U) {
    int value = 0;
    for (int index = 0; index < 8; ++index) value = (value << 1) | bits[offset + static_cast<std::size_t>(index)];
    bytes.push_back(static_cast<std::uint8_t>(value));
  }
  return bytes;
}

struct MaskScore {
  double total;
  int id;
};

std::vector<int> encode_channel(const std::vector<std::uint8_t>& encoded_bytes, const Geometry& geometry, Alphabet alphabet, int ecc_level, int frame_length, int* selected_mask) {
  const auto addresses = payload_addresses(geometry, alphabet);
  const int bits = bits_per_cell(alphabet);
  const int states = 1 << bits;
  const auto data_symbols = bits_to_symbols(bytes_to_bits(encoded_bytes), bits);
  if (data_symbols.size() > addresses.size()) throw std::runtime_error("encoded payload exceeds geometry capacity");
  const std::uint32_t seed = permutation_seed(geometry.version, alphabet, ecc_level, frame_length, geometry.format_version);
  XorShift32 padding_rng(seed ^ 0xA5C31E27U);
  std::vector<int> padded = data_symbols;
  while (padded.size() < addresses.size()) padded.push_back(padding_rng.randbelow(states));
  const auto permutation = spatial_permutation(static_cast<int>(addresses.size()), seed);
  std::vector<int> physical(addresses.size(), 0);
  for (std::size_t logical = 0; logical < padded.size(); ++logical) physical[static_cast<std::size_t>(permutation[logical])] = padded[logical];

  std::vector<MaskScore> scores;
  for (int mask = 0; mask < 8; ++mask) {
    std::vector<int> masked(addresses.size(), 0);
    for (std::size_t index = 0; index < addresses.size(); ++index) masked[index] = physical[index] ^ mask_value(mask, addresses[index], bits);
    std::vector<int> counts(static_cast<std::size_t>(states), 0);
    for (int value : masked) ++counts[static_cast<std::size_t>(value)];
    const double target = static_cast<double>(masked.size()) / states;
    double imbalance = 0.0;
    for (int count : counts) imbalance += std::abs(count - target);
    imbalance /= std::max(1.0, static_cast<double>(masked.size()));
    double angular_runs = 0.0;
    for (int ring = 0; ring < geometry.data_rings; ++ring) {
      std::vector<std::pair<int, int>> ring_values;
      for (std::size_t index = 0; index < addresses.size(); ++index) if (addresses[index].ring == ring) ring_values.emplace_back(addresses[index].sector, masked[index]);
      std::sort(ring_values.begin(), ring_values.end());
      if (ring_values.empty()) continue;
      int run = 1;
      for (std::size_t index = 1; index < ring_values.size(); ++index) {
        if (ring_values[index].second == ring_values[index - 1].second) ++run;
        else {
          if (run >= 5) angular_runs += static_cast<double>((run - 4) * (run - 4));
          run = 1;
        }
      }
      if (run >= 5) angular_runs += static_cast<double>((run - 4) * (run - 4));
    }
    double radial_repetition = 0.0;
    std::map<CellAddress, int> symbol_by_address;
    for (std::size_t index = 0; index < addresses.size(); ++index) symbol_by_address[addresses[index]] = masked[index];
    for (std::size_t index = 0; index < addresses.size(); ++index) {
      const auto address = addresses[index];
      if (address.ring == 0) continue;
      const int inner_sectors = geometry.sector_counts[static_cast<std::size_t>(address.ring - 1)];
      const auto cell_index = geometry.index_by_address.find(address);
      if (cell_index == geometry.index_by_address.end()) continue;
      const double theta = geometry.cells[static_cast<std::size_t>(cell_index->second)].theta_center;
      const int nearest = static_cast<int>(python_round(theta / kTau * inner_sectors)) % inner_sectors;
      const auto neighbor = symbol_by_address.find({address.ring - 1, nearest});
      if (neighbor != symbol_by_address.end() && neighbor->second == masked[index]) radial_repetition += 1.0;
    }
    const double normalized_runs = angular_runs / std::max(1.0, static_cast<double>(masked.size()));
    const double normalized_radial = radial_repetition / std::max(1.0, static_cast<double>(masked.size()));
    scores.push_back({100.0 * imbalance + 20.0 * normalized_runs + 5.0 * normalized_radial, mask});
  }
  const auto best = std::min_element(scores.begin(), scores.end(), [](const MaskScore& left, const MaskScore& right) { return left.total != right.total ? left.total < right.total : left.id < right.id; });
  *selected_mask = best->id;
  std::vector<int> output(addresses.size(), 0);
  for (std::size_t index = 0; index < addresses.size(); ++index) output[index] = physical[index] ^ mask_value(best->id, addresses[index], bits);
  return output;
}

std::vector<std::uint8_t> decode_channel(const std::vector<int>& physical_symbols, const Geometry& geometry, Alphabet alphabet, int ecc_level, int frame_length, int mask_id, std::size_t encoded_byte_length) {
  const auto addresses = payload_addresses(geometry, alphabet);
  if (physical_symbols.size() != addresses.size()) throw std::runtime_error("physical symbol count does not match geometry");
  const int bits = bits_per_cell(alphabet);
  std::vector<int> unmasked(addresses.size(), 0);
  for (std::size_t index = 0; index < addresses.size(); ++index) unmasked[index] = physical_symbols[index] ^ mask_value(mask_id, addresses[index], bits);
  const auto permutation = spatial_permutation(static_cast<int>(addresses.size()), permutation_seed(geometry.version, alphabet, ecc_level, frame_length, geometry.format_version));
  std::vector<int> logical(addresses.size(), 0);
  for (std::size_t logical_index = 0; logical_index < permutation.size(); ++logical_index) logical[logical_index] = unmasked[static_cast<std::size_t>(permutation[logical_index])];
  const std::size_t required_symbols = (encoded_byte_length * 8U + static_cast<std::size_t>(bits) - 1U) / static_cast<std::size_t>(bits);
  logical.resize(required_symbols);
  return symbols_to_bytes(logical, bits, encoded_byte_length);
}

std::uint64_t pack_header_data(const Header& header) {
  const std::array<std::pair<std::uint64_t, int>, 10> fields = {{{kFormatMagic, 8}, {static_cast<std::uint64_t>(header.format_version), 3}, {static_cast<std::uint64_t>(header.geometry_version), 3}, {static_cast<std::uint64_t>(header.alphabet), 2}, {static_cast<std::uint64_t>(header.palette_id), 3}, {0, 2}, {static_cast<std::uint64_t>(header.ecc_level), 2}, {static_cast<std::uint64_t>(header.mask_id), 3}, {static_cast<std::uint64_t>(header.encoded_payload_length), 16}, {0, 3}}};
  std::uint64_t value = 0;
  int width = 0;
  for (const auto& [field, bits] : fields) {
    if (field >= (std::uint64_t{1} << bits)) throw std::invalid_argument("header field does not fit");
    value = (value << bits) | field;
    width += bits;
  }
  if (width != kBchK) throw std::runtime_error("header width mismatch");
  return value;
}

Header decode_header(std::uint64_t codeword) {
  int corrected = 0;
  const std::uint64_t value = bch_decode(codeword, &corrected);
  const int widths[10] = {3, 16, 3, 2, 2, 3, 2, 3, 3, 8};
  std::uint64_t remaining = value;
  std::array<std::uint64_t, 10> fields{};
  for (int index = 0; index < 10; ++index) {
    const int bits = widths[index];
    fields[static_cast<std::size_t>(index)] = remaining & ((std::uint64_t{1} << bits) - 1U);
    remaining >>= bits;
  }
  if (remaining != 0 || fields[9] != kFormatMagic) throw std::runtime_error("invalid RadialCode header");
  Header header;
  header.format_version = static_cast<int>(fields[8]);
  header.geometry_version = static_cast<int>(fields[7]);
  header.alphabet = static_cast<Alphabet>(fields[6]);
  header.palette_id = static_cast<int>(fields[5]);
  if (fields[4] != 0) throw std::runtime_error("unsupported ECC scheme");
  header.ecc_level = static_cast<EccLevel>(fields[3]);
  header.mask_id = static_cast<int>(fields[2]);
  header.encoded_payload_length = static_cast<int>(fields[1]);
  if (fields[0] != 0 || header.format_version < 1 || header.format_version > 5 || header.mask_id > 7 || (header.alphabet == Alphabet::Color4 && header.palette_id > 3) || !geometry_allowed(header.geometry_version, header.format_version)) throw std::runtime_error("invalid RadialCode header fields");
  header.data = value;
  header.codeword = codeword;
  return header;
}

std::vector<int> unpack_symbols(const std::string& packed_hex, int count, int bits) {
  const auto bytes = hex_to_bytes(packed_hex);
  std::vector<int> symbols;
  symbols.reserve(static_cast<std::size_t>(count));
  for (std::uint8_t byte : bytes) {
    for (int shift = 8 - bits; shift >= 0 && static_cast<int>(symbols.size()) < count; shift -= bits) symbols.push_back((byte >> shift) & ((1 << bits) - 1));
  }
  if (static_cast<int>(symbols.size()) != count) throw std::runtime_error("packed channel symbol length mismatch");
  return symbols;
}

GeometryModel export_geometry(const Geometry& geometry, Alphabet alphabet, const std::vector<int>* channel_symbols) {
  const auto addresses = payload_addresses(geometry, alphabet);
  std::map<CellAddress, int> states;
  if (channel_symbols != nullptr) {
    if (channel_symbols->size() != addresses.size()) throw std::runtime_error("channel/model size mismatch");
    for (std::size_t index = 0; index < addresses.size(); ++index) states[addresses[index]] = (*channel_symbols)[index];
  }
  const int state_count = 1 << bits_per_cell(alphabet);
  const std::array<int, 4> candidates = {0, std::max(0, geometry.data_rings / 3), std::max(0, 2 * geometry.data_rings / 3), geometry.data_rings - 1};
  for (int repetition = 0; repetition < kColorReferenceRepetitions; ++repetition) {
    const int ring = candidates[static_cast<std::size_t>(repetition)];
    const int sectors = geometry.sector_counts[static_cast<std::size_t>(ring)];
    const int base = static_cast<int>(python_round((static_cast<double>(repetition) / kColorReferenceRepetitions) * sectors)) % sectors;
    for (int state = 0; state < state_count; ++state) states[{ring, (base + state) % sectors}] = state;
  }
  const auto reserved = reserved_addresses(geometry);
  for (const auto& address : reserved) states[address] = (address.ring * 5 + address.sector * 3 + 1) % state_count;

  GeometryModel output;
  output.version = geometry.version;
  output.format_version = geometry.format_version;
  output.data_rings = geometry.data_rings;
  output.data_inner = geometry.data_inner;
  output.radial_pitch = geometry.radial_pitch;
  output.sector_counts = geometry.sector_counts;
  output.cells.reserve(geometry.cells.size());
  for (const auto& cell : geometry.cells) {
    RenderCell rendered;
    rendered.ring = cell.address.ring;
    rendered.sector = cell.address.sector;
    rendered.r_inner = cell.r_inner;
    rendered.r_outer = cell.r_outer;
    rendered.theta_start = cell.theta_start;
    rendered.theta_end = cell.theta_end;
    rendered.state = states.count(cell.address) ? states[cell.address] : 0;
    rendered.payload = std::find(addresses.begin(), addresses.end(), cell.address) != addresses.end();
    output.cells.push_back(rendered);
  }
  return output;
}

}  // namespace

std::vector<std::uint8_t> hex_to_bytes(const std::string& hex) {
  if (hex.size() % 2 != 0) throw std::invalid_argument("hex string must have even length");
  std::vector<std::uint8_t> bytes;
  bytes.reserve(hex.size() / 2U);
  auto nibble = [](char value) -> int {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    return -1;
  };
  for (std::size_t index = 0; index < hex.size(); index += 2) {
    const int high = nibble(hex[index]);
    const int low = nibble(hex[index + 1]);
    if (high < 0 || low < 0) throw std::invalid_argument("invalid hexadecimal string");
    bytes.push_back(static_cast<std::uint8_t>((high << 4) | low));
  }
  return bytes;
}

std::string bytes_to_hex(const std::vector<std::uint8_t>& bytes) {
  std::ostringstream stream;
  stream << std::hex << std::setfill('0');
  for (std::uint8_t byte : bytes) stream << std::setw(2) << static_cast<int>(byte);
  return stream.str();
}

std::string uint_to_hex(std::uint64_t value, int width_bytes) {
  std::ostringstream stream;
  stream << std::hex << std::setfill('0') << std::setw(width_bytes * 2) << value;
  return stream.str();
}

EncodedSymbol encode(const std::vector<std::uint8_t>& payload, const EncodeOptions& options) {
  if (options.format_version < 1 || options.format_version > 5) throw std::invalid_argument("unsupported format version");
  if (!geometry_allowed(options.geometry_version, options.format_version)) throw std::invalid_argument("geometry is not registered for this format");
  if (options.alphabet != Alphabet::Mono2 && options.alphabet != Alphabet::Color4) throw std::invalid_argument("unsupported alphabet");
  if (options.palette_id < 0 || options.palette_id > 3) throw std::invalid_argument("unsupported palette");
  const FrameData frame = encode_frame(payload, options.payload_type, options.compression);
  const auto concatenated = rs_encode(frame.encoded, options.ecc_level);
  const auto interleaved = interleave(concatenated, frame.encoded.size(), options.ecc_level);
  const Geometry geometry = make_geometry(options.geometry_version, options.format_version);
  int mask_id = 0;
  const auto channel = encode_channel(interleaved, geometry, options.alphabet, static_cast<int>(options.ecc_level), static_cast<int>(frame.encoded.size()), &mask_id);
  Header header;
  header.format_version = options.format_version;
  header.geometry_version = options.geometry_version;
  header.alphabet = options.alphabet;
  header.palette_id = options.palette_id;
  header.ecc_level = options.ecc_level;
  header.mask_id = mask_id;
  header.encoded_payload_length = static_cast<int>(frame.encoded.size());
  header.data = pack_header_data(header);
  header.codeword = bch_encode(header.data);
  const int bits = bits_per_cell(options.alphabet);
  std::vector<int> packed_bits;
  for (int symbol : channel) for (int shift = bits - 1; shift >= 0; --shift) packed_bits.push_back((symbol >> shift) & 1);
  std::vector<std::uint8_t> packed((packed_bits.size() + 7U) / 8U, 0);
  for (std::size_t index = 0; index < packed_bits.size(); ++index) packed[index / 8U] |= static_cast<std::uint8_t>(packed_bits[index] << (7U - (index % 8U)));
  std::vector<std::uint8_t> channel_bytes;
  channel_bytes.reserve(channel.size());
  for (int symbol : channel) channel_bytes.push_back(static_cast<std::uint8_t>(symbol));
  EncodedSymbol result;
  result.payload = payload;
  result.payload_type = options.payload_type;
  result.frame = frame.encoded;
  result.rs_concatenated = concatenated;
  result.rs_interleaved = interleaved;
  result.channel_symbols = std::move(channel_bytes);
  result.channel_symbols_packed_hex = bytes_to_hex(packed);
  result.header = header;
  result.geometry = export_geometry(geometry, options.alphabet, &channel);
  result.cells = result.geometry.cells;
  return result;
}

DecodedSymbol decode(const std::vector<std::uint8_t>& packed_channel, int channel_symbol_count, std::uint64_t header_codeword) {
  const Header header = decode_header(header_codeword);
  const int bits = bits_per_cell(header.alphabet);
  const auto packed_hex = bytes_to_hex(packed_channel);
  const auto physical = unpack_symbols(packed_hex, channel_symbol_count, bits);
  const Geometry geometry = make_geometry(header.geometry_version, header.format_version);
  const std::size_t rs_length = static_cast<std::size_t>(encoded_length(static_cast<std::size_t>(header.encoded_payload_length), header.ecc_level));
  const auto interleaved_bytes = decode_channel(physical, geometry, header.alphabet, static_cast<int>(header.ecc_level), header.encoded_payload_length, header.mask_id, rs_length);
  const auto concatenated = deinterleave(interleaved_bytes, static_cast<std::size_t>(header.encoded_payload_length), header.ecc_level);
  int corrected = 0;
  const auto frame_bytes = rs_decode(concatenated, static_cast<std::size_t>(header.encoded_payload_length), header.ecc_level, &corrected);
  const FrameData frame = decode_frame(frame_bytes);
  return {frame.payload, frame.payload_type, frame.encoded, header, corrected};
}

DecodedSymbol decode_with_erasures(const std::vector<std::uint8_t>& packed_channel, int channel_symbol_count, std::uint64_t header_codeword, const std::vector<int>& erasure_cells) {
  const Header header = decode_header(header_codeword);
  const int bits = bits_per_cell(header.alphabet);
  const auto packed_hex = bytes_to_hex(packed_channel);
  const auto physical = unpack_symbols(packed_hex, channel_symbol_count, bits);
  const Geometry geometry = make_geometry(header.geometry_version, header.format_version);
  const std::size_t rs_length = static_cast<std::size_t>(encoded_length(static_cast<std::size_t>(header.encoded_payload_length), header.ecc_level));
  const auto interleaved_bytes = decode_channel(physical, geometry, header.alphabet, static_cast<int>(header.ecc_level), header.encoded_payload_length, header.mask_id, rs_length);
  const auto concatenated = deinterleave(interleaved_bytes, static_cast<std::size_t>(header.encoded_payload_length), header.ecc_level);
  const auto position_map = interleaved_to_concatenated_positions(static_cast<std::size_t>(header.encoded_payload_length), header.ecc_level);
  const auto permutation = spatial_permutation(channel_symbol_count, permutation_seed(header.geometry_version, header.alphabet, static_cast<int>(header.ecc_level), header.encoded_payload_length, header.format_version));
  std::vector<int> rs_positions;
  for (int cell : erasure_cells) {
    if (cell < 0 || cell >= static_cast<int>(permutation.size())) continue;
    const auto logical_it = std::find(permutation.begin(), permutation.end(), cell);
    if (logical_it == permutation.end()) continue;
    const int logical_index = static_cast<int>(std::distance(permutation.begin(), logical_it));
    const int first_bit = logical_index * bits;
    const int last_bit = first_bit + bits - 1;
    for (int logical_bit = first_bit; logical_bit <= last_bit; ++logical_bit) {
      const int byte_index = logical_bit / 8;
      if (byte_index >= 0 && byte_index < static_cast<int>(position_map.size())) rs_positions.push_back(position_map[static_cast<std::size_t>(byte_index)]);
    }
  }
  std::sort(rs_positions.begin(), rs_positions.end());
  rs_positions.erase(std::unique(rs_positions.begin(), rs_positions.end()), rs_positions.end());
  int corrected = 0;
  const auto frame_bytes = rs_decode_with_erasures(concatenated, static_cast<std::size_t>(header.encoded_payload_length), header.ecc_level, rs_positions, &corrected);
  const FrameData frame = decode_frame(frame_bytes);
  return {frame.payload, frame.payload_type, frame.encoded, header, corrected};
}

GeometryModel geometry_model(int geometry_version, int format_version, Alphabet alphabet) {
  return export_geometry(make_geometry(geometry_version, format_version), alphabet, nullptr);
}

Header decode_header_codeword(std::uint64_t codeword, int* corrected_bits) {
  int corrected = 0;
  Header header = decode_header(codeword);
  // decode_header already performs correction internally; recalculate the
  // correction count only for diagnostics when requested.
  if (corrected_bits != nullptr) {
    (void)bch_decode(codeword, &corrected);
    *corrected_bits = corrected;
  }
  return header;
}

std::vector<int> header_physical_bits(const Header& header, int copy_index) {
  if (copy_index < 0 || copy_index >= 4) throw std::invalid_argument("copy index must be between 0 and 3");
  std::vector<int> bits(kHeaderPhysicalSlots, 0);
  const int reserved = kHeaderSlotOffsets[copy_index];
  bits[static_cast<std::size_t>(reserved)] = kHeaderReservedBits[copy_index];
  for (int index = 0; index < kHeaderCodeBits; ++index) {
    const int shift = kHeaderCodeBits - 1 - index;
    bits[static_cast<std::size_t>((reserved + 1 + index) % kHeaderPhysicalSlots)] = static_cast<int>((header.codeword >> shift) & 1U);
  }
  return bits;
}

std::vector<int> clock_track_bits() {
  constexpr int order = 6;
  constexpr int tap_mask = 0b100001;
  int state = 0b111111;
  std::vector<int> bits{1};
  for (int index = 0; index < 63; ++index) {
    bits.push_back((state >> (order - 1)) & 1);
    int feedback = 0;
    int tapped = state & tap_mask;
    while (tapped != 0) {
      feedback ^= tapped & 1;
      tapped >>= 1;
    }
    state = ((state << 1) & 0x3F) | feedback;
  }
  return bits;
}

}  // namespace orbiqo::codec
