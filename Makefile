CXX ?= xcrun --sdk macosx clang++
SDKROOT := $(shell xcrun --sdk macosx --show-sdk-path)
CXXFLAGS ?= -O2 -std=c++17 -isysroot $(SDKROOT) -isystem $(SDKROOT)/usr/include/c++/v1

all: st_xc_sim

st_xc_sim: src/st_xc_sim.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

clean:
	rm -f st_xc_sim
