library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity sync_fifo_fwft is
  generic (
    DATA_WIDTH_G        : positive := 72;
    DEPTH_G             : positive := 4096;
    COUNT_WIDTH_G       : positive := 13;
    PROG_EMPTY_THRESH_G : natural  := 220;
    PROG_FULL_THRESH_G  : natural  := 200
  );
  port (
    clock_i         : in  std_logic;
    reset_i         : in  std_logic;
    sleep_i         : in  std_logic;
    wr_en_i         : in  std_logic;
    din_i           : in  std_logic_vector(DATA_WIDTH_G - 1 downto 0);
    rd_en_i         : in  std_logic;
    dout_o          : out std_logic_vector(DATA_WIDTH_G - 1 downto 0);
    prog_empty_o    : out std_logic;
    prog_full_o     : out std_logic;
    wr_data_count_o : out std_logic_vector(COUNT_WIDTH_G - 1 downto 0)
  );
end entity sync_fifo_fwft;

architecture sim of sync_fifo_fwft is
  type mem_t is array (0 to DEPTH_G - 1) of std_logic_vector(DATA_WIDTH_G - 1 downto 0);
  signal mem_s    : mem_t := (others => (others => '0'));
  signal rd_ptr_s : natural range 0 to DEPTH_G - 1 := 0;
  signal wr_ptr_s : natural range 0 to DEPTH_G - 1 := 0;
  signal count_s  : natural range 0 to DEPTH_G := 0;
begin
  -- Bench-local model note:
  -- The production design uses XPM FIFO sleep as a power-management hint.
  -- Modeling sleep as an immediate hard gate on reads/writes causes the
  -- per-channel FIFO to stop draining whenever the builder returns to
  -- wait4trig, which grossly inflates prog_full losses and does not match the
  -- intended steady-state measurement for this dead-time study. Ignore sleep_i
  -- here and model only the single-clock FWFT storage semantics.
  process (clock_i)
    variable do_read_v  : boolean;
    variable do_write_v : boolean;
    variable next_rd_v  : natural range 0 to DEPTH_G - 1;
    variable next_wr_v  : natural range 0 to DEPTH_G - 1;
    variable next_cnt_v : natural range 0 to DEPTH_G;
  begin
    if rising_edge(clock_i) then
      if reset_i = '1' then
        rd_ptr_s <= 0;
        wr_ptr_s <= 0;
        count_s  <= 0;
      else
        do_read_v  := (rd_en_i = '1' and count_s > 0);
        do_write_v := (wr_en_i = '1' and count_s < DEPTH_G);

        next_rd_v  := rd_ptr_s;
        next_wr_v  := wr_ptr_s;
        next_cnt_v := count_s;

        if do_write_v then
          mem_s(wr_ptr_s) <= din_i;
          if wr_ptr_s = DEPTH_G - 1 then
            next_wr_v := 0;
          else
            next_wr_v := wr_ptr_s + 1;
          end if;
          next_cnt_v := next_cnt_v + 1;
        end if;

        if do_read_v then
          if rd_ptr_s = DEPTH_G - 1 then
            next_rd_v := 0;
          else
            next_rd_v := rd_ptr_s + 1;
          end if;
          next_cnt_v := next_cnt_v - 1;
        end if;

        rd_ptr_s <= next_rd_v;
        wr_ptr_s <= next_wr_v;
        count_s  <= next_cnt_v;
      end if;
    end if;
  end process;

  dout_o <= mem_s(rd_ptr_s) when count_s > 0 else (others => '0');
  prog_empty_o <= '1' when count_s <= PROG_EMPTY_THRESH_G else '0';
  prog_full_o <= '1' when count_s >= PROG_FULL_THRESH_G else '0';
  wr_data_count_o <= std_logic_vector(to_unsigned(count_s, COUNT_WIDTH_G));
end architecture sim;
