#include "orbiqo_codec.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <csetjmp>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <numeric>
#include <vector>

#include <png.h>
#include <jpeglib.h>
#include <webp/decode.h>
#include <zlib.h>
#include <ft2build.h>
#include FT_FREETYPE_H

namespace {

constexpr double kTau = 6.283185307179586476925286766559;
constexpr double kSvgR = 500.0;
constexpr double kQuietZoneOuter = 1.05;
constexpr double kSvgCanvas = 2.0 * kQuietZoneOuter * kSvgR;
constexpr double kSvgCenter = kSvgCanvas / 2.0;
constexpr double kLogoRadius = 0.20;
constexpr double kClockInner = 0.22;
constexpr double kClockOuter = 0.255;
constexpr double kHeaderRings[3][2] = {{0.26, 0.28}, {0.285, 0.305}, {0.31, 0.33}};
constexpr double kOuterHeaderRing[2] = {0.345, 0.365};
constexpr double kGuardInner = 0.93;
constexpr double kGuardOuter = 0.97;
constexpr double kAnchorInner = 0.93;
constexpr double kAnchorOuter = 0.97;
constexpr int kHeaderSlots = 64;
constexpr int kClockSlots = 64;
constexpr int kHeaderSlotOffsets[4] = {0, 17, 43, 29};
constexpr int kAnchorSlots[4] = {0, 19, 46, 81};
constexpr int kAnchorWidths[4] = {3, 5, 7, 9};

struct Pixel {
  std::uint8_t r = 255;
  std::uint8_t g = 255;
  std::uint8_t b = 255;
  std::uint8_t a = 255;
};

struct Image {
  int width = 0;
  int height = 0;
  std::vector<Pixel> pixels;

  Image() = default;
  Image(int w, int h, Pixel fill = {}) : width(w), height(h), pixels(static_cast<std::size_t>(w) * h, fill) {
    if (w <= 0 || h <= 0) throw std::invalid_argument("image dimensions must be positive");
  }

  Pixel& at(int x, int y) { return pixels[static_cast<std::size_t>(y) * width + x]; }
  const Pixel& at(int x, int y) const { return pixels[static_cast<std::size_t>(y) * width + x]; }

