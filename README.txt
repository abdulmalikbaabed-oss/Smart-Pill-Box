# 🌟 Comprehensive Operation Guide: Smart Medicine Box Project 🌟

Welcome to the "Smart Medicine Box" project. This embedded system is built on the pyRTOS architecture and object-oriented programming (OOP) using a Raspberry Pi Pico W. The system aims to monitor the elderly's adherence to their medication regimen through weight sensors, synchronize data with the cloud (Blynk IoT), and record it locally in an Excel file.

Follow these engineering steps precisely to build and run the system from scratch:

---

## 🛒 Step 1: Hardware Procurement
Before starting anything, you must ensure you have the necessary electronic components:

1. Go to the `04_Hardware_Schematics` folder and open the **Component List (Excel/PDF)** file.

2. Check the required components (e.g., Raspberry Pi Pico W, HX711, Load Cells, OLED, SG90 Servos, etc.).

3. If any components are missing, order and purchase them online or from local electronics stores before proceeding to the next steps.

---

## 💻 Step Two: Software Transfer
We will now format the system unit (Raspberry Pi Pico W):
1. Connect the Pico W board to your computer until it appears as a storage drive named `CIRCUITPY`.

2. **Transfer Libraries:** Open the `02_Libraries` folder and copy the entire `lib` folder, then paste it into the `CIRCUITPY` directory.

3. **Moving Code:** Open the `01_Source_Code` folder and copy all the Python files (`code.py`, `compartment.py`, `smart_scale.py`, `scale_config.py`, `secrets.py`) and paste them into the root directory of Pico (next to the `lib` folder).

---

## ⚙️ Step Three: Code Customization
You need to modify some data in the code to suit your network and device:

1. **Network and Cloud Settings:** - Open the **`secrets.py`** file located inside Pico.

- Change the following data as needed:

- Line 2: `"ssid": "Your Wi-Fi network name"`

- Line 3: `"password": "Your Wi-Fi password"`

- Line 4: `"blynk_token": "Your Blink token code"`

- Save the file.

2. **Connection Port Settings (for Excel Logging):**

- Open the **`logger.py`** file located in the `03_PC_Data_Logger` folder on your laptop.

- Go to **approximately line 9**: `COM_PORT = 'COM16'`

- Change `'COM16'` to the actual port number that the Pico is connecting to on your computer (you can find this using Thonny or Device Manager).

- Save the file.

---

## 🔌 Step Four: Building the Electronic Circuit (Hardware Wiring)
1. Refer to the components list (Excel) to familiarize yourself with the function of each component and its ports.

2. Open the main electronic schematic **`schematic_circuit.pdf`** located in the `04_Hardware_Schematics` folder.

3. Connect the wires precisely as shown in the schematic (ensure that the 5V power supply is separate from the 3.3V supply to avoid damaging the microcontroller).

---

## ☁️ Step Five: Setting Up the Mobile Application (Blynk IoT Setup)
To create the mobile interface and connect push notifications:

1. Open the `Blynk` folder located inside `04_Hardware_Schematics`.

2. Open the text file **`Blynk_Documentation_and_Event_Setup.txt`**.

3. This file contains a comprehensive engineering guide. Follow the instructions precisely to create Virtual Pins (V0-V15), select the appropriate widgets, and enable notification events to be sent to the patient's phone.

---

## ⚖️ Step Six: Mechanical Assembly and System Operation
1. **Physical Assembly:** Due to the sensitivity of the Load Cell, it must be mounted so that it does not touch the walls of the box. **Refer to the attached illustrations in the project archive** for the correct physical arrangement of the scale and mechanical components.

2. **Starting Data Logging:**

- Ensure that the Thunny program is completely closed to prevent it from blocking the connection.

- Navigate to the `03_PC_Data_Logger` folder.

- Open the Command Prompt (CMD) and run the code using the command: `python logger.py`

- The system will now automatically track and record each pill in the `medication_log.csv` file.

🎉 **Congratulations!** Your system is now ready and operating with high professionalism.