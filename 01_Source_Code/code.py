# File: code.py (RTOS + OOP + Fast Hardware + Serial Logging + 30s Clean Logic) Final Golden Code
import time
import board
import digitalio
import analogio
import busio
import os
import wifi
import socketpool
import adafruit_ds3231
import adafruit_ntp
import adafruit_ssd1306
import neopixel
import pyRTOS  
import adafruit_requests

from secrets import secrets
import scale_config as cfg
from compartment import MedicineCompartment

# ==========================================
# 1. Setup OLED Display and RTC Module
# ==========================================
WIDTH = 128
HEIGHT = 64
i2c_oled = busio.I2C(scl=board.GP17, sda=board.GP16)
oled = adafruit_ssd1306.SSD1306_I2C(WIDTH, HEIGHT, i2c_oled)

i2c_rtc = busio.I2C(scl=board.GP7, sda=board.GP6) 
rtc = adafruit_ds3231.DS3231(i2c_rtc)

# ==========================================
# 2. Setup Control Inputs, Buzzer, and NeoPixels
# ==========================================
potentiometer = analogio.AnalogIn(board.GP27)
button = digitalio.DigitalInOut(board.GP18)
button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP 

touch_sensor = digitalio.DigitalInOut(board.GP20)
touch_sensor.direction = digitalio.Direction.INPUT

buzzer = digitalio.DigitalInOut(board.GP19)
buzzer.direction = digitalio.Direction.OUTPUT
buzzer.value = False

pixels = neopixel.NeoPixel(board.GP28, 8, brightness=0.15, auto_write=False)

# ==========================================
# 3. Instantiate Smart Medicine Compartment Objects
# ==========================================
box1 = MedicineCompartment(
    box_id=0, servo_pin=board.GP4, angle_closed=90, angle_open=0,
    scale_dt=board.GP12, scale_sck=board.GP13, scale_factor=cfg.SCALE_2_FACTOR,
    led_indices=[4, 5, 6, 7], pixels_ref=pixels
)

box2 = MedicineCompartment(
    box_id=1, servo_pin=board.GP5, angle_closed=0, angle_open=90,
    scale_dt=board.GP14, scale_sck=board.GP15, scale_factor=cfg.SCALE_1_FACTOR,
    led_indices=[0, 1, 2, 3], pixels_ref=pixels
)

boxes = [box1, box2]

def get_pot_mapped(max_val):
    val = potentiometer.value
    mapped = (val * max_val) // 65536
    if mapped >= max_val: mapped = max_val - 1
    return mapped

def get_next_alarm_string(box, current_h, current_m, url_encoded=False):
    if not box.alarms:
        return "No%20Alarm" if url_encoded else "No Alarm"
    
    current_mins = current_h * 60 + current_m
    future_alarms = []
    all_alarms = []
    
    for a in box.alarms:
        alarm_mins = a['h'] * 60 + a['m']
        all_alarms.append((alarm_mins, a['h'], a['m']))
        if alarm_mins > current_mins:
            future_alarms.append((alarm_mins, a['h'], a['m']))
            
    if future_alarms:
        future_alarms.sort()
        next_a = future_alarms[0]
    else:
        all_alarms.sort()
        next_a = all_alarms[0]
        
    separator = "%3A" if url_encoded else ":"
    return f"{next_a[1]:02d}{separator}{next_a[2]:02d}"

# Fixed overlapping schedules issue: Buzzer triggers independently for 30s per alarm
def evaluate_box_alarm(box, current_h, current_m, current_s):
    current_mins = current_h * 60 + current_m
    untaken = [a for a in box.alarms if not a['taken']]
    
    if not untaken:
        return False, 0, None
        
    is_active = False
    min_elapsed = 9999999
    target_alarm = None

    untaken.sort(key=lambda x: x['h'] * 60 + x['m'])

    for a in untaken:
        alarm_mins = a['h'] * 60 + a['m']
        if current_mins >= alarm_mins and (current_mins - alarm_mins) < 1440:
            is_active = True
            elapsed_sec = (current_mins - alarm_mins) * 60 + current_s
            
            # Retain minimum elapsed time (most recent alarm) to trigger 30s buzzer window
            if elapsed_sec < min_elapsed:
                min_elapsed = elapsed_sec
            
            # Retain oldest untaken alarm to log accurately when patient opens the box
            if target_alarm is None:
                target_alarm = a
                
    if is_active:
        return True, min_elapsed, target_alarm
    return False, 0, None