  void set(int x, int y, Pixel value) {
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    at(x, y) = value;
  }
};

struct RenderConfig {
  int dpi = 600;
  double diameter_mm = 0.0;
  double radial_fill = 0.80;
  double angular_fill = 0.82;
  Pixel background{255, 255, 255, 255};
  std::string center_text;
  std::vector<std::uint8_t> center_image;
};

struct NativeRequest {
  std::string op;
  std::vector<std::uint8_t> payload;
  int geometry = -1;
  int format = 5;
  orbiqo::codec::Alphabet alphabet = orbiqo::codec::Alphabet::Color4;
  orbiqo::codec::PayloadType payload_type = orbiqo::codec::PayloadType::Binary;
  orbiqo::codec::Compression compression = orbiqo::codec::Compression::Auto;
  orbiqo::codec::EccLevel ecc = orbiqo::codec::EccLevel::Balanced;
  int palette_id = 0;
  RenderConfig render;
  std::vector<std::uint8_t> image;
  bool canonical = false;
  int output_size = 1024;
  double erasure_threshold = 0.55;
};

Pixel rgb(int r, int g, int b) {
  if (r < 0 || r > 255 || g < 0 || g > 255 || b < 0 || b > 255) throw std::invalid_argument("RGB value out of range");
  return Pixel{static_cast<std::uint8_t>(r), static_cast<std::uint8_t>(g), static_cast<std::uint8_t>(b), 255};
}

Pixel parse_hex_color(const std::string& value) {
  if (value.size() != 7 || value[0] != '#') throw std::invalid_argument("background must be #RRGGBB");
  auto nibble = [](char c) -> int {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
  };
  int values[6]{};
  for (int i = 0; i < 6; ++i) {
    values[i] = nibble(value[static_cast<std::size_t>(i + 1)]);
    if (values[i] < 0) throw std::invalid_argument("invalid background color");
  }
  return rgb(values[0] * 16 + values[1], values[2] * 16 + values[3], values[4] * 16 + values[5]);
}

std::string xml_escape(const std::string& value) {
  std::string out;
  for (char c : value) {
    if (c == '&') out += "&amp;";
    else if (c == '<') out += "&lt;";
    else if (c == '>') out += "&gt;";
    else if (c == '"') out += "&quot;";
    else if (c == '\'') out += "&apos;";
    else out.push_back(c);
  }
  return out;
}

std::string base64_encode(const std::vector<std::uint8_t>& data) {
  static constexpr char table[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string out;
  out.reserve((data.size() + 2U) / 3U * 4U);
  for (std::size_t i = 0; i < data.size(); i += 3) {
    const std::uint32_t value = (static_cast<std::uint32_t>(data[i]) << 16U) |
        (i + 1 < data.size() ? static_cast<std::uint32_t>(data[i + 1]) << 8U : 0U) |
        (i + 2 < data.size() ? static_cast<std::uint32_t>(data[i + 2]) : 0U);
    out.push_back(table[(value >> 18U) & 63U]);
    out.push_back(table[(value >> 12U) & 63U]);
    out.push_back(i + 1 < data.size() ? table[(value >> 6U) & 63U] : '=');
    out.push_back(i + 2 < data.size() ? table[value & 63U] : '=');
  }
  return out;
}

std::vector<std::uint8_t> base64_decode(const std::string& value) {
  static const std::array<int, 256> lookup = [] {
    std::array<int, 256> out{};
    out.fill(-1);
    const std::string chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    for (int i = 0; i < static_cast<int>(chars.size()); ++i) out[static_cast<unsigned char>(chars[static_cast<std::size_t>(i)])] = i;
    return out;
  }();
  if (value.size() % 4 != 0) throw std::invalid_argument("invalid base64 length");
  std::vector<std::uint8_t> out;
  for (std::size_t i = 0; i < value.size(); i += 4) {
    int a = lookup[static_cast<unsigned char>(value[i])];
    int b = lookup[static_cast<unsigned char>(value[i + 1])];
    int c = value[i + 2] == '=' ? 0 : lookup[static_cast<unsigned char>(value[i + 2])];
    int d = value[i + 3] == '=' ? 0 : lookup[static_cast<unsigned char>(value[i + 3])];
    if (a < 0 || b < 0 || c < 0 || d < 0) throw std::invalid_argument("invalid base64 data");
    const std::uint32_t n = (static_cast<std::uint32_t>(a) << 18U) | (static_cast<std::uint32_t>(b) << 12U) | (static_cast<std::uint32_t>(c) << 6U) | static_cast<std::uint32_t>(d);
    out.push_back(static_cast<std::uint8_t>((n >> 16U) & 255U));
    if (value[i + 2] != '=') out.push_back(static_cast<std::uint8_t>((n >> 8U) & 255U));
    if (value[i + 3] != '=') out.push_back(static_cast<std::uint8_t>(n & 255U));
  }
  return out;
}

std::vector<std::uint8_t> hex_decode(const std::string& value) { return orbiqo::codec::hex_to_bytes(value); }

std::string geometry_name(int version) {
  switch (version) {
    case 0: return "micro-2";
    case 1: return "small";
    case 2: return "medium";
    case 3: return "large";
    case 4: return "xl";
    case 5: return "micro-4";
    case 6: return "micro-1";
    default: return "unknown";
  }
}

double recommended_diameter(int version) {
  switch (version) {
    case 0: return 16.0;
    case 1: return 30.0;
    case 2: return 40.0;
    case 3: return 50.0;
    case 4: return 70.0;
    case 5: return 18.0;
    case 6: return 16.0;
    default: return 30.0;
  }
}

int native_bits_per_cell(orbiqo::codec::Alphabet alphabet) {
  return alphabet == orbiqo::codec::Alphabet::Color4 ? 2 : 1;
}

int native_encoded_length(int data_length, orbiqo::codec::EccLevel level) {
  if (data_length <= 0) return 0;
  const int data_bytes = level == orbiqo::codec::EccLevel::Fast ? 223 : level == orbiqo::codec::EccLevel::Balanced ? 191 : level == orbiqo::codec::EccLevel::Robust ? 159 : 127;
  const int parity_bytes = level == orbiqo::codec::EccLevel::Fast ? 32 : level == orbiqo::codec::EccLevel::Balanced ? 64 : level == orbiqo::codec::EccLevel::Robust ? 96 : 128;
  const int blocks = (data_length + data_bytes - 1) / data_bytes;
  return data_length + blocks * parity_bytes;
}

int native_max_frame_bytes(int channel_bytes, orbiqo::codec::EccLevel level) {
  int maximum = 0;
  for (int length = 1; length <= channel_bytes; ++length) {
    if (native_encoded_length(length, level) <= channel_bytes) maximum = length;
  }
  return maximum;
}

int columns_for(const orbiqo::codec::GeometryModel& model) {
  return model.sector_counts.empty() ? 0 : model.sector_counts.front();
}

std::vector<Pixel> palette_for(orbiqo::codec::Alphabet alphabet, int palette_id) {
  if (alphabet == orbiqo::codec::Alphabet::Mono2) return {rgb(255, 255, 255), rgb(17, 17, 17)};
  static const int colors[4][4][3] = {
      {{17, 17, 17}, {0, 166, 214}, {216, 27, 96}, {240, 200, 8}},
      {{17, 17, 17}, {76, 201, 240}, {247, 37, 133}, {167, 201, 87}},
      {{17, 17, 17}, {42, 157, 143}, {231, 111, 81}, {255, 214, 10}},
      {{17, 17, 17}, {33, 158, 188}, {255, 77, 109}, {128, 237, 153}},
  };
  if (palette_id < 0 || palette_id > 3) throw std::invalid_argument("unsupported palette id");
  std::vector<Pixel> out;
  for (const auto& color : colors[palette_id]) out.push_back(rgb(color[0], color[1], color[2]));
  return out;
}

void blend(Image& image, int x, int y, Pixel source, double opacity = 1.0) {
  if (x < 0 || y < 0 || x >= image.width || y >= image.height || opacity <= 0.0) return;
  Pixel& target = image.at(x, y);
  const double alpha = std::clamp(opacity * static_cast<double>(source.a) / 255.0, 0.0, 1.0);
  target.r = static_cast<std::uint8_t>(std::round(target.r * (1.0 - alpha) + source.r * alpha));
  target.g = static_cast<std::uint8_t>(std::round(target.g * (1.0 - alpha) + source.g * alpha));
  target.b = static_cast<std::uint8_t>(std::round(target.b * (1.0 - alpha) + source.b * alpha));
  target.a = 255;
}

void draw_disc(Image& image, double cx, double cy, double radius, Pixel color) {
  const int min_x = static_cast<int>(std::floor(cx - radius));
  const int max_x = static_cast<int>(std::ceil(cx + radius));
  const int min_y = static_cast<int>(std::floor(cy - radius));
  const int max_y = static_cast<int>(std::ceil(cy + radius));
  const double rr = radius * radius;
  for (int y = min_y; y <= max_y; ++y) for (int x = min_x; x <= max_x; ++x) {
    const double dx = x + 0.5 - cx;
    const double dy = y + 0.5 - cy;
    if (dx * dx + dy * dy <= rr) image.set(x, y, color);
  }
}

void draw_ring(Image& image, double center, double radius, double width, Pixel color) {
  const int min_x = static_cast<int>(std::floor(center - radius - width));
  const int max_x = static_cast<int>(std::ceil(center + radius + width));
  const double inner = std::max(0.0, radius - width / 2.0);
  const double outer = radius + width / 2.0;
  const double inner_sq = inner * inner;
  const double outer_sq = outer * outer;
  for (int y = min_x; y <= max_x; ++y) for (int x = min_x; x <= max_x; ++x) {
    const double dx = x + 0.5 - center;
    const double dy = y + 0.5 - center;
    const double d = dx * dx + dy * dy;
    if (d >= inner_sq && d <= outer_sq) image.set(x, y, color);
  }
}

void draw_arc(Image& image, double center, double radius, double start, double end, double width, Pixel color, bool round_caps = false) {
  const int steps = std::max(2, static_cast<int>(std::ceil(std::abs(end - start) * radius / 1.2)));
  const double cap = std::max(0.5, width / 2.0);
  for (int i = 0; i <= steps; ++i) {
    const double theta = start + (end - start) * i / steps;
    draw_disc(image, center + radius * std::sin(theta), center - radius * std::cos(theta), cap, color);
  }
  if (!round_caps) {
    // The native primitive is intentionally conservative; the interior discs
    // reproduce the reference butt cap after supersample downsampling.
  }
}

Image downsample_box(const Image& source, int output_size, int factor) {
  Image out(output_size, output_size, Pixel{});
  const int samples = factor * factor;
  for (int y = 0; y < output_size; ++y) for (int x = 0; x < output_size; ++x) {
    int r = 0, g = 0, b = 0;
    for (int by = 0; by < factor; ++by) for (int bx = 0; bx < factor; ++bx) {
      const int sx = std::min(source.width - 1, x * factor + bx);
      const int sy = std::min(source.height - 1, y * factor + by);
      const Pixel p = source.at(sx, sy);
      r += p.r; g += p.g; b += p.b;
    }
    out.set(x, y, rgb(r / samples, g / samples, b / samples));
  }
  return out;
}

struct PngWriteBuffer { std::vector<std::uint8_t> bytes; };

void png_write_callback(png_structp png_ptr, png_bytep data, png_size_t length) {
  auto* buffer = static_cast<PngWriteBuffer*>(png_get_io_ptr(png_ptr));
  buffer->bytes.insert(buffer->bytes.end(), data, data + length);
}

void png_flush_callback(png_structp) {}

std::vector<std::uint8_t> write_png(const Image& image) {
  png_structp png = png_create_write_struct(PNG_LIBPNG_VER_STRING, nullptr, nullptr, nullptr);
  if (!png) throw std::runtime_error("PNG writer allocation failed");
  png_infop info = png_create_info_struct(png);
  if (!info) { png_destroy_write_struct(&png, nullptr); throw std::runtime_error("PNG info allocation failed"); }
  PngWriteBuffer buffer;
  if (setjmp(png_jmpbuf(png)) != 0) { png_destroy_write_struct(&png, &info); throw std::runtime_error("PNG writing failed"); }
  png_set_write_fn(png, &buffer, png_write_callback, png_flush_callback);
  png_set_IHDR(png, info, image.width, image.height, 8, PNG_COLOR_TYPE_RGB, PNG_INTERLACE_NONE, PNG_COMPRESSION_TYPE_BASE, PNG_FILTER_TYPE_BASE);
  png_write_info(png, info);
  std::vector<std::vector<std::uint8_t>> rows(static_cast<std::size_t>(image.height), std::vector<std::uint8_t>(static_cast<std::size_t>(image.width) * 3U));
  std::vector<png_bytep> row_ptrs(static_cast<std::size_t>(image.height));
  for (int y = 0; y < image.height; ++y) {
    for (int x = 0; x < image.width; ++x) {
      const Pixel p = image.at(x, y);
      rows[static_cast<std::size_t>(y)][static_cast<std::size_t>(x) * 3U] = p.r;
      rows[static_cast<std::size_t>(y)][static_cast<std::size_t>(x) * 3U + 1U] = p.g;
      rows[static_cast<std::size_t>(y)][static_cast<std::size_t>(x) * 3U + 2U] = p.b;
    }
    row_ptrs[static_cast<std::size_t>(y)] = rows[static_cast<std::size_t>(y)].data();
  }
  png_write_image(png, row_ptrs.data());
  png_write_end(png, info);
  png_destroy_write_struct(&png, &info);
  return buffer.bytes;
}

struct PngReadBuffer { const std::vector<std::uint8_t>* bytes; std::size_t offset = 0; };

void png_read_callback(png_structp png_ptr, png_bytep data, png_size_t length) {
  auto* buffer = static_cast<PngReadBuffer*>(png_get_io_ptr(png_ptr));
  if (buffer->offset + length > buffer->bytes->size()) png_error(png_ptr, "PNG input truncated");
  std::memcpy(data, buffer->bytes->data() + buffer->offset, length);
  buffer->offset += length;
}

Image read_png(const std::vector<std::uint8_t>& bytes) {
  if (bytes.size() < 8 || png_sig_cmp(const_cast<png_bytep>(bytes.data()), 0, 8) != 0) throw std::runtime_error("native decoder accepts PNG input");
  png_structp png = png_create_read_struct(PNG_LIBPNG_VER_STRING, nullptr, nullptr, nullptr);
  if (!png) throw std::runtime_error("PNG reader allocation failed");
  png_infop info = png_create_info_struct(png);
  if (!info) { png_destroy_read_struct(&png, nullptr, nullptr); throw std::runtime_error("PNG info allocation failed"); }
  PngReadBuffer source{&bytes};
  if (setjmp(png_jmpbuf(png)) != 0) { png_destroy_read_struct(&png, &info, nullptr); throw std::runtime_error("PNG reading failed"); }
  png_set_read_fn(png, &source, png_read_callback);
  png_read_info(png, info);
  png_uint_32 width = 0, height = 0;
  int bit_depth = 0, color_type = 0;
  png_get_IHDR(png, info, &width, &height, &bit_depth, &color_type, nullptr, nullptr, nullptr);
  if (bit_depth == 16) png_set_strip_16(png);
  if (color_type == PNG_COLOR_TYPE_PALETTE) png_set_palette_to_rgb(png);
  if (color_type == PNG_COLOR_TYPE_GRAY && bit_depth < 8) png_set_expand_gray_1_2_4_to_8(png);
  if (png_get_valid(png, info, PNG_INFO_tRNS)) png_set_tRNS_to_alpha(png);
  if (color_type == PNG_COLOR_TYPE_GRAY || color_type == PNG_COLOR_TYPE_GRAY_ALPHA) png_set_gray_to_rgb(png);
  if (color_type == PNG_COLOR_TYPE_RGB || color_type == PNG_COLOR_TYPE_GRAY) png_set_add_alpha(png, 0xFF, PNG_FILLER_AFTER);
  png_read_update_info(png, info);
  const int channels = png_get_channels(png, info);
  if (channels != 4 || width > 4096 || height > 4096 || width * height > 16000000U) {
    png_destroy_read_struct(&png, &info, nullptr);
    throw std::runtime_error("PNG dimensions or channels are unsupported");
  }
  Image image(static_cast<int>(width), static_cast<int>(height));
  std::vector<std::vector<std::uint8_t>> rows(static_cast<std::size_t>(height), std::vector<std::uint8_t>(png_get_rowbytes(png, info)));
  std::vector<png_bytep> row_ptrs(static_cast<std::size_t>(height));
  for (std::size_t y = 0; y < rows.size(); ++y) row_ptrs[y] = rows[y].data();
  png_read_image(png, row_ptrs.data());
  png_destroy_read_struct(&png, &info, nullptr);
  for (int y = 0; y < image.height; ++y) for (int x = 0; x < image.width; ++x) {
    const auto* p = &rows[static_cast<std::size_t>(y)][static_cast<std::size_t>(x) * 4U];
    image.at(x, y) = Pixel{p[0], p[1], p[2], p[3]};
  }
  return image;
}

struct JpegErrorManager {
  jpeg_error_mgr public_manager{};
  jmp_buf jump{};
  char message[JMSG_LENGTH_MAX]{};
};

void jpeg_error_exit(j_common_ptr info) {
  auto* manager = reinterpret_cast<JpegErrorManager*>(info->err);
  (*info->err->format_message)(info, manager->message);
  longjmp(manager->jump, 1);
}

Image read_jpeg(const std::vector<std::uint8_t>& bytes) {
  jpeg_decompress_struct decoder{};
  JpegErrorManager errors{};
  decoder.err = jpeg_std_error(&errors.public_manager);
  errors.public_manager.error_exit = jpeg_error_exit;
  if (setjmp(errors.jump) != 0) {
    jpeg_destroy_decompress(&decoder);
    throw std::runtime_error(std::string("JPEG reading failed: ") + errors.message);
  }
  jpeg_create_decompress(&decoder);
  jpeg_mem_src(&decoder, const_cast<unsigned char*>(bytes.data()), bytes.size());
  if (jpeg_read_header(&decoder, TRUE) != JPEG_HEADER_OK) {
    jpeg_destroy_decompress(&decoder);
    throw std::runtime_error("JPEG header is invalid");
  }
  decoder.out_color_space = JCS_RGB;
  jpeg_start_decompress(&decoder);
  if (decoder.output_width > 4096 || decoder.output_height > 4096 ||
      static_cast<std::uint64_t>(decoder.output_width) * decoder.output_height > 16000000U) {
    jpeg_destroy_decompress(&decoder);
    throw std::runtime_error("JPEG dimensions are unsupported");
  }
  Image image(static_cast<int>(decoder.output_width), static_cast<int>(decoder.output_height));
  std::vector<JSAMPLE> row(static_cast<std::size_t>(decoder.output_width) * 3U);
  while (decoder.output_scanline < decoder.output_height) {
    JSAMPROW row_pointer = row.data();
    jpeg_read_scanlines(&decoder, &row_pointer, 1);
    const int y = static_cast<int>(decoder.output_scanline - 1);
    for (int x = 0; x < image.width; ++x) {
      image.at(x, y) = Pixel{row[static_cast<std::size_t>(x) * 3U], row[static_cast<std::size_t>(x) * 3U + 1U], row[static_cast<std::size_t>(x) * 3U + 2U], 255};
    }
  }
  jpeg_finish_decompress(&decoder);
  jpeg_destroy_decompress(&decoder);
  return image;
}

Image read_webp(const std::vector<std::uint8_t>& bytes) {
  int width = 0;
  int height = 0;
  if (!WebPGetInfo(bytes.data(), bytes.size(), &width, &height) || width <= 0 || height <= 0 ||
      width > 4096 || height > 4096 || static_cast<std::uint64_t>(width) * height > 16000000U) {
    throw std::runtime_error("WebP header or dimensions are unsupported");
  }
  int decoded_width = 0;
  int decoded_height = 0;
  uint8_t* rgba = WebPDecodeRGBA(bytes.data(), bytes.size(), &decoded_width, &decoded_height);
  if (rgba == nullptr || decoded_width != width || decoded_height != height) {
    if (rgba != nullptr) WebPFree(rgba);
    throw std::runtime_error("WebP reading failed");
  }
  Image image(width, height);
  for (int y = 0; y < height; ++y) for (int x = 0; x < width; ++x) {
    const auto* pixel = rgba + (static_cast<std::size_t>(y) * width + x) * 4U;
    image.at(x, y) = Pixel{pixel[0], pixel[1], pixel[2], pixel[3]};
  }
  WebPFree(rgba);
  return image;
}

Image read_image(const std::vector<std::uint8_t>& bytes) {
  if (bytes.size() >= 8 && png_sig_cmp(const_cast<png_bytep>(bytes.data()), 0, 8) == 0) return read_png(bytes);
  if (bytes.size() >= 2 && bytes[0] == 0xff && bytes[1] == 0xd8) return read_jpeg(bytes);
  if (bytes.size() >= 12 && std::memcmp(bytes.data(), "RIFF", 4) == 0 && std::memcmp(bytes.data() + 8, "WEBP", 4) == 0) return read_webp(bytes);
  throw std::runtime_error("native decoder accepts PNG, JPEG or WebP input");
}

Image normalize_image(const Image& source) {
  constexpr int canvas = 1024;
  constexpr int occupied = 900;
  Image result(canvas, canvas, Pixel{255, 255, 255, 255});
  const int offset = (canvas - occupied) / 2;
  for (int y = 0; y < occupied; ++y) for (int x = 0; x < occupied; ++x) {
    const int source_x = std::min(source.width - 1, x * source.width / occupied);
    const int source_y = std::min(source.height - 1, y * source.height / occupied);
    result.set(x + offset, y + offset, source.at(source_x, source_y));
  }
  return result;
}

Pixel sample_bilinear(const Image& image, double x, double y) {
  if (x < 0.0 || y < 0.0 || x >= image.width - 1 || y >= image.height - 1) {
    const int ix = std::clamp(static_cast<int>(std::round(x)), 0, image.width - 1);
    const int iy = std::clamp(static_cast<int>(std::round(y)), 0, image.height - 1);
    return image.at(ix, iy);
  }
  const int x0 = static_cast<int>(std::floor(x));
  const int y0 = static_cast<int>(std::floor(y));
  const double fx = x - x0;
  const double fy = y - y0;
  const Pixel p00 = image.at(x0, y0);
  const Pixel p10 = image.at(x0 + 1, y0);
  const Pixel p01 = image.at(x0, y0 + 1);
  const Pixel p11 = image.at(x0 + 1, y0 + 1);
  auto mix = [&](int channel) {
    auto value = [channel](const Pixel& pixel) -> double {
      if (channel == 0) return pixel.r;
      if (channel == 1) return pixel.g;
      if (channel == 2) return pixel.b;
      return pixel.a;
    };
    const double a = value(p00);
    const double b = value(p10);
    const double c = value(p01);
    const double d = value(p11);
    return static_cast<std::uint8_t>(std::clamp(std::round((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy), 0.0, 255.0));
  };
  return Pixel{mix(0), mix(1), mix(2), mix(3)};
}

void draw_center_image(Image& image, double center, double radius, const std::vector<std::uint8_t>& bytes) {
  if (bytes.empty()) return;
  const Image source = read_image(bytes);
  const double side = static_cast<double>(std::min(source.width, source.height));
  const double left = (source.width - side) / 2.0;
  const double top = (source.height - side) / 2.0;
  const int min_x = static_cast<int>(std::floor(center - radius));
  const int max_x = static_cast<int>(std::ceil(center + radius));
  const double rr = radius * radius;
  for (int y = min_x; y <= max_x; ++y) for (int x = min_x; x <= max_x; ++x) {
    const double dx = x + 0.5 - center;
    const double dy = y + 0.5 - center;
    if (dx * dx + dy * dy > rr) continue;
    const double u = (dx / radius + 1.0) * 0.5;
    const double v = (dy / radius + 1.0) * 0.5;
    const Pixel p = sample_bilinear(source, left + u * side, top + v * side);
    blend(image, x, y, p, static_cast<double>(p.a) / 255.0);
  }
}

void draw_center_text(Image& image, double center, double radius, const std::string& text) {
  if (text.empty()) return;
  const char* configured = std::getenv("ORBIQO_FONT_PATH");
  const std::string font_path = configured != nullptr ? configured : "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf";
  FT_Library library = nullptr;
  FT_Face face = nullptr;
  if (FT_Init_FreeType(&library) != 0 || FT_New_Face(library, font_path.c_str(), 0, &face) != 0) {
    if (face) FT_Done_Face(face);
    if (library) FT_Done_FreeType(library);
    throw std::runtime_error("native text renderer could not load FreeType font");
  }
  const int size = std::max(8, static_cast<int>(radius * 0.78));
  FT_Set_Pixel_Sizes(face, 0, static_cast<FT_UInt>(size));
  std::vector<FT_UInt> glyphs;
  for (unsigned char c : text) glyphs.push_back(FT_Get_Char_Index(face, c));
  long total_advance = 0;
  for (FT_UInt glyph : glyphs) if (FT_Load_Glyph(face, glyph, FT_LOAD_DEFAULT) == 0) total_advance += face->glyph->advance.x;
  double pen_x = center - static_cast<double>(total_advance) / 128.0;
  const double baseline = center + radius * 0.34;
  for (FT_UInt glyph : glyphs) {
    if (FT_Load_Glyph(face, glyph, FT_LOAD_DEFAULT) != 0 || FT_Render_Glyph(face->glyph, FT_RENDER_MODE_NORMAL) != 0) continue;
    FT_GlyphSlot slot = face->glyph;
    const int origin_x = static_cast<int>(std::round(pen_x + slot->bitmap_left));
    const int origin_y = static_cast<int>(std::round(baseline - slot->bitmap_top));
    for (int row = 0; row < slot->bitmap.rows; ++row) for (int col = 0; col < slot->bitmap.width; ++col) {
      const auto alpha = slot->bitmap.buffer[row * slot->bitmap.pitch + col];
      blend(image, origin_x + col, origin_y + row, Pixel{17, 17, 17, alpha}, static_cast<double>(alpha) / 255.0);
    }
    pen_x += slot->advance.x / 64.0;
  }
  FT_Done_Face(face);
  FT_Done_FreeType(library);
}

std::vector<std::uint8_t> pack_symbols(const std::vector<int>& symbols, int bits) {
  std::vector<std::uint8_t> out((symbols.size() * static_cast<std::size_t>(bits) + 7U) / 8U, 0);
  for (std::size_t i = 0; i < symbols.size(); ++i) for (int shift = bits - 1; shift >= 0; --shift) {
    const std::size_t bit = i * static_cast<std::size_t>(bits) + static_cast<std::size_t>(bits - 1 - shift);
    out[bit / 8U] |= static_cast<std::uint8_t>(((symbols[i] >> shift) & 1) << (7U - (bit % 8U)));
  }
  return out;
}

std::vector<int> calibration_state(const orbiqo::codec::GeometryModel& model, int ring, int sector, int states) {
  std::vector<int> result;
  if (states <= 1) return result;
  const int candidates[4] = {0, std::max(0, model.data_rings / 3), std::max(0, 2 * model.data_rings / 3), model.data_rings - 1};
  for (int repetition = 0; repetition < 4; ++repetition) {
    if (candidates[repetition] != ring) continue;
    const int sectors = model.sector_counts[static_cast<std::size_t>(ring)];
    const int base = static_cast<int>(std::round(static_cast<double>(repetition) / 4.0 * sectors));
    for (int state = 0; state < states; ++state) if ((base + state) % sectors == sector) result.push_back(state);
  }
  return result;
}

void draw_bootstrap(Image& image, double center, double functional_radius, const orbiqo::codec::Header& header, Pixel dark, Pixel background) {
  draw_ring(image, center, ((kGuardInner + kGuardOuter) / 2.0) * functional_radius, (kGuardOuter - kGuardInner) * functional_radius, dark);
  const auto clock = orbiqo::codec::clock_track_bits();
  const double clock_radius = ((kClockInner + kClockOuter) / 2.0) * functional_radius;
  const double clock_width = std::max(1.0, (kClockOuter - kClockInner) * functional_radius * 0.90);
  for (int slot = 0; slot < kClockSlots; ++slot) if (clock[static_cast<std::size_t>(slot)] != 0) {
    const double span = kTau / kClockSlots;
    draw_arc(image, center, clock_radius, slot * span + span * 0.12, (slot + 1) * span - span * 0.12, clock_width, dark);
  }
  const int copies = header.format_version >= 5 ? 4 : 3;
  for (int copy = 0; copy < copies; ++copy) {
    const double inner = copy < 3 ? kHeaderRings[copy][0] : kOuterHeaderRing[0];
    const double outer = copy < 3 ? kHeaderRings[copy][1] : kOuterHeaderRing[1];
    const double radius = (inner + outer) / 2.0 * functional_radius;
    const double width = std::max(1.0, (outer - inner) * functional_radius * 0.78);
    const auto bits = orbiqo::codec::header_physical_bits(header, copy);
    const double span = kTau / kHeaderSlots;
    for (int slot = 0; slot < kHeaderSlots; ++slot) if (bits[static_cast<std::size_t>(slot)] != 0) {
      draw_arc(image, center, radius, slot * span + span * 0.13, (slot + 1) * span - span * 0.13, width, dark);
    }
  }
  const double anchor_radius = (kAnchorInner + kAnchorOuter) / 2.0 * functional_radius;
  const double anchor_width = std::max(1.0, (kAnchorOuter - kAnchorInner) * functional_radius * 0.64);
  for (int i = 0; i < 4; ++i) {
    const double theta = kAnchorSlots[i] * kTau / 128.0;
    const double half = kAnchorWidths[i] * kTau / 128.0 * 0.38;
    draw_arc(image, center, anchor_radius, theta - half, theta + half, anchor_width, background, true);
  }
}

Image render_raster(const orbiqo::codec::EncodedSymbol& symbol, const RenderConfig& config) {
  if (config.dpi < 72 || config.dpi > 600) throw std::invalid_argument("dpi must be between 72 and 600");
  const double diameter_mm = config.diameter_mm > 0.0 ? config.diameter_mm : recommended_diameter(symbol.geometry.version);
  const int output = std::max(1, static_cast<int>(std::ceil(diameter_mm * kQuietZoneOuter / 25.4 * config.dpi)));
  const int supersample = symbol.geometry.data_rings <= 4 ? 3 : symbol.geometry.version >= 3 ? 2 : 1;
  const int pixels = output * supersample;
  const double scale = pixels / kSvgCanvas;
  const double center = kSvgCenter * scale;
  const double functional_radius = kSvgR * scale;
  Image image(pixels, pixels, config.background);
  const Pixel dark = rgb(17, 17, 17);
  const auto palette = palette_for(symbol.header.alphabet, symbol.header.palette_id);
  draw_bootstrap(image, center, functional_radius, symbol.header, dark, config.background);
  const int states = 1 << (symbol.header.alphabet == orbiqo::codec::Alphabet::Color4 ? 2 : 1);
  std::vector<int> ring_offsets(static_cast<std::size_t>(symbol.geometry.data_rings), 0);
  std::size_t cell_offset = 0;
  for (int ring = 0; ring < symbol.geometry.data_rings; ++ring) {
    const int sectors = symbol.geometry.sector_counts[static_cast<std::size_t>(ring)];
    const double span = kTau / sectors;
    const double first = symbol.geometry.cells[cell_offset].theta_start;
    ring_offsets[static_cast<std::size_t>(ring)] = static_cast<int>(std::round(first / span)) % sectors;
    cell_offset += static_cast<std::size_t>(sectors);
  }
  for (int y = 0; y < pixels; ++y) for (int x = 0; x < pixels; ++x) {
    const double dx = x + 0.5 - center;
    const double dy = center - (y + 0.5);
    const double radius = std::sqrt(dx * dx + dy * dy) / functional_radius;
    if (radius < symbol.geometry.data_inner || radius > 0.91) continue;
    int ring = static_cast<int>((radius - symbol.geometry.data_inner) / symbol.geometry.radial_pitch);
    if (ring < 0 || ring >= symbol.geometry.data_rings) continue;
    const int sectors = symbol.geometry.sector_counts[static_cast<std::size_t>(ring)];
    const double span = kTau / sectors;
    double theta = std::atan2(dx, dy);
    if (theta < 0) theta += kTau;
    const double offset = symbol.geometry.cells[std::accumulate(symbol.geometry.sector_counts.begin(), symbol.geometry.sector_counts.begin() + ring, 0)].theta_start;
    double shifted = theta - offset;
    while (shifted < 0) shifted += kTau;
    while (shifted >= kTau) shifted -= kTau;
    const int sector = std::min(sectors - 1, static_cast<int>(shifted / span));
    const double local = shifted - sector * span;
    const double gutter = span * (1.0 - config.angular_fill) / 2.0;
    const double radial_center = symbol.geometry.data_inner + (ring + 0.5) * symbol.geometry.radial_pitch;
    if (local < gutter || local > span - gutter || std::abs(radius - radial_center) > symbol.geometry.radial_pitch * config.radial_fill / 2.0) continue;
    std::size_t index = 0;
    for (int r = 0; r < ring; ++r) index += static_cast<std::size_t>(symbol.geometry.sector_counts[static_cast<std::size_t>(r)]);
    index += static_cast<std::size_t>(sector);
    const int state = std::clamp(symbol.geometry.cells[index].state, 0, states - 1);
    image.set(x, y, palette[static_cast<std::size_t>(state)]);
  }
  const double logo_radius = kLogoRadius * functional_radius * 0.92;
  draw_disc(image, center, center, logo_radius, config.background);
  if (!config.center_image.empty()) draw_center_image(image, center, logo_radius, config.center_image);
  else if (!config.center_text.empty()) draw_center_text(image, center, logo_radius, config.center_text);
  draw_ring(image, center, logo_radius, std::max(1.0, functional_radius * 0.008), dark);
  return supersample == 1 ? image : downsample_box(image, output, supersample);
}

std::string arc_path(double radius, double start, double end) {
  auto point = [&](double theta) {
    std::ostringstream s;
    s << std::fixed << std::setprecision(4) << kSvgCenter + radius * std::sin(theta) << ' ' << kSvgCenter - radius * std::cos(theta);
    return s.str();
  };
  const int large = end - start > 3.141592653589793 ? 1 : 0;
  std::ostringstream out;
  out << "M " << point(start) << " A " << std::fixed << std::setprecision(4) << radius << ' ' << radius << " 0 " << large << " 1 " << point(end);
  return out.str();
}

std::string render_svg(const orbiqo::codec::EncodedSymbol& symbol, const RenderConfig& config) {
  const double diameter = config.diameter_mm > 0.0 ? config.diameter_mm : recommended_diameter(symbol.geometry.version);
  const double total_mm = diameter * kQuietZoneOuter;
  const auto palette = palette_for(symbol.header.alphabet, symbol.header.palette_id);
  auto color_hex = [](Pixel p) {
    std::ostringstream out;
    out << '#' << std::hex << std::setfill('0') << std::setw(2) << static_cast<int>(p.r) << std::setw(2) << static_cast<int>(p.g) << std::setw(2) << static_cast<int>(p.b);
    return out.str();
  };
  const std::string background = color_hex(config.background);
  const std::string dark = "#111111";
  std::ostringstream out;
  out << "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n";
  out << "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"" << total_mm << "mm\" height=\"" << total_mm << "mm\" viewBox=\"0 0 " << kSvgCanvas << ' ' << kSvgCanvas << "\" role=\"img\" aria-label=\"Orbiqo symbol\">\n";
  out << "<title>Orbiqo " << xml_escape(geometry_name(symbol.geometry.version)) << " symbol</title>\n";
  out << "<desc>Built with RadialCode — an open radial 2D code project.</desc>\n";
  out << "<metadata>{\"generator\":\"Orbiqo native C++ renderer\",\"format_version\":" << symbol.header.format_version << ",\"geometry_version\":" << symbol.geometry.version << ",\"palette_id\":" << symbol.header.palette_id << "}</metadata>\n";
  out << "<rect width=\"" << kSvgCanvas << "\" height=\"" << kSvgCanvas << "\" fill=\"" << background << "\"/>\n";
  const double guard_radius = (kGuardInner + kGuardOuter) / 2.0 * kSvgR;
  out << "<circle cx=\"" << kSvgCenter << "\" cy=\"" << kSvgCenter << "\" r=\"" << guard_radius << "\" fill=\"none\" stroke=\"" << dark << "\" stroke-width=\"" << (kGuardOuter - kGuardInner) * kSvgR << "\"/>\n";
  const auto clock = orbiqo::codec::clock_track_bits();
  const double clock_radius = (kClockInner + kClockOuter) / 2.0 * kSvgR;
  const double clock_span = kTau / kClockSlots;
  for (int slot = 0; slot < kClockSlots; ++slot) if (clock[static_cast<std::size_t>(slot)]) out << "<path d=\"" << arc_path(clock_radius, slot * clock_span + clock_span * 0.12, (slot + 1) * clock_span - clock_span * 0.12) << "\" fill=\"none\" stroke=\"" << dark << "\" stroke-width=\"" << (kClockOuter - kClockInner) * kSvgR * 0.90 << "\"/>\n";
  const int copies = symbol.header.format_version >= 5 ? 4 : 3;
  for (int copy = 0; copy < copies; ++copy) {
    const double inner = copy < 3 ? kHeaderRings[copy][0] : kOuterHeaderRing[0];
    const double outer = copy < 3 ? kHeaderRings[copy][1] : kOuterHeaderRing[1];
    const double radius = (inner + outer) / 2.0 * kSvgR;
    const double span = kTau / kHeaderSlots;
    const auto bits = orbiqo::codec::header_physical_bits(symbol.header, copy);
    for (int slot = 0; slot < kHeaderSlots; ++slot) if (bits[static_cast<std::size_t>(slot)]) out << "<path d=\"" << arc_path(radius, slot * span + span * 0.13, (slot + 1) * span - span * 0.13) << "\" fill=\"none\" stroke=\"" << dark << "\" stroke-width=\"" << (outer - inner) * kSvgR * 0.78 << "\"/>\n";
  }
  const double anchor_radius = (kAnchorInner + kAnchorOuter) / 2.0 * kSvgR;
  for (int i = 0; i < 4; ++i) {
    const double center = kAnchorSlots[i] * kTau / 128.0;
    const double half = kAnchorWidths[i] * kTau / 128.0 * 0.38;
    out << "<path d=\"" << arc_path(anchor_radius, center - half, center + half) << "\" fill=\"none\" stroke=\"" << background << "\" stroke-width=\"" << (kAnchorOuter - kAnchorInner) * kSvgR * 0.64 << "\" stroke-linecap=\"round\"/>\n";
  }
  const std::string cap = symbol.header.format_version >= 3 ? "butt" : "round";
  out << "<g fill=\"none\" stroke-linecap=\"" << cap << "\">\n";
  for (const auto& cell : symbol.geometry.cells) {
    const double span = cell.theta_end - cell.theta_start;
    const double gutter = span * (1.0 - config.angular_fill) / 2.0;
    out << "<path d=\"" << arc_path((cell.r_inner + cell.r_outer) / 2.0 * kSvgR, cell.theta_start + gutter, cell.theta_end - gutter) << "\" stroke=\"" << color_hex(palette[static_cast<std::size_t>(std::clamp(cell.state, 0, static_cast<int>(palette.size()) - 1))]) << "\" stroke-width=\"" << (cell.r_outer - cell.r_inner) * kSvgR * config.radial_fill << "\"/>\n";
  }
  out << "</g>\n";
  const double logo_radius = kLogoRadius * kSvgR * 0.92;
  out << "<circle cx=\"" << kSvgCenter << "\" cy=\"" << kSvgCenter << "\" r=\"" << logo_radius << "\" fill=\"" << background << "\"/>\n";
  if (!config.center_image.empty()) {
    out << "<defs><clipPath id=\"orbiqo-center\"><circle cx=\"" << kSvgCenter << "\" cy=\"" << kSvgCenter << "\" r=\"" << logo_radius << "\"/></clipPath></defs>\n";
    out << "<image x=\"" << kSvgCenter - logo_radius << "\" y=\"" << kSvgCenter - logo_radius << "\" width=\"" << 2 * logo_radius << "\" height=\"" << 2 * logo_radius << "\" preserveAspectRatio=\"none\" clip-path=\"url(#orbiqo-center)\" href=\"data:image/png;base64," << base64_encode(config.center_image) << "\"/>\n";
  } else if (!config.center_text.empty()) {
    out << "<text x=\"" << kSvgCenter << "\" y=\"" << kSvgCenter + kSvgR * 0.035 << "\" text-anchor=\"middle\" font-family=\"DejaVu Sans, sans-serif\" font-size=\"" << kSvgR * 0.12 << "\" font-weight=\"700\" fill=\"" << dark << "\">" << xml_escape(config.center_text.substr(0, 8)) << "</text>\n";
  }
  out << "<circle cx=\"" << kSvgCenter << "\" cy=\"" << kSvgCenter << "\" r=\"" << logo_radius << "\" fill=\"none\" stroke=\"" << dark << "\" stroke-width=\"" << kSvgR * 0.008 << "\"/>\n</svg>\n";
  return out.str();
}

struct DecodeResult {
  std::vector<std::uint8_t> payload;
  orbiqo::codec::PayloadType payload_type = orbiqo::codec::PayloadType::Binary;
  orbiqo::codec::Header header;
  int corrected_header_bits = 0;
  int corrected_rs_symbols = 0;
  double average_confidence = 1.0;
  double minimum_confidence = 1.0;
  int erasure_cells = 0;
  int width = 0;
  int height = 0;
  double axis_ratio = 1.0;
  std::string mode = "canonical";
};

double luma(Pixel p) { return 0.2126 * p.r + 0.7152 * p.g + 0.0722 * p.b; }

Pixel sample_patch(const Image& image, double nx, double theta, int patch_radius = 1) {
  const double cx = (image.width - 1) / 2.0;
  const double cy = (image.height - 1) / 2.0;
  const double functional = std::min(image.width, image.height) / (2.0 * kQuietZoneOuter);
  const int ix = static_cast<int>(std::round(cx + nx * functional * std::sin(theta)));
  const int iy = static_cast<int>(std::round(cy - nx * functional * std::cos(theta)));
  double r = 0, g = 0, b = 0;
  int count = 0;
  for (int y = iy - patch_radius; y <= iy + patch_radius; ++y) for (int x = ix - patch_radius; x <= ix + patch_radius; ++x) if (x >= 0 && y >= 0 && x < image.width && y < image.height) {
    const Pixel p = image.at(x, y); r += p.r; g += p.g; b += p.b; ++count;
  }
  if (count == 0) throw std::runtime_error("sample lies outside image");
  return rgb(static_cast<int>(std::round(r / count)), static_cast<int>(std::round(g / count)), static_cast<int>(std::round(b / count)));
}

double adaptive_threshold(const std::vector<double>& values) {
  if (values.empty()) throw std::runtime_error("empty threshold sample");
  double low = *std::min_element(values.begin(), values.end());
  double high = *std::max_element(values.begin(), values.end());
  for (int iteration = 0; iteration < 16; ++iteration) {
    const double midpoint = (low + high) / 2.0;
    double low_sum = 0, high_sum = 0; int low_count = 0, high_count = 0;
    for (double value : values) { if (value <= midpoint) { low_sum += value; ++low_count; } else { high_sum += value; ++high_count; } }
    if (low_count == 0 || high_count == 0) break;
    const double next_low = low_sum / low_count;
    const double next_high = high_sum / high_count;
    if (std::abs(next_low - low) + std::abs(next_high - high) < 0.02) { low = next_low; high = next_high; break; }
    low = next_low; high = next_high;
  }
  if (high - low < 4.0) throw std::runtime_error("insufficient header separation");
  return (low + high) / 2.0;
}

std::uint64_t physical_to_codeword(const std::vector<int>& bits, int copy) {
  const int offsets[4] = {0, 17, 43, 29};
  std::uint64_t value = 0;
  for (int i = 0; i < 63; ++i) value = (value << 1U) | static_cast<std::uint64_t>(bits[static_cast<std::size_t>((offsets[copy] + 1 + i) % 64)]);
  return value;
}

std::pair<orbiqo::codec::Header, int> decode_header_from_image(const Image& image) {
  std::vector<std::pair<orbiqo::codec::Header, int>> successes;
  std::array<std::vector<int>, 4> physical_copies;
  for (int copy = 0; copy < 4; ++copy) {
    const double radius = copy < 3
        ? (kHeaderRings[copy][0] + kHeaderRings[copy][1]) / 2.0
        : (kOuterHeaderRing[0] + kOuterHeaderRing[1]) / 2.0;
    std::vector<double> values;
    for (int slot = 0; slot < 64; ++slot) values.push_back(luma(sample_patch(image, radius, (slot + 0.5) * kTau / 64.0, 0)));
    try {
      const double threshold = adaptive_threshold(values);
      std::vector<int> bits; for (double value : values) bits.push_back(value < threshold ? 1 : 0);
      physical_copies[static_cast<std::size_t>(copy)] = bits;
      int corrected = 0;
      successes.emplace_back(orbiqo::codec::decode_header_codeword(physical_to_codeword(bits, copy), &corrected), corrected);
    } catch (const std::exception&) {
      continue;
    }
  }
  auto majority_codeword = [&](int copies) {
    std::uint64_t codeword = 0;
    for (int index = 0; index < 63; ++index) {
      int votes = 0;
      int count = 0;
      for (int copy = 0; copy < copies; ++copy) {
        const auto& bits = physical_copies[static_cast<std::size_t>(copy)];
        if (bits.size() != 64) continue;
        votes += bits[static_cast<std::size_t>((kHeaderSlotOffsets[copy] + 1 + index) % 64)];
        ++count;
      }
      if (count == 0) throw std::runtime_error("no BCH header samples are usable");
      codeword = (codeword << 1U) | static_cast<std::uint64_t>(votes * 2 >= count ? 1 : 0);
    }
    return codeword;
  };
  if (successes.empty()) {
    for (int copies : {3, 4}) {
      try {
        int corrected = 0;
        auto header = orbiqo::codec::decode_header_codeword(majority_codeword(copies), &corrected);
        if (copies == 3 || header.format_version >= 5) return {header, corrected};
      } catch (const std::exception&) {
        continue;
      }
    }
    throw std::runtime_error("no BCH header copy is correctable");
  }
  std::size_t best_index = 0;
  int best_votes = 0;
  int best_correction = std::numeric_limits<int>::max();
  for (std::size_t candidate = 0; candidate < successes.size(); ++candidate) {
    int votes = 0;
    for (const auto& success : successes) if (success.first.data == successes[candidate].first.data) ++votes;
    if (votes > best_votes || (votes == best_votes && successes[candidate].second < best_correction)) {
      best_votes = votes;
      best_correction = successes[candidate].second;
      best_index = candidate;
    }
  }
  return successes[best_index];
}

DecodeResult decode_canonical_image(const Image& image, double erasure_threshold) {
  (void)erasure_threshold;
  const auto header_result = decode_header_from_image(image);
  const auto header = header_result.first;
  const auto model = orbiqo::codec::geometry_model(header.geometry_version, header.format_version, header.alphabet);
  const auto palette = palette_for(header.alphabet, header.palette_id);
  const int bits_per_cell = header.alphabet == orbiqo::codec::Alphabet::Color4 ? 2 : 1;
  std::map<int, std::array<double, 3>> means;
  std::map<int, int> counts;
  for (const auto& cell : model.cells) if (!cell.payload) {
    const auto possible = calibration_state(model, cell.ring, cell.sector, 1 << bits_per_cell);
    if (possible.empty()) continue;
    const Pixel p = sample_patch(image, (cell.r_inner + cell.r_outer) / 2.0, (cell.theta_start + cell.theta_end) / 2.0, 1);
    auto& mean = means[possible.front()]; mean[0] += p.r; mean[1] += p.g; mean[2] += p.b; counts[possible.front()]++;
  }
  for (auto& [state, mean] : means) { const double n = std::max(1, counts[state]); mean[0] /= n; mean[1] /= n; mean[2] /= n; }
  std::vector<int> symbols;
  std::vector<double> confidences;
  std::vector<int> erasure_cells;
  int physical_index = 0;
  for (const auto& cell : model.cells) if (cell.payload) {
    const Pixel p = sample_patch(image, (cell.r_inner + cell.r_outer) / 2.0, (cell.theta_start + cell.theta_end) / 2.0, 1);
    int state = 0; double best = std::numeric_limits<double>::max(), second = std::numeric_limits<double>::max();
    if (header.alphabet == orbiqo::codec::Alphabet::Mono2) {
      state = luma(p) < 128.0 ? 1 : 0;
      best = std::abs(luma(p) - (state ? 17.0 : 255.0));
      second = std::abs(luma(p) - (state ? 255.0 : 17.0));
    } else {
      for (int candidate = 0; candidate < 4; ++candidate) {
        const auto it = means.find(candidate);
        const double mr = it == means.end() ? palette[static_cast<std::size_t>(candidate)].r : it->second[0];
        const double mg = it == means.end() ? palette[static_cast<std::size_t>(candidate)].g : it->second[1];
        const double mb = it == means.end() ? palette[static_cast<std::size_t>(candidate)].b : it->second[2];
        const double distance = std::sqrt((p.r - mr) * (p.r - mr) + (p.g - mg) * (p.g - mg) + (p.b - mb) * (p.b - mb));
        if (distance < best) { second = best; best = distance; state = candidate; } else if (distance < second) second = distance;
      }
    }
    symbols.push_back(state);
    const double confidence = std::clamp(second / std::max(1.0, best + second), 0.0, 1.0);
    confidences.push_back(confidence);
    if (confidence < erasure_threshold) erasure_cells.push_back(physical_index);
    ++physical_index;
  }
  const auto packed = pack_symbols(symbols, bits_per_cell);
  auto decoded = erasure_cells.empty()
      ? orbiqo::codec::decode(packed, static_cast<int>(symbols.size()), header.codeword)
      : orbiqo::codec::decode_with_erasures(packed, static_cast<int>(symbols.size()), header.codeword, erasure_cells);
  DecodeResult result;
  result.payload = decoded.payload;
  result.payload_type = decoded.payload_type;
  result.header = decoded.header;
  result.corrected_header_bits = header_result.second;
  result.corrected_rs_symbols = decoded.corrected_rs_symbols;
  result.width = image.width;
  result.height = image.height;
  result.average_confidence = confidences.empty() ? 1.0 : std::accumulate(confidences.begin(), confidences.end(), 0.0) / confidences.size();
  result.minimum_confidence = confidences.empty() ? 1.0 : *std::min_element(confidences.begin(), confidences.end());
  result.erasure_cells = static_cast<int>(std::count_if(confidences.begin(), confidences.end(), [erasure_threshold](double value) { return value < erasure_threshold; }));
  return result;
}

struct AnchorObservation {
  std::array<double, 2> point{};
  int width = 0;
};

std::vector<AnchorObservation> light_runs(const Image& image, double normalized_radius, int sample_count) {
  const double center = image.width / 2.0;
  const double functional = image.width / (2.0 * kQuietZoneOuter);
  std::vector<double> samples;
  samples.reserve(static_cast<std::size_t>(sample_count));
  for (int index = 0; index < sample_count; ++index) {
    const double theta = index * kTau / sample_count;
    const double x = center + normalized_radius * functional * std::sin(theta);
    const double y = center - normalized_radius * functional * std::cos(theta);
    samples.push_back(luma(sample_bilinear(image, x, y)));
  }
  const double threshold = adaptive_threshold(samples);
  std::vector<int> bits;
  bits.reserve(samples.size());
  for (double value : samples) bits.push_back(value > threshold ? 1 : 0);
  if (std::all_of(bits.begin(), bits.end(), [](int value) { return value == 0; }) || std::all_of(bits.begin(), bits.end(), [](int value) { return value == 1; })) return {};
  int light = 0;
  while (light < sample_count && bits[static_cast<std::size_t>(light)] != 0) ++light;
  const int start = (light + 1) % sample_count;
  std::vector<AnchorObservation> runs;
  int index = 0;
  while (index < sample_count) {
    const int position = (start + index) % sample_count;
    if (bits[static_cast<std::size_t>(position)] == 0) { ++index; continue; }
    const int run_start = index;
    while (index < sample_count && bits[static_cast<std::size_t>((start + index) % sample_count)] == 1) ++index;
    const int width = index - run_start;
    if (width >= 3 && width <= sample_count / 8) {
      const double center_ordered = run_start + (width - 1) / 2.0;
      const double theta = (start + center_ordered) * kTau / sample_count;
      runs.push_back({{center + normalized_radius * functional * std::sin(theta), center - normalized_radius * functional * std::cos(theta)}, width});
    }
  }
  return runs;
}

std::vector<std::array<double, 2>> detect_anchor_points(const Image& image, std::array<int, 4>* widths) {
  constexpr int sample_count = 512;
  const std::array<double, 4> expected_widths = {3.0, 5.0, 7.0, 9.0};
  const std::array<double, 4> expected_gaps = {19.0, 27.0, 35.0, 47.0};
  double best_score = -std::numeric_limits<double>::infinity();
  std::vector<AnchorObservation> best;
  for (int scan = 0; scan < 89; ++scan) {
    const double radius = 0.915 + scan * 0.110 / 88.0;
    std::vector<AnchorObservation> runs;
    try { runs = light_runs(image, radius, sample_count); } catch (const std::exception&) { continue; }
    if (runs.size() < 4) continue;
    std::sort(runs.begin(), runs.end(), [](const auto& left, const auto& right) { return left.width > right.width; });
    runs.resize(4);
    std::sort(runs.begin(), runs.end(), [](const auto& left, const auto& right) { return left.width < right.width; });
    double dot = 0.0, norm = 0.0;
    for (int i = 0; i < 4; ++i) { dot += runs[static_cast<std::size_t>(i)].width * expected_widths[static_cast<std::size_t>(i)]; norm += expected_widths[static_cast<std::size_t>(i)] * expected_widths[static_cast<std::size_t>(i)]; }
    const double scale = dot / norm;
    if (scale <= 0.0) continue;
    double width_error = 0.0;
    for (int i = 0; i < 4; ++i) width_error += std::abs(runs[static_cast<std::size_t>(i)].width - scale * expected_widths[static_cast<std::size_t>(i)]) / (scale * expected_widths[static_cast<std::size_t>(i)]);
    std::array<double, 4> angles{};
    for (int i = 0; i < 4; ++i) angles[static_cast<std::size_t>(i)] = std::atan2(runs[static_cast<std::size_t>(i)].point[0] - image.width / 2.0, image.height / 2.0 - runs[static_cast<std::size_t>(i)].point[1]);
    double spacing_error = 0.0;
    for (int i = 0; i < 4; ++i) {
      double delta = angles[static_cast<std::size_t>((i + 1) % 4)] - angles[static_cast<std::size_t>(i)];
      while (delta < 0.0) delta += kTau;
      const double measured = delta * sample_count / kTau;
      const double expected = expected_gaps[static_cast<std::size_t>(i)] * sample_count / 128.0;
      spacing_error += std::abs(measured - expected) / expected;
    }
    const double score = 500.0 - 160.0 * width_error / 4.0 - 260.0 * spacing_error / 4.0;
    if (score > best_score) { best_score = score; best = runs; }
  }
  if (best.empty()) throw std::runtime_error("four anchor notches were not detected");
  if (widths != nullptr) for (int i = 0; i < 4; ++i) (*widths)[static_cast<std::size_t>(i)] = best[static_cast<std::size_t>(i)].width;
  std::vector<std::array<double, 2>> points;
  for (const auto& item : best) points.push_back(item.point);
  return points;
}

struct GuardHole {
  int area = 0;
  std::array<double, 2> point{};
};

int otsu_threshold(const Image& image) {
  std::array<int, 256> histogram{};
  for (const auto& pixel : image.pixels) {
    ++histogram[static_cast<std::size_t>(std::clamp(static_cast<int>(std::round(luma(pixel))), 0, 255))];
  }
  const int total = image.width * image.height;
  double weighted_total = 0.0;
  for (int value = 0; value < 256; ++value) weighted_total += value * histogram[static_cast<std::size_t>(value)];
  int background_count = 0;
  double background_sum = 0.0;
  double best_between = -1.0;
  int best_threshold = 127;
  for (int threshold = 0; threshold < 256; ++threshold) {
    background_count += histogram[static_cast<std::size_t>(threshold)];
    if (background_count == 0) continue;
    const int foreground_count = total - background_count;
    if (foreground_count == 0) break;
    background_sum += threshold * histogram[static_cast<std::size_t>(threshold)];
    const double background_mean = background_sum / background_count;
    const double foreground_mean = (weighted_total - background_sum) / foreground_count;
    const double difference = background_mean - foreground_mean;
    const double between = static_cast<double>(background_count) * foreground_count * difference * difference;
    if (between > best_between) {
      best_between = between;
      best_threshold = threshold;
    }
  }
  return best_threshold;
}

std::vector<GuardHole> detect_guard_holes(const Image& image) {
  const int threshold = otsu_threshold(image);
  const std::size_t total = image.pixels.size();
  std::vector<std::uint8_t> visited(total, 0);
  std::vector<GuardHole> holes;
  const double center_x = (image.width - 1) / 2.0;
  const double center_y = (image.height - 1) / 2.0;
  const double functional = std::min(image.width, image.height) / (2.0 * kQuietZoneOuter);
  const int maximum_area = std::max(20, static_cast<int>(total * 0.008));
  const std::array<std::array<int, 2>, 4> neighbors = {{{1, 0}, {-1, 0}, {0, 1}, {0, -1}}};
  const auto index_of = [&](int x, int y) { return static_cast<std::size_t>(y) * image.width + x; };
  const auto is_light = [&](int x, int y) { return luma(image.at(x, y)) > threshold; };
  for (int y = 0; y < image.height; ++y) for (int x = 0; x < image.width; ++x) {
    const std::size_t seed = index_of(x, y);
    if (visited[seed] || !is_light(x, y)) continue;
    visited[seed] = 1;
    std::vector<std::array<int, 2>> stack{{x, y}};
    int area = 0;
    double sum_x = 0.0;
    double sum_y = 0.0;
    while (!stack.empty()) {
      const auto point = stack.back();
      stack.pop_back();
      ++area;
      sum_x += point[0];
      sum_y += point[1];
      for (const auto delta : neighbors) {
        const int nx = point[0] + delta[0];
        const int ny = point[1] + delta[1];
        if (nx < 0 || ny < 0 || nx >= image.width || ny >= image.height) continue;
        const std::size_t neighbor = index_of(nx, ny);
        if (!visited[neighbor] && is_light(nx, ny)) {
          visited[neighbor] = 1;
          stack.push_back({nx, ny});
        }
      }
    }
    if (area < 12 || area > maximum_area) continue;
    const double px = sum_x / area;
    const double py = sum_y / area;
    const double radius = std::hypot(px - center_x, py - center_y) / functional;
    if (radius >= 0.84 && radius <= 1.16) holes.push_back({area, {px, py}});
  }
  return holes;
}

struct GuardHoleMatch {
  std::vector<std::array<double, 2>> source;
  std::vector<int> anchor_ids;
  double relative_error = std::numeric_limits<double>::infinity();
};

GuardHoleMatch match_guard_holes(const Image& image) {
  auto holes = detect_guard_holes(image);
  if (holes.size() < 3) throw std::runtime_error("fewer than three guard notches were detected");
  std::sort(holes.begin(), holes.end(), [](const auto& left, const auto& right) { return left.area > right.area; });
  if (holes.size() > 4) holes.resize(4);
  std::sort(holes.begin(), holes.end(), [](const auto& left, const auto& right) { return left.area < right.area; });
  const int count = static_cast<int>(holes.size());
  const std::array<int, 4> expected = {3, 5, 7, 9};
  GuardHoleMatch best;
  for (int mask = 0; mask < 16; ++mask) {
    if (__builtin_popcount(static_cast<unsigned>(mask)) != count) continue;
    std::vector<int> ids;
    for (int index = 0; index < 4; ++index) if (mask & (1 << index)) ids.push_back(index);
    double numerator = 0.0;
    double denominator = 0.0;
    for (int index = 0; index < count; ++index) {
      const double width = expected[static_cast<std::size_t>(ids[static_cast<std::size_t>(index)])];
      numerator += holes[static_cast<std::size_t>(index)].area * width;
      denominator += width * width;
    }
    const double scale = numerator / std::max(1.0, denominator);
    double error = 0.0;
    for (int index = 0; index < count; ++index) {
      const double expected_area = scale * expected[static_cast<std::size_t>(ids[static_cast<std::size_t>(index)])];
      error += std::abs(holes[static_cast<std::size_t>(index)].area - expected_area) / std::max(1.0, expected_area);
    }
    error /= count;
    if (error < best.relative_error) {
      best.relative_error = error;
      best.anchor_ids = ids;
      best.source.clear();
      for (const auto& hole : holes) best.source.push_back(hole.point);
    }
  }
  if (best.source.size() < 3 || best.relative_error > 0.45) throw std::runtime_error("guard-notch width signature is ambiguous");
  return best;
}

std::array<double, 9> homography_from_points(const std::vector<std::array<double, 2>>& source, const std::vector<std::array<double, 2>>& target) {
  if (source.size() != 4 || target.size() != 4) throw std::runtime_error("homography needs four points");
  std::array<std::array<double, 9>, 8> matrix{};
  for (int i = 0; i < 4; ++i) {
    const double x = source[static_cast<std::size_t>(i)][0], y = source[static_cast<std::size_t>(i)][1];
    const double u = target[static_cast<std::size_t>(i)][0], v = target[static_cast<std::size_t>(i)][1];
    const int row = i * 2;
    matrix[static_cast<std::size_t>(row)] = {x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y, u};
    matrix[static_cast<std::size_t>(row + 1)] = {0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y, v};
  }
  for (int col = 0; col < 8; ++col) {
    int pivot = col;
    for (int row = col + 1; row < 8; ++row) if (std::abs(matrix[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)]) > std::abs(matrix[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(col)])) pivot = row;
    if (std::abs(matrix[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(col)]) < 1e-10) throw std::runtime_error("singular homography");
    std::swap(matrix[static_cast<std::size_t>(pivot)], matrix[static_cast<std::size_t>(col)]);
    const double divisor = matrix[static_cast<std::size_t>(col)][static_cast<std::size_t>(col)];
    for (int j = col; j < 9; ++j) matrix[static_cast<std::size_t>(col)][static_cast<std::size_t>(j)] /= divisor;
    for (int row = 0; row < 8; ++row) if (row != col) {
      const double factor = matrix[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)];
      for (int j = col; j < 9; ++j) matrix[static_cast<std::size_t>(row)][static_cast<std::size_t>(j)] -= factor * matrix[static_cast<std::size_t>(col)][static_cast<std::size_t>(j)];
    }
  }
  return {matrix[0][8], matrix[1][8], matrix[2][8], matrix[3][8], matrix[4][8], matrix[5][8], matrix[6][8], matrix[7][8], 1.0};
}

std::array<double, 9> affine_from_points(const std::vector<std::array<double, 2>>& source, const std::vector<std::array<double, 2>>& target) {
  if (source.size() != 3 || target.size() != 3) throw std::runtime_error("affine fit needs three points");
  auto solve = [&](int component) {
    std::array<std::array<double, 4>, 3> matrix{};
    for (int row = 0; row < 3; ++row) matrix[static_cast<std::size_t>(row)] = {
      source[static_cast<std::size_t>(row)][0],
      source[static_cast<std::size_t>(row)][1],
      1.0,
      target[static_cast<std::size_t>(row)][static_cast<std::size_t>(component)],
    };
    for (int col = 0; col < 3; ++col) {
      int pivot = col;
      for (int row = col + 1; row < 3; ++row) if (std::abs(matrix[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)]) > std::abs(matrix[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(col)])) pivot = row;
      if (std::abs(matrix[static_cast<std::size_t>(pivot)][static_cast<std::size_t>(col)]) < 1e-10) throw std::runtime_error("singular affine fit");
      std::swap(matrix[static_cast<std::size_t>(pivot)], matrix[static_cast<std::size_t>(col)]);
      const double divisor = matrix[static_cast<std::size_t>(col)][static_cast<std::size_t>(col)];
      for (int j = col; j < 4; ++j) matrix[static_cast<std::size_t>(col)][static_cast<std::size_t>(j)] /= divisor;
      for (int row = 0; row < 3; ++row) if (row != col) {
        const double factor = matrix[static_cast<std::size_t>(row)][static_cast<std::size_t>(col)];
        for (int j = col; j < 4; ++j) matrix[static_cast<std::size_t>(row)][static_cast<std::size_t>(j)] -= factor * matrix[static_cast<std::size_t>(col)][static_cast<std::size_t>(j)];
      }
    }
    return std::array<double, 3>{matrix[0][3], matrix[1][3], matrix[2][3]};
  };
  const auto x = solve(0);
  const auto y = solve(1);
  return {x[0], x[1], x[2], y[0], y[1], y[2], 0.0, 0.0, 1.0};
}

