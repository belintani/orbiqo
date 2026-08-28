#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include <png.h>

namespace {

constexpr double kTau = 6.28318530717958647692;

struct Color {
  std::uint8_t r{};
  std::uint8_t g{};
  std::uint8_t b{};
};

struct Image {
  int width{};
  int height{};
  std::vector<std::uint8_t> pixels;

  Image(int width_in, int height_in, Color fill)
      : width(width_in), height(height_in), pixels(static_cast<std::size_t>(width_in) * height_in * 3U) {
    for (int y = 0; y < height; ++y) {
      for (int x = 0; x < width; ++x) {
        set(x, y, fill);
      }
    }
  }

  void set(int x, int y, Color color) {
    if (x < 0 || y < 0 || x >= width || y >= height) return;
    const std::size_t offset = (static_cast<std::size_t>(y) * width + x) * 3U;
    pixels[offset] = color.r;
    pixels[offset + 1U] = color.g;
    pixels[offset + 2U] = color.b;
  }
};

struct Arc {
  double radius{};
  double width{};
  double start{};
  double end{};
  Color color{};
};

struct DataRing {
  double inner{};
  double outer{};
  int sectors{};
  double angular_fill{};
  double offset{};
  std::string states;
};

bool read_color(std::istringstream& fields, Color* color) {
  int r = 0;
  int g = 0;
  int b = 0;
  if (!(fields >> r >> g >> b) || r < 0 || r > 255 || g < 0 || g > 255 || b < 0 || b > 255) return false;
  *color = Color{static_cast<std::uint8_t>(r), static_cast<std::uint8_t>(g), static_cast<std::uint8_t>(b)};
  return true;
}

void draw_disc(Image* image, double cx, double cy, double radius, Color color) {
  const int min_x = static_cast<int>(std::floor(cx - radius));
  const int max_x = static_cast<int>(std::ceil(cx + radius));
  const int min_y = static_cast<int>(std::floor(cy - radius));
  const int max_y = static_cast<int>(std::ceil(cy + radius));
  const double radius_squared = radius * radius;
  for (int y = min_y; y <= max_y; ++y) {
    for (int x = min_x; x <= max_x; ++x) {
      const double dx = (static_cast<double>(x) + 0.5) - cx;
      const double dy = (static_cast<double>(y) + 0.5) - cy;
      if (dx * dx + dy * dy <= radius_squared) image->set(x, y, color);
    }
  }
}

void draw_ring(Image* image, double center, double radius, double width, Color color) {
  const double half = width / 2.0;
  const int min_x = static_cast<int>(std::floor(center - radius - half));
  const int max_x = static_cast<int>(std::ceil(center + radius + half));
  const int min_y = min_x;
  const int max_y = max_x;
  const double inner = std::max(0.0, radius - half);
  const double outer = radius + half;
  const double inner_sq = inner * inner;
  const double outer_sq = outer * outer;
  for (int y = min_y; y <= max_y; ++y) {
    for (int x = min_x; x <= max_x; ++x) {
      const double dx = (static_cast<double>(x) + 0.5) - center;
      const double dy = (static_cast<double>(y) + 0.5) - center;
      const double distance_sq = dx * dx + dy * dy;
      if (distance_sq >= inner_sq && distance_sq <= outer_sq) image->set(x, y, color);
    }
  }
}

void draw_arc(Image* image, double center, const Arc& arc) {
  const double arc_length = std::max(1.0, std::abs(arc.end - arc.start) * arc.radius);
  const int steps = std::max(2, static_cast<int>(std::ceil(arc_length / 1.25)));
  const double disc_radius = std::max(0.5, arc.width / 2.0);
  for (int step = 0; step <= steps; ++step) {
    const double theta = arc.start + (arc.end - arc.start) * static_cast<double>(step) / static_cast<double>(steps);
    draw_disc(image, center + arc.radius * std::sin(theta), center - arc.radius * std::cos(theta), disc_radius, arc.color);
  }
}

void draw_data(Image* image, double center, const std::vector<DataRing>& rings, const std::vector<Color>& palette) {
  for (int y = 0; y < image->height; ++y) {
    for (int x = 0; x < image->width; ++x) {
      const double dx = (static_cast<double>(x) + 0.5) - center;
      const double dy = center - (static_cast<double>(y) + 0.5);
      const double radius = std::sqrt(dx * dx + dy * dy);
      const DataRing* selected = nullptr;
      for (const DataRing& ring : rings) {
        if (radius >= ring.inner && radius <= ring.outer) {
          selected = &ring;
          break;
        }
      }
      if (selected == nullptr) continue;
      double theta = std::atan2(dx, dy);
      if (theta < 0.0) theta += kTau;
      const double span = kTau / static_cast<double>(selected->sectors);
      double shifted = theta - selected->offset;
      if (shifted < 0.0) shifted += kTau;
      const int sector = std::min(selected->sectors - 1, static_cast<int>(shifted / span));
      const double local = shifted - static_cast<double>(sector) * span;
      const double gutter = span * (1.0 - selected->angular_fill) / 2.0;
      if (local < gutter || local > span - gutter) continue;
      const char state_char = selected->states[static_cast<std::size_t>(sector)];
      if (state_char < '0' || state_char > '9') continue;
      const int state = state_char - '0';
      if (state < 0 || state >= static_cast<int>(palette.size())) continue;
      image->set(x, y, palette[static_cast<std::size_t>(state)]);
    }
  }
}

Image downsample_box(const Image& source, int output_pixels, int supersample) {
  Image output(output_pixels, output_pixels, Color{});
  const int block = std::max(1, supersample);
  const int samples = block * block;
  for (int y = 0; y < output_pixels; ++y) {
    for (int x = 0; x < output_pixels; ++x) {
      int red = 0;
      int green = 0;
      int blue = 0;
      for (int by = 0; by < block; ++by) {
        for (int bx = 0; bx < block; ++bx) {
          const int source_x = std::min(source.width - 1, x * block + bx);
          const int source_y = std::min(source.height - 1, y * block + by);
          const std::size_t offset = (static_cast<std::size_t>(source_y) * source.width + source_x) * 3U;
          red += source.pixels[offset];
          green += source.pixels[offset + 1U];
          blue += source.pixels[offset + 2U];
        }
      }
      output.set(x, y, Color{static_cast<std::uint8_t>(red / samples), static_cast<std::uint8_t>(green / samples), static_cast<std::uint8_t>(blue / samples)});
    }
  }
  return output;
}

bool write_png(const Image& image) {
  png_structp png = png_create_write_struct(PNG_LIBPNG_VER_STRING, nullptr, nullptr, nullptr);
  if (png == nullptr) return false;
  png_infop info = png_create_info_struct(png);
  if (info == nullptr) {
    png_destroy_write_struct(&png, nullptr);
    return false;
  }
  if (setjmp(png_jmpbuf(png)) != 0) {
    png_destroy_write_struct(&png, &info);
    return false;
  }
  png_init_io(png, stdout);
  png_set_IHDR(png, info, image.width, image.height, 8, PNG_COLOR_TYPE_RGB, PNG_INTERLACE_NONE, PNG_COMPRESSION_TYPE_BASE, PNG_FILTER_TYPE_BASE);
  png_write_info(png, info);
  std::vector<png_bytep> rows(static_cast<std::size_t>(image.height));
  for (int row = 0; row < image.height; ++row) rows[static_cast<std::size_t>(row)] = const_cast<png_bytep>(&image.pixels[static_cast<std::size_t>(row) * image.width * 3U]);
  png_write_image(png, rows.data());
  png_write_end(png, info);
  png_destroy_write_struct(&png, &info);
  return true;
}

}  // namespace

