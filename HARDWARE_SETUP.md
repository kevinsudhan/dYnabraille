# Hardware Setup Guide

## Components Required

### Electronics
- ESP32 Development Board (ESP32-DevKitC or similar)
- 6x 5V Solenoid Actuators (push-pull type recommended)
- 6-Channel 5V Relay Module OR 6x N-Channel MOSFETs (IRLZ44N or similar)
- 5V Power Supply (minimum 2A for solenoids)
- Jumper wires
- Breadboard (optional, for prototyping)

### Optional
- Raspberry Pi 4 (for camera streaming)
- Pi Camera Module V2 or V3
- USB Webcam (alternative to Pi camera)

## Wiring Diagram

### ESP32 to Relay Module

```
ESP32          Relay Module
------         ------------
GPIO 12   -->  IN1 (Solenoid 1 - Dot 1)
GPIO 14   -->  IN2 (Solenoid 2 - Dot 2)
GPIO 27   -->  IN3 (Solenoid 3 - Dot 3)
GPIO 26   -->  IN4 (Solenoid 4 - Dot 4)
GPIO 25   -->  IN5 (Solenoid 5 - Dot 5)
GPIO 33   -->  IN6 (Solenoid 6 - Dot 6)
GND       -->  GND
```

### Power Connections

```
5V Power Supply (+)  -->  Relay Module VCC
5V Power Supply (-)  -->  Relay Module GND & ESP32 GND (common ground)

Each Solenoid:
  One terminal  -->  Relay NO (Normally Open)
  Other terminal -->  5V Power Supply (+)

Relay COM  -->  5V Power Supply (-)
```

### Alternative: Using MOSFETs

```
ESP32 GPIO  -->  MOSFET Gate (through 220Ω resistor)
MOSFET Source  -->  GND
MOSFET Drain  -->  Solenoid (-)
Solenoid (+)  -->  5V Power Supply (+)

Add flyback diode across each solenoid (cathode to +5V, anode to -)
```

## Braille Cell Physical Layout

```
Dot 1 ●    ● Dot 4
Dot 2 ●    ● Dot 5
Dot 3 ●    ● Dot 6
```

Recommended spacing: 2.5mm between dots (standard Braille)

## Assembly Steps

1. **Mount Solenoids**: Arrange 6 solenoids in 3x2 grid matching Braille layout
2. **Connect Relay Module**: Wire ESP32 GPIOs to relay inputs
3. **Power Wiring**: Connect 5V supply to relay module and solenoids
4. **Test Individual Solenoids**: Use Arduino Serial Monitor to test each solenoid
5. **Calibrate Actuation**: Adjust solenoid stroke length if needed

## Raspberry Pi Camera Setup

### Hardware
1. Connect Pi Camera Module to CSI port on Raspberry Pi
2. Enable camera in `raspi-config`
3. Connect Pi to same network as main computer

### Software
```bash
# On Raspberry Pi
pip install -r requirements_pi.txt
python pi_camera_server.py
```

## Testing

### ESP32 Test Commands

Open Arduino Serial Monitor (115200 baud) and send:

```json
{"type":"braille","dots":[1,2,3],"timestamp":0}
```

Expected response:
```json
{"status":"pattern_set","dots":3}
```

### Reset Test
```json
{"type":"reset","timestamp":0}
```

## Troubleshooting

### Solenoids Not Actuating
- Check power supply current rating (min 2A)
- Verify relay module LED indicators
- Test solenoid directly with 5V
- Check common ground between ESP32 and power supply

### ESP32 Not Responding
- Verify serial connection (correct COM port)
- Check baud rate (115200)
- Press EN button to reset ESP32
- Re-upload firmware

### Weak Actuation
- Increase power supply voltage (up to solenoid rating)
- Check wire gauge (use thicker wires for power)
- Reduce actuation duration in firmware

## Safety Notes

- Always use appropriate current ratings for wiring
- Add flyback diodes when using MOSFETs
- Do not exceed solenoid voltage ratings
- Ensure proper ventilation for power supply
- Use insulated connectors for all connections
