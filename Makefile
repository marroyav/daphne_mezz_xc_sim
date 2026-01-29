CXX ?= g++
CXXFLAGS ?= -O2 -std=c++17

all: st_xc_sim

st_xc_sim: st_xc_sim.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

clean:
	rm -f st_xc_sim
