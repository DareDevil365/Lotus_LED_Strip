import asyncio
import colorsys
import math
import random
import time
from typing import Callable, Optional, Tuple

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

console = Console()

class MotionPatternEngine:
    """
    High-performance Software Motion Animation Engine.
    Generates rich, organic, dynamic procedural lighting patterns
    including Rainbow Waves, Aurora Borealis, Campfire Flicker, Pacifica Ocean,
    Cyberpunk Neon, Police Strobe, Heartbeat, and Lightning.
    """

    PATTERNS = [
        ("rainbow_wave", "🌈 Rainbow Spectrum Wave", "Fluid continuous movement across the 360° color wheel"),
        ("aurora", "🌌 Aurora Borealis", "Ethereal northern lights with surging emerald, cyan, and violet"),
        ("campfire", "🔥 Campfire / Fireplace Flicker", "Organic randomized flame flickers between crimson, orange, and amber"),
        ("ocean_tide", "🌊 Pacifica / Ocean Waves", "Calming gentle tide undulating between cobalt, aqua, and deep seafoam"),
        ("cyberpunk", "🌆 Cyberpunk 2077 Neon", "High-contrast electric magenta, cyan, and violet pulse wave"),
        ("police", "🚨 Police Emergency Beacon", "Rhythmic double/triple flash alternating Red and Blue"),
        ("sunset", "🌅 Sunset & Twilight", "Warm golden hour melting into blood orange and twilight violet"),
        ("heartbeat", "❤️ Bio Heartbeat EKG", "Organic double-thump pulse with resting pauses"),
        ("lightning", "⚡ Storm & Lightning", "Deep stormy dark blue with realistic randomized lightning strikes"),
        ("matrix", "🟢 Matrix Cyber Rain", "Pulsing terminal emerald green with digital phosphor decay"),
        ("lava_lamp", "🌋 Molten Lava Dream", "Slow undulating molten magma drifting between crimson and golden amber"),
    ]

    def __init__(self, ble_controller, pattern_id: str = "rainbow_wave", speed: float = 1.0, brightness: int = 80):
        self.controller = ble_controller
        self.pattern_id = pattern_id.lower()
        self.speed = max(0.1, min(5.0, float(speed)))
        self.brightness = max(5, min(100, int(brightness))) / 100.0

        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.on_frame_update: Optional[Callable[[Tuple[int, int, int], str], None]] = None

    async def start(self):
        """Start the motion pattern loop."""
        if self.running:
            return
        self.running = True
        if self.controller and self.controller.is_connected:
            await self.controller.set_power(True, immediate=True)
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        """Stop the motion pattern loop."""
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None

    def _compute_frame(self, t: float) -> Tuple[int, int, int]:
        """Compute the RGB color for time t based on selected pattern."""
        pid = self.pattern_id
        b_scale = self.brightness

        # 1. Rainbow Spectrum Wave
        if pid in ["rainbow_wave", "rainbow", "spectrum", "1"]:
            hue = (t * 0.15 * self.speed) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, b_scale)

        # 2. Aurora Borealis (Ethereal polar greens, blues, purples)
        elif pid in ["aurora", "northern_lights", "2"]:
            # Complex overlapping sines for natural wave motion
            h_wave = 0.38 + 0.18 * math.sin(t * 0.4 * self.speed) + 0.08 * math.sin(t * 0.9 * self.speed)
            v_wave = 0.50 + 0.45 * math.sin(t * 0.7 * self.speed) ** 2
            r, g, b = colorsys.hsv_to_rgb(h_wave % 1.0, 0.95, v_wave * b_scale)

        # 3. Campfire / Fireplace Flame Flicker
        elif pid in ["campfire", "fire", "flame", "3"]:
            # Organic noise flicker
            noise1 = math.sin(t * 7.3 * self.speed)
            noise2 = math.sin(t * 13.7 * self.speed)
            noise3 = (random.random() - 0.5) * 0.25
            flicker = 0.65 + 0.20 * noise1 + 0.10 * noise2 + noise3
            flicker = max(0.20, min(1.0, flicker))

            # Hue shifts slightly between deep red-orange (0.02) and warm amber (0.10)
            hue = 0.03 + 0.05 * (math.sin(t * 2.1 * self.speed) * 0.5 + 0.5)
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, flicker * b_scale)

        # 4. Pacifica / Ocean Waves
        elif pid in ["ocean_tide", "ocean", "pacifica", "waves", "4"]:
            # Blue-cyan oceanic swell
            h_ocean = 0.52 + 0.08 * math.sin(t * 0.35 * self.speed)
            v_ocean = 0.40 + 0.55 * (math.sin(t * 0.6 * self.speed) * 0.5 + 0.5)
            r, g, b = colorsys.hsv_to_rgb(h_ocean, 0.90, v_ocean * b_scale)

        # 5. Cyberpunk 2077 Neon Pulse
        elif pid in ["cyberpunk", "neon", "5"]:
            # Alternates smoothly between Electric Magenta (0.88) and Cyber Cyan (0.50)
            phase = (math.sin(t * 0.8 * self.speed) * 0.5 + 0.5)
            h_cyber = 0.88 if phase > 0.5 else 0.50
            # Neon pulse intensity
            v_cyber = 0.60 + 0.40 * (math.sin(t * 3.0 * self.speed) ** 4)
            r, g, b = colorsys.hsv_to_rgb(h_cyber, 1.0, v_cyber * b_scale)

        # 6. Police Emergency Beacon
        elif pid in ["police", "cop", "emergency", "6"]:
            period = 1.0 / self.speed
            sub_t = (t % period) / period
            if sub_t < 0.45:
                # Red burst (3 rapid strobes)
                strobe_sub = (sub_t / 0.45) * 3.0
                on = (strobe_sub % 1.0) < 0.5
                r, g, b = (255, 0, 0) if on else (0, 0, 0)
            elif sub_t < 0.50:
                r, g, b = (0, 0, 0)
            elif sub_t < 0.95:
                # Blue burst (3 rapid strobes)
                strobe_sub = ((sub_t - 0.50) / 0.45) * 3.0
                on = (strobe_sub % 1.0) < 0.5
                r, g, b = (0, 30, 255) if on else (0, 0, 0)
            else:
                r, g, b = (0, 0, 0)
            return int(r * b_scale), int(g * b_scale), int(b * b_scale)

        # 7. Sunset & Twilight Horizon
        elif pid in ["sunset", "twilight", "dusk", "7"]:
            # Glides: Gold (0.12) -> Blood Orange (0.05) -> Rose Pink (0.92) -> Twilight Violet (0.75)
            cycle = (t * 0.05 * self.speed) % 1.0
            if cycle < 0.35:
                h = 0.12 - (cycle / 0.35) * 0.07  # 0.12 to 0.05
            elif cycle < 0.70:
                h = 0.05 - ((cycle - 0.35) / 0.35) * 0.13  # 0.05 to 0.92
            else:
                h = 0.92 - ((cycle - 0.70) / 0.30) * 0.17  # 0.92 to 0.75
            r, g, b = colorsys.hsv_to_rgb(h % 1.0, 0.95, 0.85 * b_scale)

        # 8. Bio Heartbeat Pulse
        elif pid in ["heartbeat", "pulse", "heart", "8"]:
            period = 1.2 / self.speed
            sub_t = (t % period) / period
            # Double beat: lub (at 0.1) and dub (at 0.35)
            if sub_t < 0.15:
                # First thump
                beat = math.sin((sub_t / 0.15) * math.pi)
            elif 0.20 < sub_t < 0.40:
                # Second thump
                beat = math.sin(((sub_t - 0.20) / 0.20) * math.pi) * 0.85
            else:
                beat = 0.08  # Resting floor
            val = max(0.08, beat) * b_scale
            r, g, b = colorsys.hsv_to_rgb(0.99, 1.0, val)

        # 9. Storm & Lightning
        elif pid in ["lightning", "storm", "thunder", "9"]:
            # Dark ominous storm background (deep navy)
            r_base, g_base, b_base = 5, 10, 45
            # Random chance of lightning strike burst
            if random.random() < (0.04 * self.speed):
                # Bright lightning flash
                flash = random.choice([255, 230, 200])
                r, g, b = flash, flash, int(flash * 0.95)
            else:
                r, g, b = r_base, g_base, b_base
            return int(r * b_scale), int(g * b_scale), int(b * b_scale)

        # 10. Matrix Cyber Rain
        elif pid in ["matrix", "hacker", "10"]:
            # Emerald green scanline pulse with phosphor decay
            pulse = (math.sin(t * 2.5 * self.speed) * 0.5 + 0.5) ** 3
            val = (0.25 + 0.75 * pulse) * b_scale
            r, g, b = colorsys.hsv_to_rgb(0.33, 1.0, val)

        # 11. Molten Lava Dream
        elif pid in ["lava_lamp", "lava", "magma", "11"]:
            h_lava = 0.02 + 0.07 * (math.sin(t * 0.25 * self.speed) * 0.5 + 0.5)
            v_lava = 0.50 + 0.45 * (math.sin(t * 0.40 * self.speed) * 0.5 + 0.5)
            r, g, b = colorsys.hsv_to_rgb(h_lava, 1.0, v_lava * b_scale)

        else:
            # Fallback rainbow
            hue = (t * 0.15 * self.speed) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue, 1.0, b_scale)

        return (
            max(5, min(255, int(round(r * 255)))),
            max(5, min(255, int(round(g * 255)))),
            max(5, min(255, int(round(b * 255)))),
        )

    async def _loop(self):
        """High-frequency 20-30 FPS motion loop."""
        t_start = time.perf_counter()
        last_sent = (-1, -1, -1)

        while self.running:
            t = time.perf_counter() - t_start
            try:
                r, g, b = self._compute_frame(t)

                delta = abs(r - last_sent[0]) + abs(g - last_sent[1]) + abs(b - last_sent[2])
                if delta >= 2 and self.controller and self.controller.is_connected:
                    last_sent = (r, g, b)
                    await self.controller.set_color_rgb(r, g, b, immediate=True)

                if self.on_frame_update:
                    self.on_frame_update((r, g, b), self.pattern_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                pass

            await asyncio.sleep(0.040)  # ~25 FPS
