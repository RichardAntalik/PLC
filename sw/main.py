#!/usr/bin/env python3
from plc import PLC
import time, math

start_time = time.time()

def get_temp(adc_val):
    adc_max=15000
    REF_RESISTANCE = 10000.0
    REF_TEMP = 273.15 + 25.0
    BETA = 3950.0
    R_DIV_UPPER = 10000.0
    
    # Avoid division by zero if ADC is at max (infinite resistance)
    if adc_val >= adc_max:
        return float('inf')
    if adc_val <= 0:
        return float('-inf')

    # Calculate resistance of the thermistor (R_lower)
    # Equation: R_lower = R_upper * (V_out / (V_ref - V_out))
    r_div_lower = adc_val * R_DIV_UPPER / (adc_max - adc_val)

    # Beta Equation
    # 1/T = 1/T0 + 1/B * ln(R/R0)
    steinhart = (1.0 / REF_TEMP) + (1.0 / BETA) * math.log(r_div_lower / REF_RESISTANCE)
    
    temp_kelvin = 1.0 / steinhart
    return temp_kelvin - 273.15  # Convert to Celsius

def draw_uptime(plc):
    uptime = time.time() - start_time
    plc.gfx.draw_text(f"Uptime: {uptime:.1f}s", x=10, y=240-16, font_size=10, color=(200, 200, 0))
    plc.gfx.draw_text("System: AUTO", x=240, y=240-16, font_size=10, color=(255, 255, 255))

# Sensors
#########

shower_temp = 0
boiler_temp = 0
exchanger_temp = 0

def shower_temp_sensor(plc):
    global shower_temp
    shower_temp = get_temp(plc.io.read(2))
    plc.gfx.draw_text(f"{shower_temp:.1f}°C", x=70, y=177, font_size=18, color=(255, 255, 255))


def exchanger_input_temp_sensor(plc):
    global exchanger_temp
    exchanger_temp = get_temp(plc.io.read(3))
    plc.gfx.draw_text(f"{exchanger_temp:.1f}°C", x=217, y=115, font_size=18, color=(255, 255, 255))


def boiler_temp_sensor(plc):
    global boiler_temp
    boiler_temp = get_temp(plc.io.read(1))
    plc.gfx.draw_text(f"{boiler_temp:.1f}°C", x=234, y=5, font_size=18, color=(255, 255, 255))

# Outputs
#########

recirc_pump_is_running = False
exchanger_pump_is_running = False

def recirculation_pump(plc):
    global recirc_pump_is_running
    if recirc_pump_is_running:
        plc.gfx.draw_image("assets/pump_on.png", 116, 90)
        plc.io.relay_set(1,1)

    else:
        plc.gfx.draw_image("assets/pump_off.png", 116, 90)
        plc.io.relay_set(1,0)

def exchanger_pump(plc):
    global exchanger_pump_is_running
    hysteresis = -0.5 if exchanger_pump_is_running else 0.5
    boiler_hysteresis = 1 if exchanger_pump_is_running else 1.5

    exchanger_pump_is_running = (
        exchanger_temp > 40 + hysteresis and
        exchanger_temp > boiler_temp + boiler_hysteresis and not
        (shower_temp > boiler_temp and shower_temp > 35)
    )

    #exchanger_pump_is_running = True

    if exchanger_pump_is_running:
        plc.gfx.draw_image("assets/pump_on.png", 86, 122)
        plc.io.relay_set(2,1)
    else:
        plc.gfx.draw_image("assets/pump_off.png", 86, 122)
        plc.io.relay_set(2,0)

def boiler_heater(plc):
    plc.io.relay_set(3,1)


# Init
#########

plc = PLC(logic_freq=2, gfx_freq=10)

plc.io.pullup_enable(1)
plc.io.pullup_enable(2)
plc.io.pullup_enable(3)
plc.io.function_set(1, plc.io.ANALOG_IN)
plc.io.function_set(2, plc.io.ANALOG_IN)
plc.io.function_set(3, plc.io.ANALOG_IN)
plc.io.i2c_enable()

plc.set_background("assets/background.png")

plc.sensor_add(shower_temp_sensor)
plc.sensor_add(exchanger_input_temp_sensor)
plc.sensor_add(boiler_temp_sensor)

plc.output_add(recirculation_pump)
plc.output_add(exchanger_pump)
plc.output_add(boiler_heater)

plc.generic_add(draw_uptime)
plc.plc_start()