from wasmtime import Store, Module, Instance, Engine, Config, Val
import random
import os

def read_environmental_data():
    return {
        'current_energy_usage': random.uniform(2.0, 10.0),  # Simulated energy usage in kW
        'outside_temperature': random.uniform(10, 35)       # Simulated temperature in Celsius
    }

wasm_path = '../target/wasm32-unknown-unknown/release/smart_building.wasm'

config = Config()
store = Store(Engine(config))

with open(wasm_path, 'rb') as file:
    wasm_bytes = file.read()
module = Module(store.engine, wasm_bytes)

imports = []

instance = Instance(store, module, imports)
print("Available exports:", [key for key in instance.exports(store)])


exports = instance.exports(store)
create_building_system = exports["create_building_system"]
adjust_systems = exports["adjust_systems"]
get_hvac_power = exports["get_hvac_power"]
get_lighting_power = exports["get_lighting_power"]
create_cpp_signal = exports["create_cpp_signal"]  # New function to create CPPSignal

building_system = create_building_system(store)

environmental_data = read_environmental_data()


if environmental_data['current_energy_usage'] > 5:
    cpp_signal_price = 0.20
else:
    cpp_signal_price = 0.10

cpp_signal_duration = 60

# Create a CPPSignal struct
cpp_signal = create_cpp_signal(store, Val.f32(cpp_signal_price), Val.i32(cpp_signal_duration))

# Adjust building systems based on CPP signal
# Directly pass 'cpp_signal' which is already a pointer
adjust_systems(store, building_system, cpp_signal)

# Adjust building systems based on CPP signal
adjust_systems(store, building_system, cpp_signal_ptr)

hvac_power = get_hvac_power(store, building_system)
lighting_power = get_lighting_power(store, building_system)

print(f"HVAC Power: {hvac_power} kW, Lighting Power: {lighting_power} kW")
print(f"Current Energy Usage: {environmental_data['current_energy_usage']} kW")
print(f"Outside Temperature: {environmental_data['outside_temperature']} Celsius")