std::array<double, 9> inverse_homography(const std::array<double, 9>& h) {
  const double a = h[0], b = h[1], c = h[2], d = h[3], e = h[4], f = h[5], g = h[6], i = h[7], j = h[8];
  const double det = a * (e * j - f * i) - b * (d * j - f * g) + c * (d * i - e * g);
  if (std::abs(det) < 1e-12) throw std::runtime_error("homography is not invertible");
  return {(e * j - f * i) / det, (c * i - b * j) / det, (b * f - c * e) / det,
          (f * g - d * j) / det, (a * j - c * g) / det, (c * d - a * f) / det,
          (d * i - e * g) / det, (b * g - a * i) / det, (a * e - b * d) / det};
}

Image warp_homography(const Image& source, const std::array<double, 9>& source_to_target, int output_size) {
  const auto inverse = inverse_homography(source_to_target);
  Image output(output_size, output_size, Pixel{255, 255, 255, 255});
  for (int y = 0; y < output_size; ++y) for (int x = 0; x < output_size; ++x) {
    const double denominator = inverse[6] * x + inverse[7] * y + inverse[8];
    if (std::abs(denominator) < 1e-12) continue;
    const double sx = (inverse[0] * x + inverse[1] * y + inverse[2]) / denominator;
    const double sy = (inverse[3] * x + inverse[4] * y + inverse[5]) / denominator;
    output.set(x, y, sample_bilinear(source, sx, sy));
  }
  return output;
}

