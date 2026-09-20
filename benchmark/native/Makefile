CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -Wpedantic
ZXING_CFLAGS ?= -I/usr/include $(shell pkg-config --cflags zxing)
ZXING_LIBS ?= $(shell pkg-config --libs zxing)
PNG_LIBS ?= -lpng
TARGET := orbiqo_external_compare
SOURCE := orbiqo_external_compare.cpp

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SOURCE)
	$(CXX) $(CXXFLAGS) $(ZXING_CFLAGS) $(SOURCE) -o $(TARGET) $(ZXING_LIBS) $(PNG_LIBS)

clean:
	rm -f $(TARGET)
