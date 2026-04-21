library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

library xpm;
use xpm.vcomponents.all;

entity xpm_memory_sdpram is
  generic (
    ADDR_WIDTH_A            : integer := 6;
    ADDR_WIDTH_B            : integer := 6;
    AUTO_SLEEP_TIME         : integer := 0;
    BYTE_WRITE_WIDTH_A      : integer := 32;
    CASCADE_HEIGHT          : integer := 0;
    CLOCKING_MODE           : string  := "common_clock";
    ECC_MODE                : string  := "no_ecc";
    MEMORY_INIT_FILE        : string  := "none";
    MEMORY_INIT_PARAM       : string  := "0";
    MEMORY_OPTIMIZATION     : string  := "true";
    MEMORY_PRIMITIVE        : string  := "auto";
    MEMORY_SIZE             : integer := 2048;
    MESSAGE_CONTROL         : integer := 0;
    READ_DATA_WIDTH_B       : integer := 32;
    READ_LATENCY_B          : integer := 1;
    READ_RESET_VALUE_B      : string  := "0";
    RST_MODE_A              : string  := "SYNC";
    RST_MODE_B              : string  := "SYNC";
    SIM_ASSERT_CHK          : integer := 0;
    USE_EMBEDDED_CONSTRAINT : integer := 0;
    USE_MEM_INIT            : integer := 0;
    WAKEUP_TIME             : string  := "disable_sleep";
    WRITE_DATA_WIDTH_A      : integer := 32;
    WRITE_MODE_B            : string  := "no_change"
  );
  port (
    addra           : in  std_logic_vector(ADDR_WIDTH_A - 1 downto 0);
    addrb           : in  std_logic_vector(ADDR_WIDTH_B - 1 downto 0);
    clka            : in  std_logic;
    clkb            : in  std_logic;
    dbiterrb        : out std_logic;
    dina            : in  std_logic_vector(WRITE_DATA_WIDTH_A - 1 downto 0);
    doutb           : out std_logic_vector(READ_DATA_WIDTH_B - 1 downto 0);
    ena             : in  std_logic;
    enb             : in  std_logic;
    injectdbiterra  : in  std_logic;
    injectsbiterra  : in  std_logic;
    regceb          : in  std_logic;
    rstb            : in  std_logic;
    sbiterrb        : out std_logic;
    sleep           : in  std_logic;
    wea             : in  std_logic_vector((WRITE_DATA_WIDTH_A / BYTE_WRITE_WIDTH_A) - 1 downto 0)
  );
end entity xpm_memory_sdpram;

architecture sim of xpm_memory_sdpram is
  constant DEPTH_C : natural := MEMORY_SIZE / WRITE_DATA_WIDTH_A;
  type mem_t is array (0 to DEPTH_C - 1) of std_logic_vector(WRITE_DATA_WIDTH_A - 1 downto 0);
  signal mem_s     : mem_t := (others => (others => '0'));
  signal dout_s    : std_logic_vector(READ_DATA_WIDTH_B - 1 downto 0) := (others => '0');
begin
  process (clka)
    variable wr_idx_v : natural range 0 to DEPTH_C - 1;
    variable rd_idx_v : natural range 0 to DEPTH_C - 1;
  begin
    if rising_edge(clka) then
      wr_idx_v := to_integer(unsigned(addra));
      rd_idx_v := to_integer(unsigned(addrb));

      if rstb = '1' then
        dout_s <= (others => '0');
      elsif sleep = '0' and enb = '1' and regceb = '1' then
        if ena = '1' and wea /= (wea'range => '0') and wr_idx_v < DEPTH_C then
          mem_s(wr_idx_v) <= dina;
        end if;

        if READ_LATENCY_B = 1 then
          if rd_idx_v < DEPTH_C then
            dout_s <= mem_s(rd_idx_v);
          else
            dout_s <= (others => '0');
          end if;
        else
          assert false report "xpm_memory_sdpram sim stub only supports READ_LATENCY_B=1" severity failure;
        end if;
      end if;
    end if;
  end process;

  doutb    <= dout_s;
  dbiterrb <= '0';
  sbiterrb <= '0';
end architecture sim;