Image rectify_frontal(const Image& source, double* axis_ratio) {
  int min_x = source.width, min_y = source.height, max_x = -1, max_y = -1;
  for (int y = 0; y < source.height; ++y) for (int x = 0; x < source.width; ++x) if (luma(source.at(x, y)) < 88.0) {
    min_x = std::min(min_x, x); min_y = std::min(min_y, y); max_x = std::max(max_x, x); max_y = std::max(max_y, y);
  }
  if (max_x < 0) throw std::runtime_error("no dark guard candidate found");
  const double cx = (min_x + max_x) / 2.0;
  const double cy = (min_y + max_y) / 2.0;
  const double rx = std::max(1.0, (max_x - min_x) / (2.0 * kGuardOuter));
  const double ry = std::max(1.0, (max_y - min_y) / (2.0 * kGuardOuter));
  if (axis_ratio) *axis_ratio = std::min(rx, ry) / std::max(rx, ry);
  const int out_size = std::clamp(std::max(source.width, source.height), 256, 1024);
  Image out(out_size, out_size, Pixel{255, 255, 255, 255});
  const double target_functional = out_size / (2.0 * kQuietZoneOuter);
  const double target_guard = target_functional * kGuardOuter;
  const double target_c = out_size / 2.0;
  for (int y = 0; y < out_size; ++y) for (int x = 0; x < out_size; ++x) {
    const double sx = cx + (x + 0.5 - target_c) * rx / target_guard;
    const double sy = cy + (y + 0.5 - target_c) * ry / target_guard;
    out.set(x, y, sample_bilinear(source, sx, sy));
  }
  try {
    const auto match = match_guard_holes(out);
    const double target_center = out_size / 2.0;
    const double target_radius = out_size / (2.0 * kQuietZoneOuter) * ((kAnchorInner + kAnchorOuter) / 2.0);
    std::vector<std::array<double, 2>> target_points;
    for (const int anchor_id : match.anchor_ids) {
      const int slot = kAnchorSlots[anchor_id];
      const double theta = slot * kTau / 128.0;
      target_points.push_back({target_center + target_radius * std::sin(theta), target_center - target_radius * std::cos(theta)});
    }
    const auto transform = match.source.size() == 4
        ? homography_from_points(match.source, target_points)
        : affine_from_points(match.source, target_points);
    return warp_homography(out, transform, out_size);
  } catch (const std::exception&) {
    return out;
  }
}

