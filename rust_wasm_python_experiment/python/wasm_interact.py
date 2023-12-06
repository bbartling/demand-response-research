from wasmer import Store, Module, Instance
import os
import random

# Function to simulate reading data from a building control system
def read_environmental_data():
    # Simulate data such as current energy usage or temperature
    # In a real scenario, this would interface with building sensors
    return {
        'current_energy_usage': random.uniform(2.0, 10.0),  # Simulated energy usage in kW
        'outside_temperature': random.uniform(10, 35)       # Simulated temperature in Celsius
    }

# Relative path to the WebAssembly module
wasm_path = '../target/wasm32-unknown-unknown/release/smart_building.wasm'
with open(wasm_path, 'rb') as file:
    wasm_bytes = file.read()

# Compile the module
store = Store()
module = Module(store, wasm_bytes)
instance = Instance(module)

# Create a new BuildingSystem
building_system = instance.exports.create_building_system()

# Read environmental data
environmental_data = read_environmental_data()

# Example: Adjust system based on current energy usage
if environmental_data['current_energy_usage'] > 5:
    # High energy usage: Increase CPP signal price to trigger energy-saving mode
    cpp_signal_price = 0.20
else:
    # Normal energy usage: Keep CPP signal price low
    cpp_signal_price = 0.10

cpp_signal_duration = 60  # Duration in minutes

# Adjust building systems based on CPP signal
instance.exports.adjust_systems(building_system, cpp_signal_price, cpp_signal_duration)

# Get the updated state of the building system
hvac_power = instance.exports.get_hvac_power(building_system)
lighting_power = instance.exports.get_lighting_power(building_system)

print(f"HVAC Power: {hvac_power} kW, Lighting Power: {lighting_power} kW")
print(f"Current Energy Usage: {environmental_data['current_energy_usage']} kW")
print(f"Outside Temperature: {environmental_data['outside_temperature']} Celsius")