# ==========================================
# 4. State Machine Variables
# ==========================================
sys_state = "IDLE"          
menu_action = 0             
selected_box = 0            
temp_h = 8                  
temp_m = 0                  

msg_timer = 0
measure_timer = 0
measure_count = 0
sum_w = 0.0
msg_text1 = ""
msg_text2 = ""

blynk_terminal_queue = []

# ==========================================
# 5. System Boot, WiFi Connection, and NTP Time Sync
# ==========================================
oled.fill(0); oled.text("Booting System...", 10, 15, 1)
oled.text("Auto-Taring...", 5, 35, 1); oled.show()

for box in boxes:
    box.scale.boot_tare()

pool = None 

try:
    print(">> Connecting to WiFi...")
    wifi.radio.connect(secrets["ssid"], secrets["password"])
    print(">> WiFi Connected! IP:", wifi.radio.ipv4_address)
    
    pool = socketpool.SocketPool(wifi.radio)
    
    time_synced = False
    ntp_servers = ["time.google.com", "pool.ntp.org"]
    for server_ip in ntp_servers:
        if time_synced: break 
        ntp = adafruit_ntp.NTP(pool, server=server_ip, tz_offset=8) 
        for _ in range(2): 
            try:
                rtc.datetime = ntp.datetime
                oled.fill(0); oled.text("Time Synced!", 25, 25, 1); oled.show(); time.sleep(1)
                time_synced = True
                break
            except Exception: time.sleep(1) 
except Exception as e:
    print("WiFi Error:", e)

# Removed lingering green LED: System reverts to normal state after 30 seconds
def update_running_status_leds(is_alrm1, elapsed1, is_alrm2, elapsed2, current_sec):
    for b_idx in range(2):
        group = boxes[b_idx].led_indices
        is_alrm = is_alrm1 if b_idx == 0 else is_alrm2
        elapsed = elapsed1 if b_idx == 0 else elapsed2
        
        if sys_state != "IDLE" and selected_box == b_idx and sys_state.startswith("SETUP"): continue 
        if sys_state != "IDLE" and selected_box == b_idx and sys_state.startswith("ALARM_SET"): continue

        for p in group: pixels[p] = (0, 0, 0)

        if boxes[b_idx].is_open: 
            color = (0, 255, 255)
            for p in group: pixels[p] = color
        elif is_alrm and elapsed < 30: 
            # Flashing green LED during the initial 30-second alarm window only
            color = (0, 255, 0) if (current_sec % 2 == 0) else (0, 0, 0)
            for p in group: pixels[p] = color
        elif boxes[b_idx].pill_count <= 0: 
            # Revert to solid red if time has passed and compartment is empty
            color = (255, 0, 0) 
            for p in group: pixels[p] = color
        else: 
            # Revert to normal yellow/orange if time has passed and compartment has pills
            color = (255, 180, 0) 
            for p in group: pixels[p] = color
            
    pixels.show()

# ==========================================
# 6. pyRTOS Multitasking Scheduler Tasks
# ==========================================

