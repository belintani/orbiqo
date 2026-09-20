CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -Wpedantic
LDFLAGS ?= -lpng
NATIVE_IMAGE_LIBS ?= -ljpeg -lwebp
FREETYPE_CFLAGS ?= $(shell pkg-config --cflags freetype2 2>/dev/null)
FREETYPE_LIBS ?= $(shell pkg-config --libs freetype2 2>/dev/null || echo -lfreetype)

TARGET := orbiqo_renderer
SOURCE := orbiqo_renderer.cpp
CODEC_TARGET := orbiqo_codec
CODEC_SOURCES := orbiqo_codec.cpp orbiqo_codec_cli.cpp
BENCH_TARGET := orbiqo_codec_bench
BENCH_SOURCES := orbiqo_codec.cpp orbiqo_codec_bench.cpp
NATIVE_TARGET := orbiqo_native
NATIVE_SOURCES := orbiqo_codec.cpp orbiqo_native.cpp

.PHONY: all clean

all: $(TARGET) $(CODEC_TARGET) $(BENCH_TARGET) $(NATIVE_TARGET)

$(TARGET): $(SOURCE)
	$(CXX) $(CXXFLAGS) $(SOURCE) -o $(TARGET) $(LDFLAGS)

$(CODEC_TARGET): $(CODEC_SOURCES) orbiqo_codec.hpp
	$(CXX) $(CXXFLAGS) $(CODEC_SOURCES) -o $(CODEC_TARGET) -lz

$(BENCH_TARGET): $(BENCH_SOURCES) orbiqo_codec.hpp
	$(CXX) $(CXXFLAGS) $(BENCH_SOURCES) -o $(BENCH_TARGET) -lz

$(NATIVE_TARGET): $(NATIVE_SOURCES) orbiqo_codec.hpp
	$(CXX) $(CXXFLAGS) $(FREETYPE_CFLAGS) $(NATIVE_SOURCES) -o $(NATIVE_TARGET) -lz $(LDFLAGS) $(NATIVE_IMAGE_LIBS) $(FREETYPE_LIBS)

clean:
	rm -f $(TARGET) $(CODEC_TARGET) $(BENCH_TARGET) $(NATIVE_TARGET)
