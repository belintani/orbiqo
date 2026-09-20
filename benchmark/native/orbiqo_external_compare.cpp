#include <ZXing/BarcodeFormat.h>
#include <ZXing/BitMatrix.h>
#include <ZXing/ByteArray.h>
#include <ZXing/ImageView.h>
#include <ZXing/MultiFormatWriter.h>
#include <ZXing/ReadBarcode.h>
#include <ZXing/ReaderOptions.h>
#include <ZXing/Result.h>
#include <png.h>

#include <chrono>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;

std::vector<std::uint8_t> hex_decode(const std::string& value) {
  if (value.size() % 2 != 0) throw std::invalid_argument("payload hex must have even length");
  std::vector<std::uint8_t> result;
  result.reserve(value.size() / 2);
  auto nibble = [](char c) -> int {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
  };
  for (std::size_t index = 0; index < value.size(); index += 2) {
    const int high = nibble(value[index]);
    const int low = nibble(value[index + 1]);
    if (high < 0 || low < 0) throw std::invalid_argument("invalid payload hex");
    result.push_back(static_cast<std::uint8_t>((high << 4) | low));
  }
  return result;
}

std::string shell_quote(const fs::path& path) {
  const std::string value = path.string();
  std::string quoted = "'";
  for (const char c : value) {
    if (c == '\'') quoted += "'\\''";
    else quoted += c;
  }
  quoted += "'";
  return quoted;
}

struct ExternalResult {
  std::string format;
  std::string toolchain;
  std::vector<std::uint8_t> payload;
  std::vector<std::uint8_t> decoded;
  int width = 0;
  int height = 0;
  std::vector<std::uint8_t> png;
  double encode_ms = 0.0;
  double decode_ms = 0.0;
};

std::string base64_encode(const std::vector<std::uint8_t>& bytes) {
  static constexpr char alphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string result;
  result.reserve((bytes.size() + 2) / 3 * 4);
  for (std::size_t index = 0; index < bytes.size(); index += 3) {
    const std::uint32_t value = (static_cast<std::uint32_t>(bytes[index]) << 16) |
      (index + 1 < bytes.size() ? static_cast<std::uint32_t>(bytes[index + 1]) << 8 : 0) |
      (index + 2 < bytes.size() ? bytes[index + 2] : 0);
    result.push_back(alphabet[(value >> 18) & 63]);
    result.push_back(alphabet[(value >> 12) & 63]);
    result.push_back(index + 1 < bytes.size() ? alphabet[(value >> 6) & 63] : '=');
    result.push_back(index + 2 < bytes.size() ? alphabet[value & 63] : '=');
  }
  return result;
}

void png_write_callback(png_structp png, png_bytep data, png_size_t length) {
  auto* output = static_cast<std::vector<std::uint8_t>*>(png_get_io_ptr(png));
  output->insert(output->end(), data, data + length);
}

void png_flush_callback(png_structp) {}

std::vector<std::uint8_t> grayscale_png(const std::vector<std::uint8_t>& image, int width, int height) {
  std::vector<std::uint8_t> output;
  png_structp png = png_create_write_struct(PNG_LIBPNG_VER_STRING, nullptr, nullptr, nullptr);
  if (!png) throw std::runtime_error("could not create PNG writer");
  png_infop info = png_create_info_struct(png);
  if (!info) { png_destroy_write_struct(&png, nullptr); throw std::runtime_error("could not create PNG metadata"); }
  if (setjmp(png_jmpbuf(png))) { png_destroy_write_struct(&png, &info); throw std::runtime_error("could not encode PNG"); }
  png_set_write_fn(png, &output, png_write_callback, png_flush_callback);
  png_set_IHDR(png, info, width, height, 8, PNG_COLOR_TYPE_GRAY, PNG_INTERLACE_NONE, PNG_COMPRESSION_TYPE_DEFAULT, PNG_FILTER_TYPE_DEFAULT);
  std::vector<png_bytep> rows(static_cast<std::size_t>(height));
  for (int y = 0; y < height; ++y) rows[static_cast<std::size_t>(y)] = const_cast<png_bytep>(image.data() + static_cast<std::size_t>(y) * width);
  png_set_rows(png, info, rows.data());
  png_write_png(png, info, PNG_TRANSFORM_IDENTITY, nullptr);
  png_destroy_write_struct(&png, &info);
  return output;
}