def task_core_ui(self):
    global sys_state, menu_action, selected_box, temp_h, temp_m
    global msg_timer, measure_timer, measure_count, sum_w, msg_text1, msg_text2
    global blynk_terminal_queue
    
    btn_prev = button.value
    touch_prev = touch_sensor.value
    
    pills_before_open_b1 = -1
    pills_before_open_b2 = -1
    
    yield
    while True:
        now = time.monotonic()
        t = rtc.datetime
        current_sec = t.tm_sec
        blink = (current_sec % 2 == 0)

        btn_curr = button.value
        touch_curr = touch_sensor.value
        btn_pressed = (btn_curr == False and btn_prev == True)
        touch_pressed = (touch_curr == True and touch_prev == False)
        btn_prev = btn_curr
        touch_prev = touch_curr

        for box in boxes:
            box.reset_daily_alarms(t.tm_hour, t.tm_min)

        is_alrm1, elapsed1, active_a1 = evaluate_box_alarm(box1, t.tm_hour, t.tm_min, t.tm_sec)
        is_alrm2, elapsed2, active_a2 = evaluate_box_alarm(box2, t.tm_hour, t.tm_min, t.tm_sec)
        any_alarm = is_alrm1 or is_alrm2

        update_running_status_leds(is_alrm1, elapsed1, is_alrm2, elapsed2, current_sec)
        
        play_buzzer = False
        if is_alrm1 and elapsed1 < 30: play_buzzer = True
        if is_alrm2 and elapsed2 < 30: play_buzzer = True
        buzzer.value = play_buzzer and blink

        show_oled_alarm = False
        alarm_box_name = ""
        # OLED warning displays for 30 seconds only, synchronized with buzzer duration
        if (is_alrm1 and elapsed1 < 30) and (is_alrm2 and elapsed2 < 30):
            show_oled_alarm = True; alarm_box_name = "BOTH"
        elif is_alrm1 and elapsed1 < 30:
            show_oled_alarm = True; alarm_box_name = "BOX 1"
        elif is_alrm2 and elapsed2 < 30:
            show_oled_alarm = True; alarm_box_name = "BOX 2"

        if touch_pressed and sys_state == "IDLE" and not (box1.is_open or box2.is_open):
            if any_alarm:
                if is_alrm1: 
                    pills_before_open_b1 = box1.pill_count
                    box1.open_lid()
                if is_alrm2: 
                    pills_before_open_b2 = box2.pill_count
                    box2.open_lid()
                msg_text1 = "Box Opened"; msg_text2 = "Take your Pill"; msg_timer = now; sys_state = "MSG_DELAY"
                touch_pressed = False 

        oled.fill(0)

        if sys_state == "MSG_DELAY":
            oled.text(msg_text1, 25, 15, 1); oled.text(msg_text2, 10, 35, 1)
            if now - msg_timer >= 2.0: sys_state = "IDLE"

        elif show_oled_alarm and sys_state == "IDLE" and not (box1.is_open or box2.is_open):
            if blink:
                oled.text(f" ({alarm_box_name}) ", 30, 5, 1); oled.text(" TIME FOR PILL! ", 15, 25, 1)
            else:
                oled.text("Tap Sensor", 35, 40, 1); oled.text("to Open", 40, 55, 1)

        elif (box1.is_open or box2.is_open) and sys_state == "IDLE":
            oled.text("Boxes Open", 30, 20, 1); oled.text("Touch to Close", 15, 40, 1)
            if touch_pressed:
                oled.fill(0); oled.text("Updating...", 25, 25, 1); oled.show()
                
                act_h = t.tm_hour; act_m = t.tm_min
                was_b1_open = box1.is_open
                was_b2_open = box2.is_open
                
                if was_b1_open: box1.close_lid()
                if was_b2_open: box2.close_lid()
                
                yield [pyRTOS.timeout(1.5)] 
                
                if was_b1_open:
                    box1.refresh_inventory()
                    if is_alrm1 and active_a1 is not None and box1.pill_count < pills_before_open_b1:
                        active_a1['taken'] = True 
                        
                        # Calculate delay accurately based on actual ingestion time
                        delay_mins = (act_h * 60 + act_m) - (active_a1['h'] * 60 + active_a1['m'])
                        
                        pills_after = box1.pill_count
                        taken_amount = pills_before_open_b1 - pills_after
                        sched_str = f"{active_a1['h']:02d}:{active_a1['m']:02d}"
                        act_str = f"{act_h:02d}:{act_m:02d}"
                        
                        term_msg = f"Box 1 | Sched:{sched_str} | Taken:{act_str} | Delay:{delay_mins}m\n"
                        blynk_terminal_queue.append(term_msg)
                        
                        print(f"DATALOG,Box 1,{sched_str},{act_str},{pills_before_open_b1},{pills_after},{taken_amount},{delay_mins}")

                if was_b2_open:
                    box2.refresh_inventory()
                    if is_alrm2 and active_a2 is not None and box2.pill_count < pills_before_open_b2:
                        active_a2['taken'] = True 
                        
                        delay_mins = (act_h * 60 + act_m) - (active_a2['h'] * 60 + active_a2['m'])
                        
                        pills_after = box2.pill_count
                        taken_amount = pills_before_open_b2 - pills_after
                        sched_str = f"{active_a2['h']:02d}:{active_a2['m']:02d}"
                        act_str = f"{act_h:02d}:{act_m:02d}"
                        
                        term_msg = f"Box 2 | Sched:{sched_str} | Taken:{act_str} | Delay:{delay_mins}m\n"
                        blynk_terminal_queue.append(term_msg)
                        
                        print(f"DATALOG,Box 2,{sched_str},{act_str},{pills_before_open_b2},{pills_after},{taken_amount},{delay_mins}")

                msg_text1 = "Updated!"; msg_text2 = ""; msg_timer = now; sys_state = "MSG_DELAY"

        elif sys_state == "IDLE":
            view_index = get_pot_mapped(3)
            next_b1_alarm_str = get_next_alarm_string(box1, t.tm_hour, t.tm_min, url_encoded=False)
            next_b2_alarm_str = get_next_alarm_string(box2, t.tm_hour, t.tm_min, url_encoded=False)
            
            if view_index == 0:
                time_str = f"Time: {t.tm_hour:02}:{t.tm_min:02}"
                oled.text(time_str, 0, 0, 1)
                oled.text(f"B1 Next: {next_b1_alarm_str}", 0, 15, 1)
                oled.text(f"B2 Next: {next_b2_alarm_str}", 0, 25, 1)
                oled.text("-" * 21, 0, 35, 1)
                oled.text(f"L1: {box1.pill_count} | L2: {box2.pill_count}", 10, 45, 1)
                oled.text("[ MAIN VIEW ]", 25, 55, 1)
            elif view_index == 1:
                oled.text("--- BOX 1 ---", 25, 0, 1)
                oled.text(f"Count: {box1.pill_count} Pills", 0, 15, 1)
                oled.text(f"W: {box1.last_weight:.1f}g", 0, 25, 1)
                oled.text(f"Next: {next_b1_alarm_str}", 0, 35, 1)
                oled.text("[ BOX 1 VIEW ]", 20, 55, 1)
            elif view_index == 2:
                oled.text("--- BOX 2 ---", 25, 0, 1)
                oled.text(f"Count: {box2.pill_count} Pills", 0, 15, 1)
                oled.text(f"W: {box2.last_weight:.1f}g", 0, 25, 1)
                oled.text(f"Next: {next_b2_alarm_str}", 0, 35, 1)
                oled.text("[ BOX 2 VIEW ]", 20, 55, 1)

            if btn_pressed: sys_state = "MAIN_MENU"
            if touch_pressed:
                if view_index == 1: box1.open_lid()
                elif view_index == 2: box2.open_lid()
                elif view_index == 0: box1.refresh_inventory(); box2.refresh_inventory()

        elif sys_state == "MAIN_MENU":
            options = ["1. Setup Pill", "2. Refill Box", "3. Set Alarm", "4. Exit"]
            idx = get_pot_mapped(len(options))
            oled.text("--- MAIN MENU ---", 10, 0, 1)
            for i, opt in enumerate(options):
                prefix = "> " if i == idx else "  "
                oled.text(f"{prefix}{opt}", 0, 15 + (i * 12), 1)
            if touch_pressed: sys_state = "IDLE"
            if btn_pressed:
                if idx == 3: sys_state = "IDLE"
                else: menu_action = idx; sys_state = "SELECT_BOX"

        elif sys_state == "SELECT_BOX":
            selected_box = get_pot_mapped(2)
            oled.text("Select Box:", 10, 10, 1)
            oled.text(f"-> [ BOX {selected_box+1} ] <-", 20, 30, 1)
            oled.text("Btn:OK | Touch:Back", 0, 50, 1)
            if touch_pressed: sys_state = "MAIN_MENU"
            if btn_pressed:
                boxes[selected_box].open_lid()
                if menu_action == 0: sys_state = "SETUP_TARE"; boxes[selected_box].set_setup_step(1)
                elif menu_action == 1: sys_state = "REFILL_WAIT"; boxes[selected_box].set_setup_step(1)
                elif menu_action == 2: sys_state = "ALARM_MENU"

        elif sys_state == "SETUP_TARE":
            oled.text(f"Box {selected_box+1} Scale", 20, 0, 1); oled.text("1. Empty Scale", 15, 20, 1); oled.text("Btn: Tare", 30, 35, 1)
            if touch_pressed: boxes[selected_box].close_lid(); sys_state = "IDLE"
            if btn_pressed:
                oled.fill(0); oled.text("Taring...", 30, 25, 1); oled.show()
                boxes[selected_box].scale.tare(); boxes[selected_box].set_setup_step(2); sys_state = "SETUP_PILLS"

        elif sys_state == "SETUP_PILLS":
            oled.text(f"Box {selected_box+1}:", 0, 0, 1); oled.text("2. Put exactly", 15, 15, 1)
            oled.text(">> 5 PILLS <<", 25, 30, 1); oled.text("Then Press Btn", 15, 45, 1)
            if touch_pressed: boxes[selected_box].close_lid(); sys_state = "IDLE"
            if btn_pressed:
                boxes[selected_box].set_setup_step(3)
                measure_count = 0; sum_w = 0.0; measure_timer = now; sys_state = "SETUP_MEASURE"

        elif sys_state == "SETUP_MEASURE":
            oled.text("Measuring 5 pills", 15, 15, 1); oled.text(f"Wait {5 - (measure_count//2)}s", 35, 35, 1)
            if now - measure_timer >= 0.1:
                measure_timer = now
                sum_w += boxes[selected_box].scale.get_weight(samples=10)
                measure_count += 1
                if measure_count >= 10:
                    total_w = sum_w / 10.0
                    calc_unit = total_w / 5.0
                    boxes[selected_box].scale.unit_w = calc_unit if calc_unit > 0.05 else 0.60
                    boxes[selected_box].close_lid(); boxes[selected_box].set_box_solid_color((0, 255, 0))
                    msg_text1 = "Setup Done!"; msg_text2 = f"1 Pill={boxes[selected_box].scale.unit_w:.2f}g"
                    msg_timer = now; sys_state = "MSG_DELAY"

        elif sys_state == "REFILL_WAIT":
            oled.text(f"Fill Box {selected_box+1}", 25, 15, 1); oled.text("Push Btn = Done", 15, 35, 1)
            if touch_pressed: boxes[selected_box].close_lid(); sys_state = "IDLE"
            if btn_pressed:
                boxes[selected_box].set_setup_step(2)
                oled.fill(0); oled.text("Updating Scale...", 10, 25, 1); oled.show()
                boxes[selected_box].close_lid(); boxes[selected_box].refresh_inventory()
                boxes[selected_box].set_box_solid_color((0, 255, 0))
                msg_text1 = f"Box {selected_box+1} Refilled!"; msg_text2 = f"Total: {boxes[selected_box].pill_count} Pills"
                msg_timer = now; sys_state = "MSG_DELAY"

        elif sys_state == "ALARM_MENU":
            opts = ["1. View Alarms", "2. Add Alarm", "3. Clear All", "4. Back"]
            idx = get_pot_mapped(len(opts))
            oled.text(f"-- BOX {selected_box+1} ALARMS --", 5, 0, 1)
            for i, opt in enumerate(opts):
                prefix = "> " if i == idx else "  "
                oled.text(f"{prefix}{opt}", 0, 15 + (i * 12), 1)
            if touch_pressed: boxes[selected_box].close_lid(); sys_state = "IDLE"
            if btn_pressed:
                if idx == 3: boxes[selected_box].close_lid(); sys_state = "IDLE"
                elif idx == 2: 
                    boxes[selected_box].clear_alarms()
                    msg_text1 = "Alarms Cleared!"; msg_text2 = ""; msg_timer = now; sys_state = "MSG_DELAY"
                elif idx == 1: boxes[selected_box].set_setup_step(1); temp_h = 8; sys_state = "ALARM_SET_H"
                elif idx == 0: sys_state = "ALARM_VIEW"

        elif sys_state == "ALARM_VIEW":
            box = boxes[selected_box]
            oled.text(f"Box {selected_box+1} Alarms:", 5, 0, 1)
            if len(box.alarms) == 0: oled.text("No Alarms Set", 25, 25, 1)
            else:
                y_pos = 15
                for i, alrm in enumerate(box.alarms):
                    if y_pos > 45: oled.text("... and more", 10, y_pos, 1); break
                    oled.text(f"{i+1}. {alrm['h']:02}:{alrm['m']:02}", 10, y_pos, 1); y_pos += 12
            oled.text("Btn/Touch to Back", 5, 55, 1)
            if btn_pressed or touch_pressed: sys_state = "ALARM_MENU"

        elif sys_state == "ALARM_SET_H":
            temp_h = get_pot_mapped(24)
            oled.text("Set Hour:", 10, 0, 1); oled.text(f"-> {temp_h:02} <-", 45, 25, 1)
            if touch_pressed: sys_state = "ALARM_MENU"
            if btn_pressed: boxes[selected_box].set_setup_step(2); temp_m = 0; sys_state = "ALARM_SET_M"

        elif sys_state == "ALARM_SET_M":
            temp_m = get_pot_mapped(60)
            oled.text("Set Minute:", 10, 0, 1); oled.text(f"{temp_h:02} : -> {temp_m:02} <-", 25, 25, 1)
            if touch_pressed: sys_state = "ALARM_MENU"
            if btn_pressed:
                boxes[selected_box].add_alarm(temp_h, temp_m)
                boxes[selected_box].set_box_solid_color((0, 255, 0)); boxes[selected_box].close_lid()
                msg_text1 = "Alarm Added!"; msg_text2 = f"Time: {temp_h:02}:{temp_m:02}"; msg_timer = now; sys_state = "MSG_DELAY"

        oled.show()
        yield [pyRTOS.timeout(0.01)] 

