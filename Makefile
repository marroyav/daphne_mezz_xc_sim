CXX ?= xcrun --sdk macosx clang++
SDKROOT := $(shell xcrun --sdk macosx --show-sdk-path)
CXXFLAGS ?= -O2 -std=c++17 -isysroot $(SDKROOT) -isystem $(SDKROOT)/usr/include/c++/v1
GHDL ?= ghdl
DAPHNE_FIRMWARE_ROOT ?= ../daphne-firmware
DEADTIME_TB_SRC ?= hdl/multichannel_deadtime_tb.vhd
XPM_GHDL_SRCS = \
	hdl/xpm_vcomponents.vhd \
	hdl/xpm_memory_sdpram.vhd
GHDL_SRCS = \
	$(DAPHNE_FIRMWARE_ROOT)/ip_repo/daphne_ip/rtl/daphne_package.vhd \
	$(DAPHNE_FIRMWARE_ROOT)/rtl/isolated/common/daphne_subsystem_pkg.vhd \
	$(wildcard $(DAPHNE_FIRMWARE_ROOT)/rtl/isolated/common/primitives/fixed_delay_line.vhd) \
	$(wildcard $(DAPHNE_FIRMWARE_ROOT)/rtl/isolated/common/primitives/sample_ring_buffer.vhd) \
	hdl/sync_fifo_fwft.vhd \
	$(DAPHNE_FIRMWARE_ROOT)/rtl/isolated/subsystems/trigger/stc3_record_builder.vhd \
	$(DAPHNE_FIRMWARE_ROOT)/rtl/isolated/subsystems/readout/two_lane_readout_mux.vhd \
	$(DEADTIME_TB_SRC)

all: st_xc_sim

st_xc_sim: src/st_xc_sim.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

deadtime_tb:
	rm -f work-obj08.cf xpm-obj08.cf multichannel_deadtime_tb
	$(GHDL) -a --std=08 --work=xpm $(XPM_GHDL_SRCS)
	$(GHDL) -a --std=08 $(GHDL_SRCS)
	$(GHDL) -e --std=08 multichannel_deadtime_tb

run-deadtime-tb: deadtime_tb
	$(GHDL) -r --std=08 multichannel_deadtime_tb

clean:
	rm -f st_xc_sim multichannel_deadtime_tb work-obj08.cf xpm-obj08.cf
