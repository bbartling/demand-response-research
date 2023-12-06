#[repr(C)]
pub struct BuildingSystem {
    hvac_power: f32,
    lighting_power: f32,
    operational_mode: OperationalMode,
}

#[repr(C)]
pub struct CPPSignal {
    pub price: f32,
    pub duration: u32, // Duration in minutes
}

#[repr(C)]
#[derive(Copy, Clone)]
pub enum OperationalMode {
    Normal,
    EnergySaving,
    MaximumSaving,
}


impl BuildingSystem {
    pub fn new() -> Self {
        BuildingSystem {
            hvac_power: 5.0, // Default power in kW
            lighting_power: 2.0, // Default power in kW
            operational_mode: OperationalMode::Normal,
        }
    }

    pub fn adjust_systems(&mut self, cpp_signal: &CPPSignal) {
        let threshold_price = 0.15; // Define a threshold price for comparison

        if cpp_signal.price > threshold_price {
            self.enter_energy_saving_mode();
        } else {
            self.enter_normal_mode();
        }
    }

    fn enter_energy_saving_mode(&mut self) {
        self.hvac_power *= 0.7; // Reduce HVAC power
        self.lighting_power *= 0.8; // Reduce lighting power
        self.operational_mode = OperationalMode::EnergySaving;
    }

    fn enter_normal_mode(&mut self) {
        self.hvac_power = 5.0;
        self.lighting_power = 2.0;
        self.operational_mode = OperationalMode::Normal;
    }

    pub fn get_operational_mode(&self) -> OperationalMode {
        self.operational_mode
    }
}

// Exported functions...

#[no_mangle]
pub extern "C" fn create_building_system() -> *mut BuildingSystem {
    Box::into_raw(Box::new(BuildingSystem::new()))
}

#[no_mangle]
pub extern "C" fn adjust_systems(building_system: *mut BuildingSystem, cpp_signal: CPPSignal) {
    assert!(!building_system.is_null());
    let building_system = unsafe { &mut *building_system };
    building_system.adjust_systems(&cpp_signal);
}

#[no_mangle]
pub extern "C" fn get_hvac_power(building_system: *const BuildingSystem) -> f32 {
    let building_system = unsafe {
        assert!(!building_system.is_null());
        &*building_system
    };
    building_system.hvac_power
}

#[no_mangle]
pub extern "C" fn get_lighting_power(building_system: *const BuildingSystem) -> f32 {
    let building_system = unsafe {
        assert!(!building_system.is_null());
        &*building_system
    };
    building_system.lighting_power
}

#[no_mangle]
pub extern "C" fn get_operational_mode(building_system: *const BuildingSystem) -> OperationalMode {
    let building_system = unsafe {
        assert!(!building_system.is_null());
        &*building_system
    };
    building_system.get_operational_mode()
}
