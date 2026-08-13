# File: compartment.py
import time
import pwmio
from adafruit_motor import servo
from smart_scale import SmartScale

class MedicineCompartment:
    def __init__(self, box_id, servo_pin, angle_closed, angle_open, 
                 scale_dt, scale_sck, scale_factor, 
                 led_indices, pixels_ref):
        
        self.box_id = box_id
        
        # 1. Servo Motor Setup
        pwm = pwmio.PWMOut(servo_pin, duty_cycle=2 ** 15, frequency=50)
        self.servo = servo.Servo(pwm)
        self.angle_closed = angle_closed
        self.angle_open = angle_open
        self.is_open = False
        self.servo.angle = self.angle_closed 
        
        # 2. Scale Setup (SmartScale Instance)
        self.scale = SmartScale(scale_dt, scale_sck, scale_factor, name=f"Box {box_id+1}")
        self.pill_count = 0
        self.last_weight = 0.0  
        
        # 3. LED Lighting Setup
        self.led_indices = led_indices
        self.pixels = pixels_ref  
        
        # 4. Multi-Alarm Schedule Storage
        self.alarms = [] 
        
    def open_lid(self):
        self.servo.angle = self.angle_open
        self.is_open = True
        
    def close_lid(self):
        self.servo.angle = self.angle_closed
        self.is_open = False
        time.sleep(0.5) 
        
    def refresh_inventory(self):
        """Update weight telemetry and pill count using discrete mathematical quantization."""
        if not self.is_open:
            # Sample multi-reading average using verified robust method
            cw = self.scale.get_weight(samples=15)
            
            # Dynamic zero-threshold filter: Treats noise below half a pill unit weight as absolute zero
            zero_threshold = (self.scale.unit_w / 2) if self.scale.unit_w > 0.05 else 0.2
            if abs(cw) < zero_threshold: 
                cw = 0.0
                
            self.last_weight = cw
            
            # Precisely calculate discrete pill count via mathematical rounding
            if self.scale.unit_w > 0.05:
                self.pill_count = int(round(self.last_weight / self.scale.unit_w))
                if self.pill_count < 0: 
                    self.pill_count = 0
        return self.pill_count

    # ----------------------------------------
    # Multi-Alarm Schedule Methods
    # ----------------------------------------
    def add_alarm(self, hour, minute):
        self.alarms.append({"h": hour, "m": minute, "taken": False})
        
    def clear_alarms(self):
        self.alarms = []

    def is_time_for_medicine(self, current_h, current_m):
        for alarm in self.alarms:
            if alarm["h"] == current_h and alarm["m"] == current_m and not alarm["taken"]:
                return True
        return False
        
    def mark_medicine_taken(self, current_h, current_m):
        for alarm in self.alarms:
            if alarm["h"] == current_h and alarm["m"] == current_m:
                alarm["taken"] = True
                
    def reset_daily_alarms(self, current_h, current_m):
        for alarm in self.alarms:
            if current_h != alarm["h"] or current_m != alarm["m"]:
                alarm["taken"] = False

    # ----------------------------------------
    # UI & Lighting Control Methods
    # ----------------------------------------
    def set_setup_step(self, step_num):
        for idx in self.led_indices:
            self.pixels[idx] = (0, 0, 0)
        if 1 <= step_num <= len(self.led_indices):
            target_pixel = self.led_indices[step_num - 1]
            self.pixels[target_pixel] = (0, 100, 255)
        self.pixels.show()

    def set_box_solid_color(self, color):
        for idx in self.led_indices:
            self.pixels[idx] = color
        self.pixels.show()

    def update_leds(self, is_alarm_active, blink_state):
        COLOR_RED    = (255, 0, 0)
        COLOR_YELLOW = (255, 180, 0)
        COLOR_GREEN  = (0, 255, 0)
        COLOR_CYAN   = (0, 255, 255)
        COLOR_OFF    = (0, 0, 0)

        color = COLOR_OFF
        if self.is_open:
            color = COLOR_CYAN
        elif is_alarm_active:
            color = COLOR_GREEN if blink_state else COLOR_OFF
        elif self.pill_count <= 0:
            color = COLOR_RED
        else:
            color = COLOR_YELLOW
            
        for idx in self.led_indices:
            self.pixels[idx] = color