DecodeResult decode_image(const NativeRequest& request) {
  Image image = read_image(request.image);
  if (image.width < 64 || image.height < 64) throw std::runtime_error("image is too small");
  if (request.canonical) return decode_canonical_image(image, request.erasure_threshold);
  double ratio = 1.0;
  Image rectified = rectify_frontal(image, &ratio);
  DecodeResult result = decode_canonical_image(rectified, request.erasure_threshold);
  result.mode = "frontal-affine";
  result.axis_ratio = ratio;
  result.width = image.width;
  result.height = image.height;
  return result;
}

orbiqo::codec::EccLevel parse_ecc(const std::string& value) {
  if (value == "fast") return orbiqo::codec::EccLevel::Fast;
  if (value == "balanced") return orbiqo::codec::EccLevel::Balanced;
  if (value == "robust") return orbiqo::codec::EccLevel::Robust;
  if (value == "extreme") return orbiqo::codec::EccLevel::Extreme;
  throw std::invalid_argument("unsupported ecc");
}

orbiqo::codec::PayloadType parse_payload_type(const std::string& value) {
  if (value == "binary") return orbiqo::codec::PayloadType::Binary;
  if (value == "text" || value == "utf8") return orbiqo::codec::PayloadType::Utf8;
  if (value == "url") return orbiqo::codec::PayloadType::Url;
  throw std::invalid_argument("unsupported payload type");
}