struct Raster {
  std::vector<std::uint8_t> pixels;
  int width = 0;
  int height = 0;
};

Raster read_png_gray(const fs::path& path) {
  png_image image{};
  image.version = PNG_IMAGE_VERSION;
  if (!png_image_begin_read_from_file(&image, path.c_str())) throw std::runtime_error("could not read PNG");
  image.format = PNG_FORMAT_GRAY;
  Raster result;
  result.width = static_cast<int>(image.width);
  result.height = static_cast<int>(image.height);
  result.pixels.resize(PNG_IMAGE_SIZE(image));
  if (!png_image_finish_read(&image, nullptr, result.pixels.data(), 0, nullptr)) {
    png_image_free(&image);
    throw std::runtime_error("could not decode PNG");
  }
  png_image_free(&image);
  return result;
}

Raster normalize_raster(const Raster& source) {
  constexpr int canvas = 1024;
  constexpr int occupied = 900;
  Raster result;
  result.width = canvas;
  result.height = canvas;
  result.pixels.assign(static_cast<std::size_t>(canvas) * canvas, 255);
  const int offset = (canvas - occupied) / 2;
  for (int y = 0; y < occupied; ++y) for (int x = 0; x < occupied; ++x) {
    const int source_x = std::min(source.width - 1, x * source.width / occupied);
    const int source_y = std::min(source.height - 1, y * source.height / occupied);
    result.pixels[static_cast<std::size_t>(y + offset) * canvas + x + offset] = source.pixels[static_cast<std::size_t>(source_y) * source.width + source_x];
  }
  return result;
}

ExternalResult zxing_roundtrip(const std::string& format, const std::vector<std::uint8_t>& payload) {
  const auto barcode_format = format == "qr" ? ZXing::BarcodeFormat::QRCode : ZXing::BarcodeFormat::Aztec;
  const std::string contents(reinterpret_cast<const char*>(payload.data()), payload.size());
  const auto encode_start = Clock::now();
  ZXing::MultiFormatWriter writer(barcode_format);
  writer.setMargin(4);
  const auto matrix = writer.encode(contents, 0, 0);
  const int scale = 8;
  const int width = matrix.width() * scale;
  const int height = matrix.height() * scale;
  std::vector<std::uint8_t> image(static_cast<std::size_t>(width) * height, 255);
  for (int y = 0; y < height; ++y) for (int x = 0; x < width; ++x) {
    image[static_cast<std::size_t>(y) * width + x] = matrix.get(x / scale, y / scale) ? 0 : 255;
  }
  const auto encode_end = Clock::now();

  const auto decode_start = Clock::now();
  ZXing::ImageView view(image.data(), width, height, ZXing::ImageFormat::Lum);
  ZXing::ReaderOptions options;
  options.setFormats(ZXing::BarcodeFormats(barcode_format)).setTryRotate(false).setTryInvert(false).setTryHarder(false).setIsPure(true);
  const auto decoded = ZXing::ReadBarcode(view, options);
  const auto decode_end = Clock::now();
  if (!decoded.isValid()) throw std::runtime_error(format + " decode failed: " + decoded.error().msg());
  const auto normalized = normalize_raster(Raster{image, width, height});
  return {
    format,
    "zxing-cpp " + std::string(ZXing::ToString(barcode_format)),
    payload,
    std::vector<std::uint8_t>(decoded.bytes().begin(), decoded.bytes().end()),
    width,
    height,
    grayscale_png(normalized.pixels, normalized.width, normalized.height),
    std::chrono::duration<double, std::milli>(encode_end - encode_start).count(),
    std::chrono::duration<double, std::milli>(decode_end - decode_start).count(),
  };
}

