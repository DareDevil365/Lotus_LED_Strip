import asyncio
import colorsys
import ctypes
import logging
import math
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
# Distinct Stable Color Themes (Clean, 100% Saturated Palettes)
# ---------------------------------------------------------------------------
PALETTE_THEMES = [
    ("WARM_ORANGE", 0.075, "🕯️ Warm Yellow-Orange (Eye Comfort / Dark Mode)", (255, 128, 0)),
    ("GOTHAM_BLUE", 0.580, "🦇 Deep Slate / Electric Blue", (0, 130, 255)),
    ("CYBER_CYAN",  0.500, "💎 Sci-Fi Pure Cyan", (0, 255, 255)),
    ("MATRIX_GREEN",0.330, "🌲 Vibrant Emerald Green", (0, 255, 60)),
    ("NEON_PURPLE", 0.780, "🔮 Rich Purple / Magenta", (200, 0, 255)),
    ("CRIMSON_RED", 0.005, "🔴 Deep Crimson Red", (255, 0, 30)),
    ("GOLDEN_AMBER",0.110, "🌅 Warm Golden Amber", (255, 180, 0)),
]

def classify_screen_theme(r_flat: np.ndarray, g_flat: np.ndarray, b_flat: np.ndarray) -> Tuple[str, float, str, Tuple[int, int, int]]:
    """
    Classify the screen's core theme into a solid, distinct palette color.
    Uses strict majority voting to prevent micro-fluctuations from icons or thumbnails.
    """
    max_c = np.maximum(np.maximum(r_flat, g_flat), b_flat)
    min_c = np.minimum(np.minimum(r_flat, g_flat), b_flat)
    delta = max_c - min_c
    sat = np.where(max_c > 0.02, delta / (max_c + 1e-6), 0.0)

    avg_bright = float(np.mean(max_c))
    
    # Check if there is significant colored content (>6% of screen)
    vivid_mask = (sat > 0.20) & (max_c > 0.15)
    vivid_pixels = int(np.sum(vivid_mask))
    total_pixels = len(sat)  # 1024
    coverage = vivid_pixels / float(total_pixels)

    if coverage < 0.06:
        # Dark mode, reading text, or general coding -> Stable Warm Yellow-Orange
        if avg_bright < 0.30:
            return "WARM_ORANGE", 0.075, "🕯️ Warm Yellow-Orange (Dark Mode / Eye Comfort)", (255, 128, 0)
        else:
            return "GOLDEN_AMBER", 0.095, "🌅 Soft Golden Warmth (Bright Page / Anti-Glare)", (255, 180, 0)

    # Calculate dominant color across the vivid areas
    weights = (sat ** 1.8) * (max_c ** 0.6)
    w_sum = float(np.sum(weights))
    if w_sum <= 0.001:
        return "WARM_ORANGE", 0.075, "🕯️ Warm Yellow-Orange (Eye Comfort)", (255, 128, 0)

    w_r = float(np.sum(r_flat * weights) / w_sum)
    w_g = float(np.sum(g_flat * weights) / w_sum)
    w_b = float(np.sum(b_flat * weights) / w_sum)
    raw_h, raw_s, raw_v = colorsys.rgb_to_hsv(w_r, w_g, w_b)

    # Map raw continuous hue to the nearest solid discrete theme:
    if raw_h < 0.035 or raw_h >= 0.95:
        return "CRIMSON_RED", 0.005, "🔴 Deep Crimson Red", (255, 0, 30)
    elif 0.035 <= raw_h < 0.14:
        return "WARM_ORANGE", 0.075, "🕯️ Warm Yellow-Orange", (255, 128, 0)
    elif 0.14 <= raw_h < 0.42:
        return "MATRIX_GREEN", 0.330, "🌲 Vibrant Emerald Green", (0, 255, 60)
    elif 0.42 <= raw_h < 0.53:
        return "CYBER_CYAN", 0.500, "💎 Sci-Fi Pure Cyan", (0, 255, 255)
    elif 0.53 <= raw_h < 0.70:
        return "GOTHAM_BLUE", 0.580, "🦇 Deep Slate / Electric Blue", (0, 130, 255)
    else:
        return "NEON_PURPLE", 0.780, "🔮 Rich Purple / Magenta", (200, 0, 255)


