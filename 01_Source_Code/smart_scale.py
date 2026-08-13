# File: smart_scale.py
import digitalio
import time

class SmartScale:
    def __init__(self, dt_pin, sck_pin, scale_factor, name="Scale", pill_unit_weight=0.6):
        self.name = name
        self.dt = digitalio.DigitalInOut(dt_pin)
        self.dt.direction = digitalio.Direction.INPUT
        self.sck = digitalio.DigitalInOut(sck_pin)
        self.sck.direction = digitalio.Direction.OUTPUT
        self.sck.value = False
        
        self.scale_factor = scale_factor
        self.tare_value = 0
        self.unit_w = pill_unit_weight  

    def _read(self):
        while self.dt.value: pass
        data = 0
        for _ in range(24):
            self.sck.value = True
            data = (data << 1) | (1 if self.dt.value else 0)
            self.sck.value = False
        self.sck.value = True
        self.sck.value = False
        if data & 0x800000: data -= 0x1000000
        return data

    def boot_tare(self, samples=25):
        time.sleep(0.05)
        readings = [self._read() for _ in range(samples)]
        self.tare_value = sum(readings) / len(readings)

    # Strict compatibility methods to maintain integration with your legacy OLED UI code
    def tare(self, readings=20):
        self.boot_tare(samples=readings)

    def get_units(self, readings=10):
        return self.get_weight(samples=readings)

    def get_weight(self, samples=5):
        readings = [self._read() for _ in range(samples)]
        readings.sort()
        trimmed = readings[1:-1] if len(readings) > 2 else readings
        avg_raw = sum(trimmed) / len(trimmed)
        
        weight = (avg_raw - self.tare_value) / self.scale_factor

        # Forced quantization logic for the box scale (eliminates visual drift during demonstration)
        if self.name == "ميزان العلب":
            if weight < 0.15:
                self.tare_value = (self.tare_value * 0.95) + (avg_raw * 0.05)
                return 0.0
            else:
                quantized = round(weight / self.unit_w) * self.unit_w
                return quantized

        # Logic for standard individual pill weighing scale
        if abs(weight) < 0.20:
            self.tare_value = (self.tare_value * 0.92) + (avg_raw * 0.08)
            return 0.0
            
        return weight if weight >= 0.05 else 0.0