orbiqo::codec::Compression parse_compression(const std::string& value) {
  if (value == "auto") return orbiqo::codec::Compression::Auto;
  if (value == "none") return orbiqo::codec::Compression::None;
  if (value == "deflate") return orbiqo::codec::Compression::Deflate;
  throw std::invalid_argument("unsupported compression");
}

NativeRequest read_request() {
  NativeRequest request;
  std::string line;
  while (std::getline(std::cin, line)) {
    if (line.empty()) continue;
    const std::size_t space = line.find(' ');
    const std::string key = space == std::string::npos ? line : line.substr(0, space);
    const std::string value = space == std::string::npos ? "" : line.substr(space + 1);
    if (key == "OP") request.op = value;
    else if (key == "PAYLOAD_HEX") request.payload = hex_decode(value);
    else if (key == "IMAGE_HEX") request.image = hex_decode(value);
    else if (key == "GEOMETRY") request.geometry = value == "auto" ? -1 : std::stoi(value);
    else if (key == "FORMAT") request.format = std::stoi(value);
    else if (key == "ALPHABET") request.alphabet = value == "mono2" ? orbiqo::codec::Alphabet::Mono2 : orbiqo::codec::Alphabet::Color4;
    else if (key == "PAYLOAD_TYPE") request.payload_type = parse_payload_type(value);
    else if (key == "ECC") request.ecc = parse_ecc(value);
    else if (key == "COMPRESSION") request.compression = parse_compression(value);
    else if (key == "PALETTE") request.palette_id = std::stoi(value);
    else if (key == "DPI") request.render.dpi = std::stoi(value);
    else if (key == "DIAMETER_MM") request.render.diameter_mm = std::stod(value);
    else if (key == "RADIAL_FILL") request.render.radial_fill = std::stod(value);
    else if (key == "ANGULAR_FILL") request.render.angular_fill = std::stod(value);
    else if (key == "BACKGROUND") request.render.background = parse_hex_color(value);
    else if (key == "CENTER_TEXT_B64") {
      const auto decoded = base64_decode(value);
      request.render.center_text.assign(decoded.begin(), decoded.end());
    }
    else if (key == "CENTER_IMAGE_HEX") request.render.center_image = hex_decode(value);
    else if (key == "CANONICAL") request.canonical = value == "1";
    else if (key == "OUTPUT_SIZE") request.output_size = std::stoi(value);
    else if (key == "ERASURE_THRESHOLD") request.erasure_threshold = std::stod(value);
    else if (key == "END") break;
  }
  if (request.op.empty()) throw std::invalid_argument("missing OP");
  return request;
}