ExternalResult jab_roundtrip(const std::vector<std::uint8_t>& payload, const fs::path& root) {
  const fs::path writer = root / "jabcodeWriter/bin/jabcodeWriter";
  const fs::path reader = root / "jabcodeReader/bin/jabcodeReader";
  if (!fs::is_regular_file(writer) || !fs::is_regular_file(reader)) throw std::runtime_error("JAB writer/reader binaries are not available");
  const fs::path temp = fs::temp_directory_path() / ("orbiqo-native-jab-" + std::to_string(static_cast<long long>(getpid())));
  fs::remove_all(temp);
  fs::create_directories(temp);
  const fs::path source = temp / "payload.bin";
  const fs::path symbol = temp / "symbol.png";
  const fs::path decoded = temp / "decoded.bin";
  { std::ofstream output(source, std::ios::binary); output.write(reinterpret_cast<const char*>(payload.data()), static_cast<std::streamsize>(payload.size())); }
  const auto encode_start = Clock::now();
  const std::string writer_command = shell_quote(writer) + " --input-file " + shell_quote(source) + " --output " + shell_quote(symbol) + " --color-number 4 --module-size 8 >/dev/null 2>&1";
  if (std::system(writer_command.c_str()) != 0 || !fs::is_regular_file(symbol)) { fs::remove_all(temp); throw std::runtime_error("JAB writer failed"); }
  const auto encode_end = Clock::now();
  const auto decode_start = Clock::now();
  const std::string reader_command = shell_quote(reader) + " " + shell_quote(symbol) + " --output " + shell_quote(decoded) + " >/dev/null 2>&1";
  if (std::system(reader_command.c_str()) != 0 || !fs::is_regular_file(decoded)) { fs::remove_all(temp); throw std::runtime_error("JAB reader failed"); }
  const auto decode_end = Clock::now();
  std::vector<std::uint8_t> recovered;
  { std::ifstream input(decoded, std::ios::binary); recovered.assign(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()); }
  const auto original = read_png_gray(symbol);
  const auto normalized = normalize_raster(original);
  fs::remove_all(temp);
  return {
    "jab",
    "jabcode CLI official C11 runtime",
    payload,
    recovered,
    original.width,
    original.height,
    grayscale_png(normalized.pixels, normalized.width, normalized.height),
    std::chrono::duration<double, std::milli>(encode_end - encode_start).count(),
    std::chrono::duration<double, std::milli>(decode_end - decode_start).count(),
  };
}

int main(int argc, char** argv) {
  try {
    if (argc < 3) throw std::invalid_argument("usage: orbiqo_external_compare FORMAT PAYLOAD_HEX [JAB_ROOT]");
    const std::string format = argv[1];
    const auto payload = hex_decode(argv[2]);
    ExternalResult result;
    if (format == "qr" || format == "aztec") result = zxing_roundtrip(format, payload);
    else if (format == "jab") result = jab_roundtrip(payload, argc >= 4 ? fs::path(argv[3]) : fs::path("benchmark/jabcode-runtime"));
    else throw std::invalid_argument("unsupported external format");
    std::cout << "ORBIQO_EXTERNAL_RESULT_V1\n";
    std::cout << "format " << result.format << "\n";
    std::cout << "toolchain " << result.toolchain << "\n";
    std::cout << "payload_bytes " << result.payload.size() << "\n";
    std::cout << "decoded_bytes " << result.decoded.size() << "\n";
    std::cout << "decode_exact " << (result.payload == result.decoded ? 1 : 0) << "\n";
    std::cout << "width " << result.width << "\n";
    std::cout << "height " << result.height << "\n";
    std::cout << "png_base64 " << base64_encode(result.png) << "\n";
    std::cout << std::fixed << std::setprecision(4);
    std::cout << "encode_ms " << result.encode_ms << "\n";
    std::cout << "decode_ms " << result.decode_ms << "\nEND\n";
    return result.payload == result.decoded ? 0 : 2;
  } catch (const std::exception& error) {
    std::cerr << "orbiqo_external_compare error: " << error.what() << '\n';
    return 1;
  }
}
