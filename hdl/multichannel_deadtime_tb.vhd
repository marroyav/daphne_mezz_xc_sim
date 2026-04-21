library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use ieee.math_real.all;
use std.textio.all;
use std.env.all;

library work;
use work.daphne_package.all;
use work.daphne_subsystem_pkg.all;

entity multichannel_deadtime_tb is
  generic (
    CLOCK_PERIOD_G      : time     := 16 ns;
    CLOCK_HZ_G          : positive := 62500000;
    CHANNEL_COUNT_G     : positive := 40;
    LANE_COUNT_G        : positive := 2;
    CHANNELS_PER_LANE_G : positive := 20;
    TRIGGER_RATE_HZ_G   : positive := 1000;
    RESET_CYCLES_G      : positive := 8;
    WARMUP_CYCLES_G     : positive := 20000;
    MEASURE_CYCLES_G    : positive := 200000;
    SEED_BASE_G         : positive := 101
  );
end entity multichannel_deadtime_tb;

architecture tb of multichannel_deadtime_tb is
  type natural_array_t is array (natural range <>) of natural;

  signal clock_s             : std_logic := '0';
  signal reset_s             : std_logic := '1';
  signal timestamp_s         : std_logic_vector(63 downto 0) := (others => '0');
  signal trigger_s           : trigger_xcorr_result_array_t(0 to CHANNEL_COUNT_G - 1) := (others => TRIGGER_XCORR_RESULT_NULL);
  signal trailer_s           : peak_descriptor_trailer_bank_t(0 to CHANNEL_COUNT_G - 1) := (others => PEAK_DESCRIPTOR_TRAILER_NULL);
  signal frame_match_s       : std_logic_array_t(0 to CHANNEL_COUNT_G - 1);
  signal record_count_s      : slv64_array_t(0 to CHANNEL_COUNT_G - 1);
  signal full_count_s        : slv64_array_t(0 to CHANNEL_COUNT_G - 1);
  signal busy_count_s        : slv64_array_t(0 to CHANNEL_COUNT_G - 1);
  signal trigger_count_s     : slv64_array_t(0 to CHANNEL_COUNT_G - 1);
  signal packet_count_s      : slv64_array_t(0 to CHANNEL_COUNT_G - 1);
  signal delayed_sample_s    : sample14_array_t(0 to CHANNEL_COUNT_G - 1);
  signal ready_s             : std_logic_array_t(0 to CHANNEL_COUNT_G - 1);
  signal rd_en_s             : std_logic_array_t(0 to CHANNEL_COUNT_G - 1);
  signal dout72_s            : slv72_array_t(0 to CHANNEL_COUNT_G - 1);
  signal mux_dout_s          : array_2x64_type;
  signal mux_valid_s         : std_logic_vector(LANE_COUNT_G - 1 downto 0);
  signal mux_last_s          : std_logic_vector(LANE_COUNT_G - 1 downto 0);