orbiqo::codec::EncodedSymbol encode_request(const NativeRequest& request) {
  orbiqo::codec::EncodeOptions options;
  options.format_version = request.format;
  options.alphabet = request.alphabet;
  options.payload_type = request.payload_type;
  options.compression = request.compression;
  options.ecc_level = request.ecc;
  options.palette_id = request.palette_id;
  if (request.geometry >= 0) return orbiqo::codec::encode(request.payload, [&] { options.geometry_version = request.geometry; return options; }());
  const int candidates[7] = {6, 0, 5, 1, 2, 3, 4};
  for (int candidate : candidates) {
    if (request.format <= 3 && candidate > 4) continue;
    try { options.geometry_version = candidate; return orbiqo::codec::encode(request.payload, options); }
    catch (const std::exception&) { continue; }
  }
  throw std::runtime_error("payload does not fit any registered geometry");
}

void print_generate(const orbiqo::codec::EncodedSymbol& symbol, const RenderConfig& config) {
  const Image image = render_raster(symbol, config);
  const auto png = write_png(image);
  const auto svg = render_svg(symbol, config);
  std::cout << "ORBIQO_NATIVE_RESULT_V1\n";
  std::cout << "svg_base64 " << base64_encode(std::vector<std::uint8_t>(svg.begin(), svg.end())) << "\n";
  std::cout << "png_base64 " << base64_encode(png) << "\n";
  std::cout << "format_version " << symbol.header.format_version << "\n";
  std::cout << "geometry_version " << symbol.geometry.version << "\n";
  std::cout << "geometry_name " << geometry_name(symbol.geometry.version) << "\n";
  std::cout << "layout_name " << (symbol.header.format_version >= 3 ? "constant-columns" : "legacy-radial") << "\n";
  std::cout << "columns " << columns_for(symbol.geometry) << "\n";
  std::cout << "data_inner " << symbol.geometry.data_inner << "\n";
  const double effective_diameter = config.diameter_mm > 0.0 ? config.diameter_mm : recommended_diameter(symbol.geometry.version);
  std::cout << "diameter_mm " << effective_diameter << "\n";
  std::cout << "recommended_diameter_mm " << recommended_diameter(symbol.geometry.version) << "\n";
  std::cout << "frame_bytes " << symbol.frame.size() << "\n";
  std::cout << "payload_bytes " << symbol.payload.size() << "\n";
  const int payload_cells = static_cast<int>(std::count_if(symbol.geometry.cells.begin(), symbol.geometry.cells.end(), [](const auto& cell) { return cell.payload; }));
  const int channel_bits = payload_cells * native_bits_per_cell(symbol.header.alphabet);
  const int channel_bytes = channel_bits / 8;
  const int maximum_frame_bytes = native_max_frame_bytes(channel_bytes, symbol.header.ecc_level);
  std::cout << "payload_cells " << payload_cells << "\n";
  std::cout << "channel_bits " << channel_bits << "\n";
  std::cout << "channel_bytes " << channel_bytes << "\n";
  std::cout << "maximum_uncompressed_payload_bytes " << std::max(0, maximum_frame_bytes - 8) << "\n";
  std::cout << "remaining_nominal_payload_bytes " << std::max(0, maximum_frame_bytes - 8 - static_cast<int>(symbol.payload.size())) << "\n";
  std::cout << "mask_id " << symbol.header.mask_id << "\n";
  std::cout << "palette_id " << symbol.header.palette_id << "\n";
  std::cout << "ecc_level " << static_cast<int>(symbol.header.ecc_level) << "\n";
  std::cout << "payload_type " << static_cast<int>(symbol.payload_type) << "\n";
  std::cout << "center_image_applied " << (!config.center_image.empty() ? 1 : 0) << "\n";
  std::cout << "raster_renderer cpp-native-full\nEND\n";
}

