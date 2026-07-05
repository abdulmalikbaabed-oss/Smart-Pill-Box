import board
import digitalio
import time

dt = digitalio.DigitalInOut(board.GP14)
dt.direction = digitalio.Direction.INPUT
sck = digitalio.DigitalInOut(board.GP15)
sck.direction = digitalio.Direction.OUTPUT
sck.value = False

def read_hx711():
    while dt.value: pass
    data = 0
    for i in range(24):
        sck.value = True
        data = (data << 1) | (1 if dt.value else 0)
        sck.value = False
    sck.value = True
    sck.value = False
    if data & 0x800000:
        data -= 0x1000000
    return data

# --- المعايرة ---

print("الرجاء إفراغ الميزان للبدء...")
time.sleep(2)
tare_value = sum([read_hx711() for _ in range(10)]) // 10
print(f"تم التصفير! قيمة الصفر (Tare) هي: {tare_value}")

print("الرجاء وضع وزن معلوم (مثلاً 20 جرام) ثم اضغط Enter")
input() # انتظر حتى تضع الوزن
calibration_reading = sum([read_hx711() for _ in range(10)]) // 10
actual_weight = 10.7 # الوزن الذي وضعته بالجرام

# حساب معامل القياس
scale_factor = (calibration_reading - tare_value) / actual_weight
print(f"تمت المعايرة! معامل القياس (Scale Factor) هو: {scale_factor}")

print("جاهز للعمل...")

while True:
    current_raw = read_hx711()
    # الحساب النهائي
    weight = (current_raw - tare_value) / scale_factor
    print(f"الوزن الحالي: {weight:.2f} g")
    time.sleep(0.5)