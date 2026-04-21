library ieee;
use ieee.std_logic_1164.all;

package vcomponents is
  component xpm_memory_sdpram is
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
  end component;
end package vcomponents;

package body vcomponents is
end package body vcomponents;
