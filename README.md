# Dyna Braille – AI-Powered Dynamic Braille Assistive System

<div align="center">

![Dyna Braille System](FULL%20SYSTEM%20ARC.png)

**Real-time AI-powered assistive technology that converts visual information into dynamic tactile Braille feedback**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![YOLOv8](https://img.shields.io/badge/YOLO-v8-green.svg)](https://github.com/ultralytics/ultralytics)

</div>

## 📖 Overview

**Dyna Braille** is an AI-powered, real-time assistive technology system designed to help visually impaired individuals perceive, understand, and interact with their surroundings through **dynamic tactile Braille feedback** and **audio interaction**. 

Unlike traditional static Braille displays, Dyna Braille converts **live visual information** into **refreshable Braille characters in real time**, allowing users to "feel" their environment as it changes.

The system combines:
- 🎥 **Computer Vision** (YOLO object detection)
- 🤖 **Artificial Intelligence** (LLM voice assistant)
- ⚡ **Embedded Systems** (ESP32 microcontroller)
- 🔧 **Electromechanical Actuation** (Solenoid-based Braille display)
- 📡 **Wireless Communication** (WiFi/HTTP)

---

## 🏗️ System Architecture

Dyna Braille consists of **three major subsystems** working together in a continuous real-time loop:

```
┌─────────────────────────────────────────────────────────────┐
│                    VISION ACQUISITION                        │
│  ESP32-CAM / Raspberry Pi Camera → Live Video Stream        │
└──────────────────────┬──────────────────────────────────────┘
                       │ WiFi/MJPEG
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              AI PROCESSING & INTERPRETATION                  │
│  YOLO Object Detection → Label Extraction → Voice AI        │
└──────────────────────┬──────────────────────────────────────┘
                       │ JSON/HTTP
                       ▼
┌─────────────────────────────────────────────────────────────┐
│          DYNAMIC BRAILLE OUTPUT & VOICE FEEDBACK             │
│  ESP32 Controller → MOSFET Drivers → Solenoid Actuation     │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Key Features

### 1️⃣ Vision Acquisition System

![Wearable Design](WEARABLE.png)

**Hardware Components:**
- ESP32-CAM / Raspberry Pi Camera Module
- Raspberry Pi Zero 2 W
- Ambient light sensor (VEML7700)
- LED illumination system

**Functionality:**
- 📷 **Spectacle-mounted camera** captures live video from user's point of view
- 💡 **Auto-illumination** in low-light conditions using ambient light sensor
- 📡 **WiFi streaming** via MJPEG over HTTPS
- 🔄 **Real-time processing** with minimal latency

### 2️⃣ AI Processing & Object Detection

**Technologies:**
- **YOLO (You Only Look Once)** - State-of-the-art object detection
- **OpenCV** - Image processing pipeline
- **Python** - Processing backend

**Capabilities:**
- ✅ Detects 80+ object classes (COCO dataset)
- ✅ Real-time multi-object detection
- ✅ Bounding box visualization
- ✅ Confidence scoring

**Detected Objects Include:**
- 👤 Person
- 🪑 Chair, Table, Door
- 📱 Phone, Laptop, Keyboard
- 🚗 Vehicles
- 🍎 Food items
- ⚠️ Obstacles

### 3️⃣ AI Voice Assistant

**Technologies:**
- **Ollama** - Local LLM runtime
- **eSpeak** - Text-to-Speech engine
- **Python audio libraries**

**Features:**
- 🗣️ Describes detected objects verbally
- ❓ Answers contextual questions:
  - "What is in front of me?"
  - "Is there a person nearby?"
- 🧠 Provides environmental awareness
- 💬 Interactive conversation

### 4️⃣ Dynamic Braille Display System

![Hardware Build](HARDWARE%20COMPLETED.png)

**The Core Innovation** - Unlike expensive piezoelectric displays, Dyna Braille uses an **affordable electromechanical approach**.

#### Solenoid-Based Braille Actuation

Each Braille character consists of **6 dots** in a **3x2 grid**:

```
Dot 1 ●    ● Dot 4
Dot 2 ●    ● Dot 5
Dot 3 ●    ● Dot 6
```

**Working Principle:**
1. **Solenoids** convert electrical energy → mechanical motion
2. When current flows:
   - Magnetic field created
   - Internal plunger moves **upward**
   - Braille dot **raises**
3. When current stops:
   - Plunger retracts
   - Dot **lowers**

This creates **refreshable Braille characters dynamically**.

#### MOSFET Switching System

![Hardware Pre-Build](HARDWARE%20PRE%20BUILD.png)

**Components:**
- **IRFZ44N** N-Channel MOSFET
- **ESP32** microcontroller
- **5V solenoids**

**Why MOSFETs?**
- ESP32 cannot directly power solenoids (high current requirement)
- MOSFETs act as **electronic switches**

**Operation:**
```
ESP32 GPIO → MOSFET Gate
Gate HIGH → Solenoid ON (dot raised)
Gate LOW → Solenoid OFF (dot lowered)
```

---

## 🖥️ Software Architecture

### Programming Languages

| Language | Purpose |
|----------|---------|
| **Python** | AI processing, object detection, server logic |
| **C/C++** | ESP32 firmware, embedded control |
| **JavaScript** | Web interfaces (optional) |
| **Arduino C** | Hardware control |

### Python Libraries

**Main Application:**
```python
opencv-python    # Camera & computer vision
numpy           # Array operations
PyQt5           # GUI framework
ultralytics     # YOLOv8 model
pyserial        # ESP32 communication
```

**AI Processing:**
```python
ollama          # Local LLM runtime
espeak          # Text-to-speech
```

### Communication Architecture

**Protocols:**
- HTTP/HTTPS
- MJPEG streaming
- JSON data exchange
- Serial communication (ESP32)

**Data Flow:**
```
Camera → AI Server → Braille Conversion → ESP32 → Solenoid Actuation
```

---

## 🎨 User Interface

![Test Interface](TEST%20INTERFACE.png)

**Three-Panel Layout:**

| Panel | Function |
|-------|----------|
| **Left** | Live camera feed with YOLO detection visualization |
| **Center** | Interactive chatbot assistant |
| **Right** | Braille character display (3x2 dot matrix) |

---

## 🔧 Hardware Components

### Electronics
- ESP32 Development Board
- 6× 5V Solenoid Actuators
- 6× IRFZ44N N-Channel MOSFETs
- Relay module (alternative to MOSFETs)
- 5V Power Supply (minimum 2A)
- Custom PCB board
- 3.7V / 5V power system

### Optional
- Raspberry Pi 4 with Camera Module
- ESP32-CAM
- USB Webcam
- Ambient light sensor (VEML7700)

### Wiring Diagram

```
ESP32          MOSFET         Solenoid
------         ------         --------
GPIO 12   →    Gate 1    →    Dot 1
GPIO 14   →    Gate 2    →    Dot 2
GPIO 27   →    Gate 3    →    Dot 3
GPIO 26   →    Gate 4    →    Dot 4
GPIO 25   →    Gate 5    →    Dot 5
GPIO 33   →    Gate 6    →    Dot 6

5V Supply (+) → All Solenoids (+)
MOSFET Drain → Solenoid (-)
MOSFET Source → GND
```

See [HARDWARE_SETUP.md](HARDWARE_SETUP.md) for detailed wiring instructions.

---

## 🚀 Installation & Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Flash ESP32 Firmware

1. Open `esp32_firmware/esp32_braille_controller.ino` in Arduino IDE
2. Install **ArduinoJson** library
3. Select ESP32 board
4. Upload firmware

### 3. Setup Raspberry Pi Camera (Optional)

**On Raspberry Pi:**
```bash
pip install -r requirements_pi.txt
python pi_camera_server.py
```

**On main computer:**
- Update `config.py` with Raspberry Pi IP address

### 4. Run Application

```bash
python main.py
```

---

## 📊 System Specifications

| Specification | Value |
|--------------|-------|
| **Detection FPS** | 15-30 fps |
| **Detection Latency** | < 100ms |
| **Braille Conversion** | < 50ms per character |
| **Object Classes** | 80 (COCO dataset) |
| **Camera Resolution** | 640×480 |
| **Power Consumption** | ~10W (with solenoids) |
| **Communication** | WiFi 802.11 b/g/n |

---

## 🎯 Key Innovations

✨ **Dynamic real-time Braille generation**  
💰 **Affordable solenoid-based display** (vs expensive piezoelectric)  
🤖 **AI-powered object recognition**  
👓 **Wearable spectacle form factor**  
🗣️ **Voice assistant integration**  
⚡ **Low-latency tactile feedback**  
🔌 **Modular architecture**  

---

## 📈 Advantages Over Traditional Systems

| Traditional Braille Displays | Dyna Braille |
|------------------------------|--------------|
| ❌ Static text only | ✅ Dynamic real-time |
| ❌ Expensive ($3000+) | ✅ Affordable (~$100) |
| ❌ Limited functionality | ✅ AI-powered |
| ❌ No environmental awareness | ✅ Context-aware |
| ❌ Desktop-bound | ✅ Wearable |

---

## 🌍 Applications

- 🚶 **Navigation** - Detect obstacles and pathways
- 🔍 **Object Identification** - Recognize everyday items
- 🌐 **Environmental Awareness** - Understand surroundings
- 📚 **Education** - Learn through tactile feedback
- 🏠 **Daily Tasks** - Cooking, cleaning, organizing
- 🚗 **Mobility Assistance** - Safe movement in unfamiliar spaces

---

## 📁 Project Structure

```
Dynabraille/
├── 📄 main.py                      # Application entry point
├── ⚙️ config.py                    # Configuration settings
├── 🎥 yolo_detector.py            # YOLO detection thread
├── 📹 camera_widget.py            # Camera display widget
├── ⠃ braille_widget.py           # Braille display widget
├── 🔤 braille_converter.py        # ASCII to Braille mapping
├── 💬 chatbot_widget.py           # Chat interface
├── 🤖 chatbot_engine.py           # Chatbot logic
├── 🔌 esp32_controller.py         # ESP32 communication
├── 📡 raspberry_pi_camera.py      # Pi camera client
├── 🖥️ pi_camera_server.py         # Pi camera server
├── 🛠️ utils.py                    # Utility functions
├── 🧪 test_braille.py             # Braille tests
├── 🧪 test_esp32.py               # ESP32 tests
├── 📋 requirements.txt            # Python dependencies
├── 📋 requirements_pi.txt         # Raspberry Pi dependencies
├── 📖 README.md                   # This file
├── 📖 HARDWARE_SETUP.md           # Hardware guide
├── 📄 LICENSE                     # MIT License
└── esp32_firmware/
    └── 📟 esp32_braille_controller.ino  # Arduino firmware
```

---

## 🧪 Testing

### Test Braille Conversion
```bash
python test_braille.py
```

### Test ESP32 Communication
```bash
python test_esp32.py
```

### Manual Testing
1. Launch application
2. Point camera at objects
3. Verify detection on left panel
4. Check Braille display on right panel
5. Test chatbot in center panel

---

## 🔮 Future Improvements

- [ ] Reduce latency to < 50ms
- [ ] Miniaturize hardware for better portability
- [ ] Add GPS navigation integration
- [ ] Convert video subtitles to Braille
- [ ] Integrate streaming platform APIs
- [ ] Improve power efficiency
- [ ] Add battery backup
- [ ] Multi-language Braille support
- [ ] Cloud-based detection API
- [ ] Mobile app control

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

**Kevin Sudhan**

- GitHub: [@kevinsudhan](https://github.com/kevinsudhan)
- Repository: [dYnabraille](https://github.com/kevinsudhan/dYnabraille)

---

## 🙏 Acknowledgments

- **Ultralytics** for YOLOv8
- **OpenCV** community
- **PyQt5** developers
- **Arduino** and **ESP32** communities
- All contributors to open-source assistive technology

---

## 📞 Support

If you have any questions or need help, please open an issue in the repository.

---

<div align="center">

**Transforming visual information into tactile and auditory feedback**

**Enabling visually impaired individuals to interact with their environment independently**

Made with ❤️ for accessibility

</div>
