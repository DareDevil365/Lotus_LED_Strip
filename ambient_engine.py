import asyncio
import colorsys
import ctypes
import logging
import time
from typing import Callable, Optional, Tuple
import numpy as np
from PIL import ImageGrab, Image

logger = logging.getLogger("AmbientSync")

user32 = ctypes.windll.user32

def attach_to_input_desktop():
    """Ensure process/thread is attached to the active interactive Windows desktop."""
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    try:
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception as e:
        logger.debug(f"Input desktop attach error: {e}")

# ---------------------------------------------------------------------------
# Fixed Cinematic Themes (Rock-Solid Eye-Comfort Bias Lights)
# ---------------------------------------------------------------------------
CINEMATIC_THEMES = {
    "warm_orange": (0.075, "🕯️ Warm Yellow-Orange (Candlelight / Eye Comfort)", (255, 120, 0)),
    "gotham_blue": (0.580, "🦇 Gotham Noir Slate Blue (Cinematic Night)", (0, 130, 255)),
    "cyber_cyan": (0.500, "💎 Sci-Fi Electric Cyan (Tech Glow)", (0, 240, 255)),
    "neon_magenta": (0.830, "🌆 Cyberpunk Neon Magenta (Retro Synth)", (255, 0, 140)),
    "matrix_green": (0.330, "🌲 Matrix Emerald Green (Terminal Glow)", (0, 255, 60)),
    "golden_sunset": (0.100, "🌅 Golden Hour Sunset (Warm Amber)", (255, 170, 0)),
}

class AmbientSyncEngine:
    """
    Fixed Cinematic Ambient Bias Lighting Engine.
    
    Features:
    - 🔒 Rock-Solid Color Lock: Locks firmly onto one fixed cinematic color tone.
      Zero fluctuations, zero switching, zero hunting, and zero flickering.
    - 5V Hardware Illumination Floor: Guaranteed active minimum voltage so 5V USB LEDs never turn off.
    - 100% Saturated Pure Gamut: 0% white/gray wash, rendering pure, rich, eye-soothing backlight.
    """

    def __init__(self, ble_controller, zone: str = "full", update_interval: float = 0.050, transition_speed: float = 0.05, brightness: int = 30, theme: str = "warm_orange"):
        self.controller = ble_controller
        self.zone = zone.lower()
        self.update_interval = update_interval
        self.transition_speed = transition_speed
        self.brightness = max(10, min(100, int(brightness)))  # Default 30%
        self.theme_key = theme if theme in CINEMATIC_THEMES else "warm_orange"
        
        self.running = False
        self._sync_task: Optional[asyncio.Task] = None

        # Lock to chosen cinematic theme hue
        theme_h, self.theme_name, self.base_rgb = CINEMATIC_THEMES[self.theme_key]
        self.locked_h = theme_h
        self.current_h = theme_h
        self.current_s = 1.0    # 100% Saturation
        self.current_v = 1.0

        self._last_sent_rgb = (-1, -1, -1)
        self.on_color_update: Optional[Callable[[Tuple[int, int, int]], None]] = None

    def _sample_screen(self) -> Tuple[float, float, float]:
        """Capture screen and return current locked HSV."""
        return self.locked_h, 1.0, 0.90

    def compute_output_rgb(self) -> Tuple[int, int, int]:
        """
        Compute the 100% saturated, brightness-scaled, rock-solid RGB color.
        Ensures the 5V hardware illumination floor is maintained so LEDs never turn off.
        """
        norm_bright = max(0.10, min(1.0, self.brightness / 100.0))
        r_f, g_f, b_f = colorsys.hsv_to_rgb(self.locked_h, 1.0, 1.0)

        # Scale with user brightness (e.g. 30% -> peak ~85)
        peak_scale = 255.0 * (norm_bright ** 0.65)
        out_r = max(0, min(255, int(round(r_f * peak_scale))))
        out_g = max(0, min(255, int(round(g_f * peak_scale))))
        out_b = max(0, min(255, int(round(b_f * peak_scale))))

        # 5V Hardware Illumination Floor: Primary active channel must be >= 45
        peak_ch = max(out_r, out_g, out_b)
        min_safe_floor = max(45, int(55 * norm_bright))
        if peak_ch < min_safe_floor and peak_ch > 0:
            boost = min_safe_floor / float(peak_ch)
            out_r = max(0, min(255, int(round(out_r * boost))))
            out_g = max(0, min(255, int(round(out_g * boost))))
            out_b = max(0, min(255, int(round(out_b * boost))))

        return out_r, out_g, out_b

    async def start(self):
        """Start the locked cinematic ambient bias light (auto powers ON the strip)."""
        if self.running:
            return
        if self.controller and self.controller.is_connected:
            try:
                await self.controller.set_power(True, immediate=True)
            except Exception as e:
                logger.debug(f"Auto power-on warning: {e}")
        self.running = True
        self._sync_task = asyncio.create_task(self._loop())
        logger.info(f"Locked Ambient Bias Light started [{self.theme_name}, Brightness: {self.brightness}%]")

    async def stop(self):
        """Stop ambient bias lighting."""
        self.running = False
        if self._sync_task:
            self._sync_task.cancel()
            self._sync_task = None
        logger.info("Ambient Sync stopped.")

    async def _loop(self):
        """
        Rock-solid locked ambient loop.
        Transmits the solid base theme color once and maintains it with zero fluctuations.
        """
        attach_to_input_desktop()
        
        # 1. Compute solid locked color
        out_r, out_g, out_b = self.compute_output_rgb()

        # 2. Immediately send to LED strip
        if self.controller and self.controller.is_connected:
            self._last_sent_rgb = (out_r, out_g, out_b)
            await self.controller.set_color_rgb(out_r, out_g, out_b, immediate=True, raw=True)

        if self.on_color_update:
            self.on_color_update((out_r, out_g, out_b))

        # 3. Maintain steady state (heartbeat keepalive every 1.5s with zero color change)
        while self.running:
            try:
                await asyncio.sleep(1.0)
                if self.controller and self.controller.is_connected:
                    await self.controller.set_color_rgb(out_r, out_g, out_b, immediate=True, raw=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ambient loop error: {e}")