int main() {
  std::string line;
  if (!std::getline(std::cin, line) || line != "ORBIQO_RASTER_V1") {
    std::cerr << "expected ORBIQO_RASTER_V1 input\n";
    return 2;
  }

  int pixels = 0;
  int output_pixels = 0;
  int supersample = 0;
  double center = 0.0;
  Color background{};
  Color dark{};
  double guard_radius = 0.0;
  double guard_width = 0.0;
  double center_radius = 0.0;
  double center_border = 0.0;
  bool have_canvas = false;
  bool have_dark = false;
  std::vector<Arc> arcs;
  std::vector<DataRing> data_rings;
  std::vector<Color> palette;

  while (std::getline(std::cin, line)) {
    if (line.empty()) continue;
    std::istringstream fields(line);
    std::string command;
    fields >> command;
    if (command == "END") break;
    if (command == "CANVAS") {
      if (!(fields >> pixels >> output_pixels >> supersample >> center) || !read_color(fields, &background) || pixels <= 0 || output_pixels <= 0 || supersample <= 0 || pixels != output_pixels * supersample) {
        std::cerr << "invalid CANVAS\n";
        return 3;
      }
      have_canvas = true;
    } else if (command == "DARK") {
      if (!read_color(fields, &dark)) {
        std::cerr << "invalid DARK\n";
        return 3;
      }
      have_dark = true;
    } else if (command == "GUARD") {
      if (!(fields >> guard_radius >> guard_width) || guard_radius <= 0.0 || guard_width <= 0.0) {
        std::cerr << "invalid GUARD\n";
        return 3;
      }
    } else if (command == "ARC") {
      Arc arc;
      int rounded = 0;
      if (!(fields >> arc.radius >> arc.width >> arc.start >> arc.end) || !read_color(fields, &arc.color) || !(fields >> rounded) || arc.radius <= 0.0 || arc.width <= 0.0) {
        std::cerr << "invalid ARC\n";
        return 3;
      }
      arcs.push_back(arc);
    } else if (command == "PALETTE") {
      int count = 0;
      if (!(fields >> count) || count < 2 || count > 4) {
        std::cerr << "invalid PALETTE\n";
        return 3;
      }
      palette.clear();
      for (int index = 0; index < count; ++index) {
        Color color;
        if (!read_color(fields, &color)) {
          std::cerr << "invalid PALETTE color\n";
          return 3;
        }
        palette.push_back(color);
      }
    } else if (command == "DATA") {
      DataRing ring;
      if (!(fields >> ring.inner >> ring.outer >> ring.sectors >> ring.angular_fill >> ring.offset >> ring.states) || ring.inner < 0.0 || ring.outer <= ring.inner || ring.sectors <= 0 || ring.angular_fill <= 0.0 || ring.angular_fill > 1.0 || static_cast<int>(ring.states.size()) != ring.sectors) {
        std::cerr << "invalid DATA\n";
        return 3;
      }
      data_rings.push_back(std::move(ring));
    } else if (command == "CENTER") {
      if (!(fields >> center_radius >> center_border) || center_radius <= 0.0 || center_border <= 0.0) {
        std::cerr << "invalid CENTER\n";
        return 3;
      }
    } else {
      std::cerr << "unknown command\n";
      return 3;
    }
  }

  if (!have_canvas || !have_dark || guard_radius <= 0.0 || palette.empty() || center_radius <= 0.0) {
    std::cerr << "incomplete renderer input\n";
    return 4;
  }
  if (pixels > 5000 || output_pixels > 3000) {
    std::cerr << "requested raster is too large\n";
    return 5;
  }

  Image working(pixels, pixels, background);
  draw_ring(&working, center, guard_radius, guard_width, dark);
  for (const Arc& arc : arcs) draw_arc(&working, center, arc);
  draw_data(&working, center, data_rings, palette);
  draw_disc(&working, center, center, center_radius, background);
  draw_ring(&working, center, center_radius, center_border, dark);

  const Image output = downsample_box(working, output_pixels, supersample);
  return write_png(output) ? 0 : 6;
}
