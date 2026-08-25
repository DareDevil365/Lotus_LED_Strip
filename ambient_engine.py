import asyncio
import colorsys
import ctypes
from ctypes import wintypes
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

class AmbientSyncEngine:
    """
    High-performance, ultra-smooth Ambient Screen Color Sync Engine.
    Features:
    - Coverage-Aware Color Extraction: Only shifts to vibrant colors when there is meaningful colored content on screen (>4% coverage)
    - Dark-Mode & Text Shield: Dark mode and text pages emit a gentle, dim warm ambient glow instead of latching onto tiny 5px blue buttons
    - Pure HSV-Space Transitions: Smooth circular Hue transitions with zero white/gray bleed
    - User Brightness Scaling: Configurable brightness scale (default 30%)
    """

    def __init__(self, ble_controller, zone: str = "full", update_interval: float = 0.075, transition_speed: float = 0.16, brightness: int = 30):
        self.controller = ble_controller
        self.zone = zone.lower()
        self.update_interval = update_interval
        self.transition_speed = transition_speed
        self.brightness = max(5, min(100, int(brightness)))  # Default 30%
        
        self.running = False
        self._sync_task: Optional[asyncio.Task] = None

        # Start at a soft, warm amber glow
        self.current_h = 0.08   # Warm Amber hue
        self.current_s = 0.60   # Pleasant warm saturation
        self.current_v = 0.35   # Gentle baseline
        self._last_sent_rgb = (-1, -1, -1)
        self.on_color_update: Optional[Callable[[Tuple[int, int, int]], None]] = None

    def _crop_region(self, img: Image.Image) -> Image.Image:
        """Crop image based on selected zone."""
        w, h = img.size
        z = self.zone
        if z == "center":
            return img.crop((int(w * 0.20), int(h * 0.20), int(w * 0.80), int(h * 0.80)))
        elif z == "top":
            return img.crop((0, 0, w, int(h * 0.35)))
        elif z == "bottom":
            return img.crop((0, int(h * 0.65), w, h))
        elif z == "left":
            return img.crop((0, 0, int(w * 0.35), h))
        elif z == "right":
            return img.crop((int(w * 0.65), 0, w, h))
        return img

    def _sample_screen(self) -> Tuple[float, float, float]:
        """
        Capture interactive screen, crop zone, downsample, and extract dominant vibrant color in (H, S, V).
        Uses coverage-aware filtering so small buttons or icons don't falsely turn a dark screen into cyan.
        """
        attach_to_input_desktop()
        
        try:
            full_img = ImageGrab.grab()
        except Exception:
            try:
                attach_to_input_desktop()
                full_img = ImageGrab.grab()
            except Exception as e:
                logger.debug(f"Screen capture fallback (screen locked/minimized): {e}")
                return self.current_h, self.current_s, self.current_v

        region = self._crop_region(full_img)
        small = region.resize((32, 32), Image.Resampling.BILINEAR)
        arr = np.array(small, dtype=np.float32)

        # Convert to float 0.0 - 1.0 (RGB)
        r_flat = arr[:, :, 0].flatten() / 255.0
        g_flat = arr[:, :, 1].flatten() / 255.0
        b_flat = arr[:, :, 2].flatten() / 255.0

        # Calculate saturation and value for each pixel
        max_c = np.maximum(np.maximum(r_flat, g_flat), b_flat)
        min_c = np.minimum(np.minimum(r_flat, g_flat), b_flat)
        delta = max_c - min_c
        sat = np.where(max_c > 0.02, delta / (max_c + 1e-6), 0.0)

        # Measure real colored area on screen (needs at least ~6% of screen to be chromatic)
        vivid_mask = (sat > 0.22) & (max_c > 0.18)
        vivid_count = int(np.sum(vivid_mask))
        total_pixels = len(sat)  # 1024
        color_coverage = vivid_count / float(total_pixels)

        # If at least 6% of the screen has real vivid color (e.g. video, game, banner, graphic)
        if color_coverage >= 0.06:
            # Weighted average favoring vivid pixels
            weights = (sat ** 1.8) * (max_c ** 0.6)
            w_sum = float(np.sum(weights))
            if w_sum > 0.001:
                weighted_r = float(np.sum(r_flat * weights) / w_sum)
                weighted_g = float(np.sum(g_flat * weights) / w_sum)
                weighted_b = float(np.sum(b_flat * weights) / w_sum)
                h, s, v = colorsys.rgb_to_hsv(weighted_r, weighted_g, weighted_b)
                
                # Proportional saturation based on how much of the screen is colored
                boosted_s = min(1.0, max(0.75, s * (1.2 + color_coverage)))
                boosted_v = min(1.0, max(0.50, v * 1.2))
                return h, boosted_s, boosted_v

        # Otherwise (Dark Mode, code editors, GitHub dashboard, text documents):
        # Calculate screen average brightness
        avg_brightness = float(np.mean(max_c))

        if avg_brightness < 0.28:
            # Dark Mode UI (mostly black/gray with small icons):
            # Rich, cozy Warm Yellow-Orange Candlelight glow (~2400K) — soothing for eyes in dark rooms
            h = 0.078  # Yellow-Orange Warm Light (~28° on color wheel)
            s = 0.88   # Rich warm saturation (prevents washed-out tone)
            v = max(0.25, min(0.50, avg_brightness * 1.2 + 0.25))
        else:
            # Bright / White document (Word, PDF, white webpage):
            # Soft warm golden glow (~3000K) to cut eye strain from bright screens
            h = 0.088  # Golden Warm Light
            s = 0.70   # Balanced warmth
            v = max(0.35, min(0.65, avg_brightness))

        return h, s, v

    async def start(self):
        """Start the ambient screen capture sync loop (auto powers ON the strip)."""
        if self.running:
            return
        # Ensure the strip is powered on before sending colors
        if self.controller and self.controller.is_connected:
            try:
                await self.controller.set_power(True, immediate=True)
            except Exception as e:
                logger.debug(f"Auto power-on warning: {e}")
        self.running = True
        self._sync_task = asyncio.create_task(self._loop())
        logger.info(f"Ambient Screen Sync started [Zone: {self.zone}, Brightness: {self.brightness}%]")

    async def stop(self):
        """Stop ambient screen capture."""
        self.running = False
        if self._sync_task:
            self._sync_task.cancel()
            self._sync_task = None
        logger.info("Ambient Screen Sync stopped.")

    async def _loop(self):
        """
        Continuous smooth color capture and transition loop.
        Interpolates in pure HSV space so transitions glide along the color wheel
        without ever washing out into white or gray.
        """
        attach_to_input_desktop()
        
        while self.running:
            start_time = time.perf_counter()
            try:
                # 1. Sample target screen color in HSV
                target_h, target_s, target_v = self._sample_screen()

                # 2. Smooth shortest-path Hue interpolation along color circle
                dh = target_h - self.current_h
                if dh > 0.5:
                    dh -= 1.0
                elif dh < -0.5:
                    dh += 1.0
                self.current_h = (self.current_h + dh * self.transition_speed) % 1.0
                self.current_s += (target_s - self.current_s) * self.transition_speed
                self.current_v += (target_v - self.current_v) * self.transition_speed

                # 3. Apply brightness scale (30% default)
                scale = self.brightness / 100.0
                final_v = max(0.10, self.current_v * scale)

                # 4. Convert HSV to RGB
                r_f, g_f, b_f = colorsys.hsv_to_rgb(self.current_h, self.current_s, final_v)
                out_r = max(10, min(255, int(round(r_f * 255))))
                out_g = max(10, min(255, int(round(g_f * 255))))
                out_b = max(10, min(255, int(round(b_f * 255))))

                # 5. Send BLE packet when color shifts
                last_r, last_g, last_b = self._last_sent_rgb
                delta = abs(out_r - last_r) + abs(out_g - last_g) + abs(out_b - last_b)

                if delta >= 2 and self.controller and self.controller.is_connected:
                    self._last_sent_rgb = (out_r, out_g, out_b)
                    await self.controller.set_color_rgb(out_r, out_g, out_b, immediate=True)

                if self.on_color_update:
                    self.on_color_update((out_r, out_g, out_b))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ambient loop error: {e}")

            elapsed = time.perf_counter() - start_time
            sleep_time = max(0.010, self.update_interval - elapsed)
            await asyncio.sleep(sleep_time)