class AmbientSyncEngine:
    """
    Intelligent Stable Theme Ambient Engine with Smooth Cinema Fading.
    
    Features:
    - 🌊 Smooth Gradual Transitions: When switching between themes, glides slowly (~2.0s)
      with an S-curve cosine ease along the color wheel.
    - 🔒 Zero Continuous Packet Flooding: Once transition completes, stays completely silent.
    - 🛡️ 1.2-Second Stability Lock: Ignores quick motions, thumbnail scrolling, and subtitles.
    - 💡 5V Hardware Illumination Floor: Guaranteed active minimum voltage so 5V LEDs never shut off.
    """

    def __init__(self, ble_controller, zone: str = "full", update_interval: float = 0.200, brightness: int = 30, transition_duration: float = 2.0):
        self.controller = ble_controller
        self.zone = zone.lower()
        self.update_interval = update_interval  # Check every 200ms
        self.transition_duration = transition_duration  # 2.0s smooth cinema fade
        self.brightness = max(10, min(100, int(brightness)))  # Default 30%
        
        self.running = False
        self._sync_task: Optional[asyncio.Task] = None

        # Currently locked active theme
        self.locked_theme_key = "WARM_ORANGE"
        self.locked_hue = 0.075
        self.current_h = 0.075
        self.locked_name = "🕯️ Warm Yellow-Orange (Eye Comfort / Dark Mode)"
        
        # Debounce counter: candidate theme must hold for multiple consecutive checks (~1.2s)
        self._candidate_theme_key = self.locked_theme_key
        self._candidate_hold_count = 0
        self._required_holds = 6  # 6 * 200ms = 1.2s stability lock

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
        """Capture screen and return current locked HSV."""
        return self.locked_hue, 1.0, 0.90

    def compute_rgb_for_hue(self, hue: float) -> Tuple[int, int, int]:
        """
        Compute the 100% saturated, brightness-scaled RGB color for 5V LED strips.
        """
        norm_bright = max(0.10, min(1.0, self.brightness / 100.0))
        r_f, g_f, b_f = colorsys.hsv_to_rgb(hue % 1.0, 1.0, 1.0)

        # Scale output with user brightness
        peak_scale = 255.0 * (norm_bright ** 0.65)
        out_r = max(0, min(255, int(round(r_f * peak_scale))))
        out_g = max(0, min(255, int(round(g_f * peak_scale))))
        out_b = max(0, min(255, int(round(b_f * peak_scale))))

        # 5V Hardware Illumination Floor: Primary active channel must be >= 50
        peak_ch = max(out_r, out_g, out_b)
        min_safe_floor = max(45, int(55 * norm_bright))
        if peak_ch < min_safe_floor and peak_ch > 0:
            boost = min_safe_floor / float(peak_ch)
            out_r = max(0, min(255, int(round(out_r * boost))))
            out_g = max(0, min(255, int(round(out_g * boost))))
            out_b = max(0, min(255, int(round(out_b * boost))))

        return out_r, out_g, out_b

    def _detect_screen_theme(self) -> Tuple[str, float, str, Tuple[int, int, int]]:
        """Grab screen and classify its theme."""
        attach_to_input_desktop()
        try:
            full_img = ImageGrab.grab()
        except Exception:
            try:
                attach_to_input_desktop()
                full_img = ImageGrab.grab()
            except Exception as e:
                logger.debug(f"Screen capture fallback: {e}")
                return self.locked_theme_key, self.locked_hue, self.locked_name, (255, 128, 0)

        region = self._crop_region(full_img)
        small = region.resize((32, 32), Image.Resampling.BILINEAR)
        arr = np.array(small, dtype=np.float32)

        r_flat = arr[:, :, 0].flatten() / 255.0
        g_flat = arr[:, :, 1].flatten() / 255.0
        b_flat = arr[:, :, 2].flatten() / 255.0

        return classify_screen_theme(r_flat, g_flat, b_flat)

    async def _glide_to_hue(self, target_hue: float, duration: float = 2.0):
        """
        Smoothly glides from current_h to target_hue along the shortest circular path.
        Uses S-curve cosine easing for cinema-grade gradual fading.
        """
        start_h = self.current_h
        dh = target_hue - start_h
        if dh > 0.5:
            dh -= 1.0
        elif dh < -0.5:
            dh += 1.0

        # If already at the color, send once and return
        if abs(dh) < 0.005:
            self.current_h = target_hue
            out_r, out_g, out_b = self.compute_rgb_for_hue(target_hue)
            if self.controller and self.controller.is_connected:
                self._last_sent_rgb = (out_r, out_g, out_b)
                await self.controller.set_color_rgb(out_r, out_g, out_b, immediate=True, raw=True)
            if self.on_color_update:
                self.on_color_update((out_r, out_g, out_b))
            return

        steps = max(20, int(duration / 0.045))  # ~45 steps for 2.0s
        for step in range(1, steps + 1):
            if not self.running:
                break
            
            # S-curve ease-in-out
            t = step / float(steps)
            ease_t = 0.5 * (1.0 - math.cos(t * math.pi))
            
            interp_h = (start_h + dh * ease_t) % 1.0
            self.current_h = interp_h
            
            out_r, out_g, out_b = self.compute_rgb_for_hue(interp_h)
            if self.controller and self.controller.is_connected:
                self._last_sent_rgb = (out_r, out_g, out_b)
                await self.controller.set_color_rgb(out_r, out_g, out_b, immediate=True, raw=True)

            if self.on_color_update:
                self.on_color_update((out_r, out_g, out_b))

            await asyncio.sleep(0.045)

        # Final target snap
        self.current_h = target_hue
        out_r, out_g, out_b = self.compute_rgb_for_hue(target_hue)
        if self.controller and self.controller.is_connected:
            self._last_sent_rgb = (out_r, out_g, out_b)
            await self.controller.set_color_rgb(out_r, out_g, out_b, immediate=True, raw=True)

    async def start(self):
        """Start the stable theme detection loop (auto powers ON the strip)."""
        if self.running:
            return
        if self.controller and self.controller.is_connected:
            try:
                await self.controller.set_power(True, immediate=True)
            except Exception as e:
                logger.debug(f"Auto power-on warning: {e}")
        self.running = True
        self._sync_task = asyncio.create_task(self._loop())
        logger.info(f"Stable Theme Ambient Light started [Zone: {self.zone}, Brightness: {self.brightness}%]")

    async def stop(self):
        """Stop ambient lighting."""
        self.running = False
        if self._sync_task:
            self._sync_task.cancel()
            self._sync_task = None
        logger.info("Ambient Sync stopped.")

    async def _loop(self):
        """
        Intelligent Stable Theme Loop with Smooth Transitions.
        - Identifies screen theme.
        - Fades smoothly to new theme over ~2.0 seconds.
        - Holds completely silent and rock-steady until the next screen theme change.
        """
        attach_to_input_desktop()
        
        # 1. Initial screen theme detection & smooth initial fade-in
        theme_key, hue, name, _ = self._detect_screen_theme()
        self.locked_theme_key = theme_key
        self.locked_hue = hue
        self.locked_name = name

        await self._glide_to_hue(self.locked_hue, duration=1.2)

        # 2. Main monitoring loop (rate-limited, debounced)
        while self.running:
            try:
                await asyncio.sleep(self.update_interval)

                cand_key, cand_hue, cand_name, _ = self._detect_screen_theme()

                if cand_key != self.locked_theme_key:
                    # New theme candidate detected
                    if cand_key == self._candidate_theme_key:
                        self._candidate_hold_count += 1
                        # If candidate holds steady for >= 1.2 seconds:
                        if self._candidate_hold_count >= self._required_holds:
                            self.locked_theme_key = cand_key
                            self.locked_hue = cand_hue
                            self.locked_name = cand_name
                            self._candidate_hold_count = 0

                            # Smoothly glide to new theme color over ~2.0s
                            await self._glide_to_hue(self.locked_hue, duration=self.transition_duration)
                    else:
                        # Reset candidate tracker
                        self._candidate_theme_key = cand_key
                        self._candidate_hold_count = 1
                else:
                    # Current theme is still holding
                    self._candidate_theme_key = self.locked_theme_key
                    self._candidate_hold_count = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ambient loop error: {e}")
