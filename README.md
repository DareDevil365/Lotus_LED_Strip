# 💡 MELK-OA10 Bluetooth LED Strip Controller & Ambient Screen Sync

Control your **MELK-OA10** (`BE:69:29:00:0A:23`) Bluetooth LED Light Strip directly from your Windows PC terminal! Features ultra-smooth **Ambient Screen Color Sync**, **Music Reactive mode**, **Rainbow Cycle**, **Strobe**, **Breathing**, **Favorites**, **Auto-Off Timer**, and more.

---

## 🚀 How to Run

### Option 1: Interactive Menu (Recommended)
```bash
python main.py
```

### ✨ Features at a Glance

| # | Feature | Description |
|---|---------|-------------|
| 1 | 🖥️ Ambient Screen Sync | Captures screen colors in real-time with smooth gradual transitions |
| 2 | 🎨 Set Custom Color | Enter Hex, RGB, HSL, or color names — save to favorites! |
| 3 | 🌈 Color Presets | 12 numbered presets (type `1`–`12` or name) |
| 4 | 🔆 Brightness | 0–100% brightness control |
| 5 | ⚡ Power Control | ON / OFF / Toggle / Auto-Off Timer |
| 6 | 🔍 Bluetooth Scan | Search for nearby BLE devices |
| 7 | 🔌 Reconnect | Retry BLE connection |
| 8 | 🌀 Rainbow Cycle | Smooth automatic color cycling (slow/medium/fast) |
| 9 | ⚡ Strobe / Flash | Rapid flashing at configurable BPM |
| 10 | 💫 Breathing / Pulse | Smooth sinusoidal brightness pulsation |
| 11 | 🎵 Music Reactive | Audio-reactive lighting from microphone input |
| 12 | ⭐ Favorites | Save, load, and delete custom color presets |
| 13 | ✨ Hardware Dynamic Effects | Chase, flow, center-out, spectrum wave (20 firmware modes) |
| 14 | 🌊 Procedural Motion Patterns | Aurora, Fireplace, Pacifica Ocean, Cyberpunk, Lightning (11 modes) |

---

### 🎨 Universal Color Formats (accepted everywhere)

| Format | Examples |
|--------|----------|
| **Color Names** | `red`, `cyan`, `warm white`, `hot pink`, `lavender`, `salmon` |
| **Hex Codes** | `#FF0055`, `FF0055`, `#F05`, `0xFF0055` |
| **RGB Values** | `255, 0, 85` or `255 0 85` or `rgb(255, 0, 85)` |
| **HSL Values** | `hsl(300, 100%, 50%)` |
| **Preset Numbers** | `1` through `12` |

### ⌨️ Global Shortcuts (type from anywhere)
- `on` / `off` — Power control
- `sync` — Start ambient screen sync
- `help` or `?` — Quick reference card
- Any color value — Directly set from main menu (e.g., `red`, `#00ffff`, `10`)

---

### 🌈 Preset List

| # | Name | RGB |
|---|------|-----|
| 1 | Cyberpunk Pink | 255, 0, 128 |
| 2 | Sunset Orange | 255, 90, 0 |
| 3 | Ocean Deep Blue | 0, 180, 255 |
| 4 | Vaporwave Purple | 180, 0, 255 |
| 5 | Emerald Green | 0, 255, 128 |
| 6 | Warm White | 255, 210, 150 |
| 7 | Pure Red | 255, 0, 0 |
| 8 | Pure Green | 0, 255, 0 |
| 9 | Pure Blue | 0, 0, 255 |
| 10 | Cyan Glow | 0, 255, 255 |
| 11 | Golden Amber | 255, 191, 0 |
| 12 | Ice Cold White | 200, 235, 255 |

---

### Option 2: Quick Command-Line Flags

#### 🖥️ Ambient Screen Sync
```bash
python main.py sync                         # Default 30% brightness
python main.py sync --brightness 50         # 50% brightness
python main.py sync --zone center           # Center screen sampling
```

#### ⚡ Power
```bash
python main.py on
python main.py off
```

#### 🌈 Presets
```bash
python main.py preset 10        # Cyan Glow
python main.py preset sunset    # Sunset Orange
```

#### 🎨 Colors
```bash
python main.py color red
python main.py color #FF0055
python main.py color 255 0 85
```

#### 🔆 Brightness
```bash
python main.py brightness 80
```

#### 🌀 Rainbow Cycle
```bash
python main.py rainbow
python main.py rainbow --speed fast
```

