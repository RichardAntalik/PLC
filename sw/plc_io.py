import time
import os
from enum import Enum, auto
from typing import Union, List
import smbus2
import serial

# --- SSHFS Workaround ---
_original_cwd = os.getcwd()
os.chdir('/tmp') 
import lgpio  
os.chdir(_original_cwd)
# -------------------------

class PinMode(Enum):
    INPUT = auto()
    OUTPUT = auto()
    ANALOG_IN = auto()
    PWM = auto()
    UART = auto()
    I2C = auto()

class IO:
    # Module Pin -> RPi GPIO (BCM)
    LOW_VOLTAGE_MAP = {
        1: 13, 2: 19, 3: 26, 4: 21, 
        5: 12, 6: 15, 7: 14, 8: 3, 9: 2
    }
    
    HIGH_VOLTAGE_RELAY_MAP = {
        1: 24, 2: 18, 3: 16, 4: 20
    }
    
    STRONG_PULLUP_MAP = {
        1: 4, 2: 17, 3: 27, 4: 22
    }

    ANALOG_PIN_MAP = {
        1: 1, 2: 0, 3: 2, 4: 3 
    }

    INPUT = PinMode.INPUT
    OUTPUT = PinMode.OUTPUT
    ANALOG_IN = PinMode.ANALOG_IN
    PWM = PinMode.PWM

    def __init__(self):
        self._pin_modes = {}
        self.i2c_bus = None
        self.uart = None
        self.ads1115_addr = 0x48
        
        # Open the GPIO chip (typically 0 on RPi)
        try:
            self.chip = lgpio.gpiochip_open(0)
        except Exception as e:
            print(f"Failed to open GPIO chip: {e}")
            raise

        self._init_hardware()

    def _init_hardware(self):
        """Initializes relays to OFF using lgpio."""
        for r_pin in self.HIGH_VOLTAGE_RELAY_MAP.values():
            # Claim the pin as output and set it LOW (0)
            lgpio.gpio_claim_output(self.chip, r_pin)
            lgpio.gpio_write(self.chip, r_pin, 0)

    def i2c_enable(self):
        self.i2c_bus = smbus2.SMBus(1)

    def function_set(self, pin: int, mode: PinMode):
        if mode in (PinMode.UART, PinMode.I2C):
            if mode == PinMode.UART and self.uart is None:
                self.uart = serial.Serial('/dev/serial0', baudrate=9600, timeout=0.1) 
            return

        rpi_pin = self.LOW_VOLTAGE_MAP.get(pin)
        if rpi_pin is None:
            raise ValueError(f"Invalid low-voltage pin: {pin}")

        self._pin_modes[pin] = mode

        if mode in (PinMode.INPUT, PinMode.ANALOG_IN):
            lgpio.gpio_claim_input(self.chip, rpi_pin)
        elif mode == PinMode.OUTPUT:
            lgpio.gpio_claim_output(self.chip, rpi_pin)
        elif mode == PinMode.PWM:
            # lgpio handles PWM via the gpio_claim_output and tx_pwm methods
            lgpio.gpio_claim_output(self.chip, rpi_pin)

    def pullup_enable(self, pin: int):
        if pin in self.STRONG_PULLUP_MAP:
            sp_pin = self.STRONG_PULLUP_MAP[pin]
            lgpio.gpio_claim_output(self.chip, sp_pin)
            lgpio.gpio_write(self.chip, sp_pin, 0)
        else:
            rpi_pin = self.LOW_VOLTAGE_MAP.get(pin)
            if rpi_pin is not None:
                # lgpio uses specific flags for pull-ups
                pull_flag = lgpio.SET_PULL_UP
                lgpio.gpio_claim_input(self.chip, rpi_pin, pull_flag)

    def pullup_disable(self, pin: int):
        if pin in self.STRONG_PULLUP_MAP:
            sp_pin = self.STRONG_PULLUP_MAP[pin]
            lgpio.gpio_claim_output(self.chip, sp_pin)
            lgpio.gpio_write(self.chip, sp_pin, 1)
        else:
            rpi_pin = self.LOW_VOLTAGE_MAP.get(pin)
            if rpi_pin is not None:
                # lgpio uses specific flags for pull-ups
                pull_flag = lgpio.SET_PULL_NONE
                lgpio.gpio_claim_input(self.chip, rpi_pin, pull_flag)

    def relay_set(self, relay_id: int, state: bool):
        rpi_pin = self.HIGH_VOLTAGE_RELAY_MAP.get(relay_id)
        if rpi_pin is not None:
            lgpio.gpio_write(self.chip, rpi_pin, 1 if state else 0)
        else:
            raise ValueError(f"Invalid relay ID: {relay_id}")

    def set(self, pin: int, state: bool):
        rpi_pin = self.LOW_VOLTAGE_MAP.get(pin)
        if rpi_pin is not None and self._pin_modes.get(pin) == PinMode.OUTPUT:
            lgpio.gpio_write(self.chip, rpi_pin, 1 if state else 0)


    """
    =========================================================================
    ADS1115 Configuration Register Map (16-bit) (LLM GENERATED!!!!)
    =========================================================================
    Base Config used: 0xC183 (Binary: 1100 0001 1000 0011)
    
    When combined with (channel << 12), it configures the ADC as follows:
    
    Bit [15]    OS:  1 = Start a single conversion
    Bit [14:12] MUX: (Set by channel variable)
                     100 = AIN0 vs GND (Channel 0)
                     101 = AIN1 vs GND (Channel 1)
                     110 = AIN2 vs GND (Channel 2)
                     111 = AIN3 vs GND (Channel 3)
    Bit [11:9]  PGA: 000 = +/- 6.144V range
    Bit [8]    MODE:   1 = Single-shot mode (0 = Continuous)
    Bit [7:5]    DR: 100 = 128 Samples Per Second
    Bit [4:0]  COMP: 00011 = Disable comparator (default)
    
    -------------------------------------------------------------------------
    PGA (Voltage Range) Options - Bits [11:9]
    -------------------------------------------------------------------------
    000 : +/- 6.144V (Default)
    001 : +/- 4.096V
    010 : +/- 2.048V
    011 : +/- 1.024V
    100 : +/- 0.512V
    101 : +/- 0.256V
    
    -------------------------------------------------------------------------
    Data Rate (SPS) Options - Bits [7:5]
    -------------------------------------------------------------------------
    000 : 8 SPS     |  100 : 128 SPS (Default)
    001 : 16 SPS    |  101 : 250 SPS
    010 : 32 SPS    |  110 : 475 SPS
    011 : 64 SPS    |  111 : 860 SPS
    =========================================================================
    """

    def read(self, pin: int) -> Union[bool, float]:
        mode = self._pin_modes.get(pin, PinMode.INPUT)
        
        if mode == PinMode.ANALOG_IN:
            if self.i2c_bus is None:
                raise RuntimeError("I2C must be enabled to read analog")
            channel = self.ANALOG_PIN_MAP[pin]
            
            config = 0xC183 | (channel << 12) 
            self.i2c_bus.write_i2c_block_data(self.ads1115_addr, 0x01, [(config >> 8) & 0xFF, config & 0xFF])
            time.sleep(0.015) 
            data = self.i2c_bus.read_i2c_block_data(self.ads1115_addr, 0x00, 2)
            
            # Optional but recommended: handle 16-bit signed integer properly
            raw_val = (data[0] << 8) | data[1]
            if raw_val > 32767:
                raw_val -= 65536
                
            return float(raw_val)

        rpi_pin = self.LOW_VOLTAGE_MAP.get(pin)
        return bool(lgpio.gpio_read(self.chip, rpi_pin))

    def cleanup(self):
        """Safely releases hardware resources."""
        try:
            if hasattr(self, 'i2c_bus') and self.i2c_bus:
                self.i2c_bus.close()
            if hasattr(self, 'uart') and self.uart:
                self.uart.close()
            # This is the important part for lgpio!
            if hasattr(self, 'chip'):
                lgpio.gpiochip_close(self.chip)
        except Exception as e:
            print(f"Cleanup failed: {e}")

    def i2c_write(self, addr: int, reg: int, data: Union[int, List[int]]):
        """Writes data to an I2C device."""
        if not self.i2c_bus:
            raise RuntimeError("I2C not initialized.")
        if isinstance(data, int):
            self.i2c_bus.write_byte_data(addr, reg, data)
        else:
            self.i2c_bus.write_i2c_block_data(addr, reg, data)

    def i2c_read(self, addr: int, reg: int, length: int = 1) -> Union[int, List[int]]:
        """Reads data from an I2C device."""
        if not self.i2c_bus:
            raise RuntimeError("I2C not initialized.")
        if length == 1:
            return self.i2c_bus.read_byte_data(addr, reg)
        return self.i2c_bus.read_i2c_block_data(addr, reg, length)

    def uart_write(self, data: str):
        """Writes a string to the UART interface."""
        if not self.uart:
            raise RuntimeError("UART not initialized.")
        self.uart.write(data.encode('utf-8'))

    def uart_read(self) -> str:
        """Reads a line from the UART interface."""
        if not self.uart:
            raise RuntimeError("UART not initialized.")
        if self.uart.in_waiting > 0:
            return self.uart.readline().decode('utf-8').strip()
        return ""