void print_normalize(const Image& source) {
  const Image normalized = normalize_image(source);
  std::cout << "ORBIQO_NATIVE_RESULT_V1\n";
  std::cout << "normalized_png_base64 " << base64_encode(write_png(normalized)) << "\n";
  std::cout << "image_width " << source.width << "\n";
  std::cout << "image_height " << source.height << "\n";
  std::cout << "normalized_width " << normalized.width << "\n";
  std::cout << "normalized_height " << normalized.height << "\nEND\n";
}

void print_decode(const DecodeResult& result) {
  std::cout << "ORBIQO_NATIVE_RESULT_V1\n";
  std::cout << "payload_hex " << orbiqo::codec::bytes_to_hex(result.payload) << "\n";
  std::cout << "payload_type " << static_cast<int>(result.payload_type) << "\n";
  std::cout << "format_version " << result.header.format_version << "\n";
  std::cout << "geometry_version " << result.header.geometry_version << "\n";
  std::cout << "alphabet " << static_cast<int>(result.header.alphabet) << "\n";
  std::cout << "palette_id " << result.header.palette_id << "\n";
  std::cout << "ecc_level " << static_cast<int>(result.header.ecc_level) << "\n";
  std::cout << "mask_id " << result.header.mask_id << "\n";
  std::cout << "header_corrected_bits " << result.corrected_header_bits << "\n";
  std::cout << "corrected_rs_symbols " << result.corrected_rs_symbols << "\n";
  std::cout << "erasure_cells " << result.erasure_cells << "\n";
  std::cout << "average_confidence " << result.average_confidence << "\n";
  std::cout << "minimum_confidence " << result.minimum_confidence << "\n";
  std::cout << "image_width " << result.width << "\n";
  std::cout << "image_height " << result.height << "\n";
  std::cout << "rectification_mode " << result.mode << "\n";
  std::cout << "axis_ratio " << result.axis_ratio << "\nEND\n";
}

}  // namespace

int main() {
  try {
    const NativeRequest request = read_request();
    if (request.op == "generate") print_generate(encode_request(request), request.render);
    else if (request.op == "normalize") print_normalize(read_image(request.image));
    else if (request.op == "decode") print_decode(decode_image(request));
    else throw std::invalid_argument("unsupported native operation");
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "orbiqo_native error: " << error.what() << '\n';
    return 1;
  }
}