#### ✨ Built-in Hardware Dynamic Effects
```bash
python main.py effect 1                    # 7-Color Spectrum Flow
python main.py effect 5 --speed 30         # Dynamic Chase / Flow 1
python main.py effect 7                    # Center-to-Ends Running Lights
python main.py effect 8                    # Ends-to-Center Running Lights
python main.py effect "chase"              # By name search
```

#### 🌊 Procedural Motion Patterns
```bash
python main.py pattern aurora              # Ethereal Aurora Borealis
python main.py pattern campfire            # Organic fire flame flicker
python main.py pattern ocean --speed 0.8   # Gentle Pacifica ocean swell
python main.py pattern cyberpunk           # High-energy Cyberpunk neon
python main.py pattern police              # Alternating emergency strobe
python main.py pattern lightning           # Storm with random thunderbolts
```

#### 🔍 Bluetooth Scanner
```bash
python main.py scan
```

---

## 🌊 Procedural Motion Patterns (Option 14)

| # | Motion Pattern | Description |
|---|----------------|-------------|
| 1 | 🌈 Rainbow Spectrum Wave | Fluid continuous 360° color wheel wave |
| 2 | 🌌 Aurora Borealis | Shifting emerald greens, cyan blues, and deep polar violet |
| 3 | 🔥 Campfire / Fireplace Flicker | Organic randomized flame flicker between crimson, orange, and amber |
| 4 | 🌊 Pacifica / Ocean Waves | Calming gentle tide undulating between cobalt, aqua, and deep seafoam |
| 5 | 🌆 Cyberpunk 2077 Neon | High-contrast electric magenta, cyan, and violet pulse wave |
| 6 | 🚨 Police Emergency Beacon | Rhythmic double/triple flash alternating Red and Blue |
| 7 | 🌅 Sunset & Twilight | Warm golden hour melting into blood orange and twilight violet |
| 8 | ❤️ Bio Heartbeat EKG | Organic double-thump pulse with resting pauses |
| 9 | ⚡ Storm & Lightning | Deep stormy dark blue with realistic randomized lightning strikes |
| 10 | 🟢 Matrix Cyber Rain | Pulsing terminal emerald green with digital phosphor decay |
| 11 | 🌋 Molten Lava Dream | Slow undulating molten magma drifting between crimson and golden amber |

---

## ✨ Built-in Hardware Dynamic Modes (Option 13)

| # | Effect Mode | Description |
|---|-------------|-------------|
| 1 | 7-Color Smooth Spectrum Flow | Seamless crossfade cycling through all colors |
| 2 | 3-Color RGB Smooth Flow | Smooth crossfade between Red, Green, Blue |
| 3 | 7-Color Rainbow Jump | Sharp stepping through 7 vivid colors |
| 4 | 3-Color RGB Jump | Sharp stepping Red -> Green -> Blue |
| 5 | Dynamic Chase / Flow 1 | Light train flowing along the strip |
| 6 | Dynamic Chase / Flow 2 | Fast chasing light animation |
| 7 | Center-to-Ends Running Lights | Starts in middle and splits outwards to both ends |
| 8 | Ends-to-Center Running Lights | Starts from both ends and flows inwards to middle |
| 9 | Meteor / Comet Trail Flow | Trailing comet flow along the strip |
| 10 | Wave / Waterfall Motion | Rippling wave flow motion |
| 11 | 7-Color Strobe / Flash | High energy multi-color strobe |
| 12 | 3-Color RGB Strobe / Flash | Red/Green/Blue alternating strobe |
| 13–19 | Color Pulses (Red..White) | Smooth pulsing breathing on individual colors |
| 20 | White Strobe / Flash | High-speed white strobe |

---

## 🎵 Music Reactive Mode (Optional)

Requires the `sounddevice` package:
```bash
pip install sounddevice
```

Uses your laptop microphone to react to music in real-time:
- **Bass** → warm colors (red/orange)
- **Mid** → green tones
- **Treble** → cool colors (blue/cyan)
- **Volume** → brightness

---

## 🔧 Reliability Features

- **Auto-Reconnect**: If the BLE connection drops, the controller automatically retries up to 3 times with exponential backoff.
- **Graceful Shutdown**: Pending BLE commands are flushed before disconnecting.
- **Connection Health**: Header shows write success rate, uptime, and reconnect count.
- **Anti-Flicker Floor**: Ambient mode never drops LEDs to zero (prevents power cycling).
- **Auto Power-On**: Starting any effect mode automatically powers on the strip.

---

## ⚠️ Important Note About Bluetooth Connections
> **Bluetooth light strips accept only ONE connection at a time.**
> If your phone (or a phone app like *HappyLighting* or *Lotus Lantern*) is connected to the strip in the background, close the app on your phone so your PC can communicate with it.