def task_blynk_alerts(self):
    global pool, sys_state, selected_box, msg_text1, msg_text2, msg_timer, blynk_terminal_queue
    import gc
    yield
    
    blynk_token = secrets.get("blynk_token", "")
    
    requests_session = None
    if pool is not None:
        requests_session = adafruit_requests.Session(pool)
        
    last_b1_alarm = -1; last_b2_alarm = -1
    last_b1_pills = -1; last_b2_pills = -1
    last_b1_sched = ""; last_b2_sched = ""
    
    task_scheduler = 0 
    
    while True:
        if requests_session is not None and blynk_token:
            t = rtc.datetime
            task_scheduler += 1
            
            if task_scheduler == 1:
                gc.collect()
                if len(blynk_terminal_queue) > 0:
                    try:
                        log_msg = blynk_terminal_queue[0]
                        encoded_msg = log_msg.replace('\n', '%0A').replace(' ', '%20')
                        req_url = f"http://blynk.cloud/external/api/update?token={blynk_token}&v15={encoded_msg}"
                        requests_session.get(req_url, timeout=2).close()
                        print(">> Terminal Updated!")
                        blynk_terminal_queue.pop(0)
                    except Exception as e:
                        pass
                
                yield [pyRTOS.timeout(0.1)]

                try:
                    resp = requests_session.get(f"http://blynk.cloud/external/api/get?token={blynk_token}&v8", timeout=2)
                    raw_v8 = resp.text.replace('[','').replace(']','').replace('"','').strip(); resp.close()
                    if len(raw_v8) >= 4 and ":" in raw_v8:
                        p = raw_v8.split(":")
                        if p[0].isdigit() and p[1].isdigit():
                            boxes[0].add_alarm(int(p[0]), int(p[1]))
                            last_b1_sched = "" 
                            print(f">> Remote Alarm: {p[0]}:{p[1]} added to Box 1!")
                        requests_session.get(f"http://blynk.cloud/external/api/update?token={blynk_token}&v8= ", timeout=2).close()
                except: pass

            elif task_scheduler == 2:
                gc.collect()
                try:
                    resp = requests_session.get(f"http://blynk.cloud/external/api/get?token={blynk_token}&v9", timeout=2)
                    raw_v9 = resp.text.replace('[','').replace(']','').replace('"','').strip(); resp.close()
                    if len(raw_v9) >= 4 and ":" in raw_v9:
                        p = raw_v9.split(":")
                        if p[0].isdigit() and p[1].isdigit():
                            boxes[1].add_alarm(int(p[0]), int(p[1]))
                            last_b2_sched = ""
                            print(f">> Remote Alarm: {p[0]}:{p[1]} added to Box 2!")
                        requests_session.get(f"http://blynk.cloud/external/api/update?token={blynk_token}&v9= ", timeout=2).close()
                except: pass

            elif task_scheduler == 3:
                task_scheduler = 0 
                gc.collect()
                
                current_b1_alarm = 1 if box1.is_time_for_medicine(t.tm_hour, t.tm_min) else 0
                current_b2_alarm = 1 if box2.is_time_for_medicine(t.tm_hour, t.tm_min) else 0
                current_b1_pills = box1.pill_count; current_b2_pills = box2.pill_count
                b1_next_raw = get_next_alarm_string(box1, t.tm_hour, t.tm_min, url_encoded=False)
                b2_next_raw = get_next_alarm_string(box2, t.tm_hour, t.tm_min, url_encoded=False)
                
                yield [pyRTOS.timeout(0.1)]
                
                if current_b1_alarm != last_b1_alarm:
                    try:
                        requests_session.get(f"http://blynk.cloud/external/api/logEvent?token={blynk_token}&code=box_1_alarm&v0={current_b1_alarm}", timeout=2).close()
                        last_b1_alarm = current_b1_alarm 
                    except: pass
                        
                if current_b2_alarm != last_b2_alarm:
                    try:
                        requests_session.get(f"http://blynk.cloud/external/api/logEvent?token={blynk_token}&code=box_2_alarm&v1={current_b2_alarm}", timeout=2).close()
                        last_b2_alarm = current_b2_alarm
                    except: pass

                yield [pyRTOS.timeout(0.1)]

                if current_b1_pills != last_b1_pills:
                    try:
                        requests_session.get(f"http://blynk.cloud/external/api/update?token={blynk_token}&v2={current_b1_pills}", timeout=2).close()
                        last_b1_pills = current_b1_pills
                    except: pass

                if current_b2_pills != last_b2_pills:
                    try:
                        requests_session.get(f"http://blynk.cloud/external/api/update?token={blynk_token}&v3={current_b2_pills}", timeout=2).close()
                        last_b2_pills = current_b2_pills
                    except: pass

                yield [pyRTOS.timeout(0.1)]

                if b1_next_raw != last_b1_sched:
                    try:
                        encoded_sched = b1_next_raw.replace(':', '%3A').replace(' ', '%20')
                        requests_session.get(f"http://blynk.cloud/external/api/update?token={blynk_token}&v4={encoded_sched}", timeout=2).close()
                        last_b1_sched = b1_next_raw
                    except: pass

                if b2_next_raw != last_b2_sched:
                    try:
                        encoded_sched = b2_next_raw.replace(':', '%3A').replace(' ', '%20')
                        requests_session.get(f"http://blynk.cloud/external/api/update?token={blynk_token}&v5={encoded_sched}", timeout=2).close()
                        last_b2_sched = b2_next_raw
                    except: pass
                    
        yield [pyRTOS.timeout(1.0)] 

# ==========================================
# 7. Start pyRTOS Task Scheduler
# ==========================================
try:
    print("Starting pyRTOS with PC Serial Data Logging...")
    pyRTOS.add_task(pyRTOS.Task(task_core_ui, priority=1))
    pyRTOS.add_task(pyRTOS.Task(task_blynk_alerts, priority=2))
    pyRTOS.start()

except KeyboardInterrupt:
    print("\nSystem Stopped.")
    buzzer.value = False
    pixels.fill((0,0,0)); pixels.show()
    oled.fill(0); oled.show()