begin
  assert CHANNEL_COUNT_G = LANE_COUNT_G * CHANNELS_PER_LANE_G
    report "CHANNEL_COUNT_G must equal LANE_COUNT_G * CHANNELS_PER_LANE_G"
    severity failure;

  clock_s <= not clock_s after CLOCK_PERIOD_G / 2;

  builder_gen : for ch in 0 to CHANNEL_COUNT_G - 1 generate
  begin
    dut_builder : entity work.stc3_record_builder
      port map (
        ch_id_i             => std_logic_vector(to_unsigned(ch, 8)),
        version_i           => x"1",
        threshold_xc_i      => (others => '0'),
        signal_delay_i      => (others => '0'),
        clock_i             => clock_s,
        reset_i             => reset_s,
        reset_st_counters_i => '0',
        enable_i            => '1',
        force_trigger_i     => '0',
        din_i               => (others => '0'),
        trigger_i           => trigger_s(ch),
        trailer_capture_i   => '0',
        trailer_i           => trailer_s(ch),
        frame_match_o       => frame_match_s(ch),
        record_count_o      => record_count_s(ch),
        full_count_o        => full_count_s(ch),
        busy_count_o        => busy_count_s(ch),
        trigger_count_o     => trigger_count_s(ch),
        packet_count_o      => packet_count_s(ch),
        delayed_sample_o    => delayed_sample_s(ch),
        ready_o             => ready_s(ch),
        rd_en_i             => rd_en_s(ch),
        dout_o              => dout72_s(ch)
      );
  end generate builder_gen;

  dut_mux : entity work.two_lane_readout_mux
    generic map (
      CHANNEL_COUNT_G     => CHANNEL_COUNT_G,
      LANE_COUNT_G        => LANE_COUNT_G,
      CHANNELS_PER_LANE_G => CHANNELS_PER_LANE_G
    )
    port map (
      clock_i => clock_s,
      reset_i => reset_s,
      ready_i => ready_s,
      dout_i  => dout72_s,
      rd_en_o => rd_en_s,
      dout_o  => mux_dout_s,
      valid_o => mux_valid_s,
      last_o  => mux_last_s
    );

  stim_proc : process
    type seed_array_t is array (natural range <>) of integer;
    variable seed1_v : seed_array_t(0 to CHANNEL_COUNT_G - 1);
    variable seed2_v : seed_array_t(0 to CHANNEL_COUNT_G - 1);
    variable generated_v : natural_array_t(0 to CHANNEL_COUNT_G - 1) := (others => 0);
    variable lane_sent_v : natural_array_t(0 to LANE_COUNT_G - 1) := (others => 0);
    variable record0_v   : natural_array_t(0 to CHANNEL_COUNT_G - 1) := (others => 0);
    variable busy0_v     : natural_array_t(0 to CHANNEL_COUNT_G - 1) := (others => 0);
    variable full0_v     : natural_array_t(0 to CHANNEL_COUNT_G - 1) := (others => 0);
    variable cyc_v       : natural := 0;
    variable measure_lo_v : natural := RESET_CYCLES_G + WARMUP_CYCLES_G;
    variable measure_hi_v : natural := RESET_CYCLES_G + WARMUP_CYCLES_G + MEASURE_CYCLES_G;
    variable p_v         : real := real(TRIGGER_RATE_HZ_G) / real(CLOCK_HZ_G);
    variable u_v         : real;
    variable trig_v      : trigger_xcorr_result_t;
    variable sum_generated_v : natural;
    variable sum_record_v    : natural;
    variable sum_busy_v      : natural;
    variable sum_full_v      : natural;
    variable sum_sent_v      : natural;
    variable avg_generated_v : natural;
    variable avg_record_v    : natural;
    variable dead_ppm_v      : natural;
    variable line_v          : line;

    function slv64_to_nat(value : std_logic_vector(63 downto 0)) return natural is
    begin
      return to_integer(unsigned(value(30 downto 0)));
    end function;
  begin
    for ch in 0 to CHANNEL_COUNT_G - 1 loop
      seed1_v(ch) := SEED_BASE_G + 17 * ch + 1;
      seed2_v(ch) := SEED_BASE_G + 37 * ch + 11;
    end loop;

    while cyc_v < measure_hi_v + 4 loop
      wait until rising_edge(clock_s);
      cyc_v := cyc_v + 1;

      if cyc_v <= RESET_CYCLES_G then
        reset_s <= '1';
      else
        reset_s <= '0';
      end if;

      if reset_s = '1' then
        timestamp_s <= (others => '0');
      else
        timestamp_s <= std_logic_vector(unsigned(timestamp_s) + 1);
      end if;

      for ch in 0 to CHANNEL_COUNT_G - 1 loop
        trig_v := TRIGGER_XCORR_RESULT_NULL;
        trig_v.enabled := '1';
        trig_v.trigger_timestamp := timestamp_s;
        trig_v.baseline := (others => '0');
        trig_v.monitor_sample := (others => '0');
        trig_v.descriptor_sample := (others => '0');
        trig_v.trigger_sample := std_logic_vector(to_unsigned(ch, 14));

        if cyc_v > RESET_CYCLES_G then
          uniform(seed1_v(ch), seed2_v(ch), u_v);
          if u_v < p_v then
            trig_v.trigger_pulse := '1';
            if cyc_v >= measure_lo_v and cyc_v < measure_hi_v then
              generated_v(ch) := generated_v(ch) + 1;
            end if;
          end if;
        end if;

        trigger_s(ch) <= trig_v;
      end loop;

      if cyc_v = measure_lo_v then
        for ch in 0 to CHANNEL_COUNT_G - 1 loop
          record0_v(ch) := slv64_to_nat(record_count_s(ch));
          busy0_v(ch)   := slv64_to_nat(busy_count_s(ch));
          full0_v(ch)   := slv64_to_nat(full_count_s(ch));
        end loop;
      end if;

      if cyc_v >= measure_lo_v and cyc_v < measure_hi_v then
        for lane in 0 to LANE_COUNT_G - 1 loop
          if mux_last_s(lane) = '1' then
            lane_sent_v(lane) := lane_sent_v(lane) + 1;
          end if;
        end loop;
      end if;
    end loop;

    sum_generated_v := 0;
    sum_record_v := 0;
    sum_busy_v := 0;
    sum_full_v := 0;
    sum_sent_v := 0;

    for ch in 0 to CHANNEL_COUNT_G - 1 loop
      sum_generated_v := sum_generated_v + generated_v(ch);
      sum_record_v := sum_record_v + (slv64_to_nat(record_count_s(ch)) - record0_v(ch));
      sum_busy_v := sum_busy_v + (slv64_to_nat(busy_count_s(ch)) - busy0_v(ch));
      sum_full_v := sum_full_v + (slv64_to_nat(full_count_s(ch)) - full0_v(ch));
    end loop;

    for lane in 0 to LANE_COUNT_G - 1 loop
      sum_sent_v := sum_sent_v + lane_sent_v(lane);
    end loop;

    avg_generated_v := sum_generated_v / CHANNEL_COUNT_G;
    avg_record_v := sum_record_v / CHANNEL_COUNT_G;

    if sum_generated_v = 0 then
      dead_ppm_v := 0;
    else
      dead_ppm_v := ((sum_generated_v - sum_record_v) * 1000000) / sum_generated_v;
    end if;

    write(line_v, string'("RESULT "));
    write(line_v, string'("rate_hz_per_channel="));
    write(line_v, TRIGGER_RATE_HZ_G);
    write(line_v, string'(" channels="));
    write(line_v, CHANNEL_COUNT_G);
    write(line_v, string'(" generated_total="));
    write(line_v, sum_generated_v);
    write(line_v, string'(" accepted_total="));
    write(line_v, sum_record_v);
    write(line_v, string'(" sent_total="));
    write(line_v, sum_sent_v);
    write(line_v, string'(" busy_counter_total="));
    write(line_v, sum_busy_v);
    write(line_v, string'(" full_counter_total="));
    write(line_v, sum_full_v);
    write(line_v, string'(" avg_generated_per_channel="));
    write(line_v, avg_generated_v);
    write(line_v, string'(" avg_accepted_per_channel="));
    write(line_v, avg_record_v);
    write(line_v, string'(" dead_ppm="));
    write(line_v, dead_ppm_v);
    writeline(output, line_v);

    stop;
    wait;
  end process;
end architecture tb;
