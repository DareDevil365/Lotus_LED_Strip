import asyncio
import collections
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
# Cinematic Color Tone Presets & Mood Sectors
# ---------------------------------------------------------------------------
CINEMATIC_MOODS = [
    ("WARM_GOLD", 0.080, "Golden Sunset / Candlelight Warmth"),
    ("GOTHAM_BLUE", 0.580, "Gotham Night / Cinematic Slate Blue"),
    ("CYBER_CYAN", 0.500, "Sci-Fi Electric Cyan / Neon Tech"),
    ("NEON_MAGENTA", 0.820, "Cyberpunk Purple / Neon Noir"),
    ("MATRIX_GREEN", 0.330, "Emerald Matrix / Deep Foliage"),
    ("CRIMSON_RED", 0.005, "Dramatic Crimson / Red Alert"),
    ("COZY_AMBER", 0.070, "Warm Yellow-Orange Cozy Ambient"),
]

class AmbientSyncEngine:
    """
    Cinematic Base-Theme Ambient Lighting Engine.
    
    Features:
    - Cinematic Mood-Lock: Identifies the base theme/color tone of a movie, game, or video
      and firmly locks to that color palette without rapid or distracting color fluctuations.
    - Scene Change Persistence: Only transitions when a scene fundamentally and consistently shifts.
    - Stately Cinema-Grade Transitions: Glides smoothly across 3-5 seconds with zero jitter or flickering.
    - 5V Hardware Illumination Floor: Guaranteed active minimum voltage so 5V USB LEDs never turn off.
    - 100% Saturated Pure Gamut: 0% white/gray wash, rendering pure vivid atmospheric color.
    """

    def __init__(self, ble_controller, zone: str = "full", update_interval: float = 0.040, transition_speed: float = 0.020, brightness: int = 30):
        self.controller = ble_controller
        self.zone = zone.lower()
        self.update_interval = update_interval
        self.transition_speed = transition_speed  # 0.020 = ~3.5s stately cinema transition
        self.brightness = max(10, min(100, int(brightness)))  # Default 30%
        
        self.running = False
        self._sync_task: Optional[asyncio.Task] = None

        # Active state (starts at warm amber mood)
        self.current_h = 0.075  # Warm Yellow-Orange
        self.current_s = 1.0    # 100% Saturation
        self.current_v = 0.70   # Strong full baseline
        
        # Mood-Lock tracking buffer (rolling window of recent screen color samples)
        self._recent_hues = collections.deque(maxlen=60)  # ~2.4 seconds of history
        self._locked_mood_h = 0.075
        self._locked_mood_name = "COZY_AMBER"
        self._mood_lock_counter = 0

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

    def _extract_instant_color(self) -> Tuple[float, float, float, float]:
        """
        Samples screen pixels and returns (hue, sat, val, chromatic_weight).
        """
        attach_to_input_desktop()
        try:
            full_img = ImageGrab.grab()
        except Exception:
            try:
                attach_to_input_desktop()
                full_img = ImageGrab.grab()
            except Exception as e:
                logger.debug(f"Screen capture fallback: {e}")
                return self.current_h, self.current_s, self.current_v, 0.0

        region = self._crop_region(full_img)
        small = region.resize((32, 32), Image.Resampling.BILINEAR)
        arr = np.array(small, dtype=np.float32)

        r_flat = arr[:, :, 0].flatten() / 255.0
        g_flat = arr[:, :, 1].flatten() / 255.0
        b_flat = arr[:, :, 2].flatten() / 255.0

        max_c = np.maximum(np.maximum(r_flat, g_flat), b_flat)
        min_c = np.minimum(np.minimum(r_flat, g_flat), b_flat)
        delta = max_c - min_c
        sat = np.where(max_c > 0.02, delta / (max_c + 1e-6), 0.0)

        # Detect chromatic pixels
        vivid_mask = (sat > 0.16) & (max_c > 0.12)
        vivid_count = int(np.sum(vivid_mask))
        total_pixels = len(sat)  # 1024
        color_coverage = vivid_count / float(total_pixels)
        avg_brightness = float(np.mean(max_c))

        if color_coverage >= 0.025:
            # Video scene with chromatic lighting
            weights = (sat ** 1.8) * (max_c ** 0.8)
            w_sum = float(np.sum(weights))
            if w_sum > 0.001:
                weighted_r = float(np.sum(r_flat * weights) / w_sum)
                weighted_g = float(np.sum(g_flat * weights) / w_sum)
                weighted_b = float(np.sum(b_flat * weights) / w_sum)
                h, s, v = colorsys.rgb_to_hsv(weighted_r, weighted_g, weighted_b)
                return h, 1.0, 0.90, color_coverage

        # Dark mode / static reading -> default to cozy warm amber
        return 0.075, 1.0, max(0.60, avg_brightness), 0.0

    def _sample_screen(self) -> Tuple[float, float, float]:
        """Capture screen and extract instant color (H, S, V)."""
        h, s, v, _ = self._extract_instant_color()
        return h, s, v

    def _update_cinematic_mood_lock(self, sample_h: float, sample_coverage: float) -> float:
        """
        Cinematic Mood-Lock algorithm:
        Accumulates temporal color data and locks to the dominant scene theme.
        Rejects fast flickers, camera cuts, or brief micro-flashes.
        """
        if sample_coverage > 0.02:
            self._recent_hues.append(sample_h)
        else:
            # Dark / neutral page pushes towards warm amber mood
            self._recent_hues.append(0.075)

        if len(self._recent_hues) < 15:
            return self._locked_mood_h

        # Compute angular mean on circle (prevents 0/1 wrap-around error)
        hues_arr = np.array(self._recent_hues)
        angles = hues_arr * 2.0 * np.pi
        mean_x = np.mean(np.cos(angles))
        mean_y = np.mean(np.sin(angles))
        dominant_h = (np.arctan2(mean_y, mean_x) / (2.0 * np.pi)) % 1.0

        # Angular distance between dominant buffer hue and currently locked hue
        dh = dominant_h - self._locked_mood_h
        if dh > 0.5:
            dh -= 1.0
        elif dh < -0.5:
            dh += 1.0
        
        # If scene has consistently shifted to a new color mood for a sustained period:
        if abs(dh) > 0.08:
            self._mood_lock_counter += 1
            # Require at least 25 consecutive consistent samples (~1 second) to switch scene theme
            if self._mood_lock_counter >= 25:
                self._locked_mood_h = dominant_h
                self._mood_lock_counter = 0
        else:
            self._mood_lock_counter = max(0, self._mood_lock_counter - 1)

        return self._locked_mood_h

    async def start(self):
        """Start the ambient screen capture sync loop (auto powers ON the strip)."""
        if self.running:
            return
        if self.controller and self.controller.is_connected:
            try:
                await self.controller.set_power(True, immediate=True)
            except Exception as e:
                logger.debug(f"Auto power-on warning: {e}")
        self.running = True
        self._sync_task = asyncio.create_task(self._loop())
        logger.info(f"Cinematic Ambient Sync started [Zone: {self.zone}, Brightness: {self.brightness}%]")

    async def stop(self):
        """Stop ambient screen capture."""
        self.running = False
        if self._sync_task:
            self._sync_task.cancel()
            self._sync_task = None
        logger.info("Ambient Screen Sync stopped.")

    async def _loop(self):
        """
        Cinema-Grade Ambient Sync Loop.
        Locked to the video base theme color tone. Smoothly glides across scene changes
        and maintains a solid hardware illumination floor so 5V USB LEDs NEVER shut off.
        """
        attach_to_input_desktop()
        
        while self.running:
            start_time = time.perf_counter()
            try:
                # 1. Sample current screen color
                raw_h, raw_s, raw_v, raw_cov = self._extract_instant_color()

                # 2. Update Cinematic Scene Mood Lock
                target_h = self._update_cinematic_mood_lock(raw_h, raw_cov)
                target_s = 1.0  # Always pure 100% saturated color
                target_v = 0.90

                # 3. Smooth, majestic cinema-grade Hue glide along color wheel (zero jumping)
                dh = target_h - self.current_h
                if dh > 0.5:
                    dh -= 1.0
                elif dh < -0.5:
                    dh += 1.0

                self.current_h = (self.current_h + dh * self.transition_speed) % 1.0
                self.current_s = 1.0
                self.current_v += (target_v - self.current_v) * self.transition_speed

                # 4. Apply User Brightness Scaling (e.g. 30%, 50%, 100%)
                norm_bright = max(0.10, min(1.0, self.brightness / 100.0))
                
                # Convert 100% saturated HSV to base RGB (0.0 to 1.0)
                r_f, g_f, b_f = colorsys.hsv_to_rgb(self.current_h, 1.0, 1.0)

                # Scale with brightness percentage
                # Base scale: maps 30% -> output peak ~85/255; 100% -> output peak 255/255
                peak_scale = 255.0 * (norm_bright ** 0.65)
                
                # 5. Guaranteed 5V Hardware Illumination Floor (prevents LED diode dropout)
                # Ensure the primary channel is ALWAYS >= 50 on 5V strips so it never shuts off
                out_r = max(0, min(255, int(round(r_f * peak_scale))))
                out_g = max(0, min(255, int(round(g_f * peak_scale))))
                out_b = max(0, min(255, int(round(b_f * peak_scale))))

                peak_ch = max(out_r, out_g, out_b)
                min_safe_floor = max(45, int(55 * norm_bright))
                if peak_ch < min_safe_floor and peak_ch > 0:
                    boost = min_safe_floor / float(peak_ch)
                    out_r = max(0, min(255, int(round(out_r * boost))))
                    out_g = max(0, min(255, int(round(out_g * boost))))
                    out_b = max(0, min(255, int(round(out_b * boost))))

                # 6. Send BLE packet when color shifts
                last_r, last_g, last_b = self._last_sent_rgb
                delta = abs(out_r - last_r) + abs(out_g - last_g) + abs(out_b - last_b)

                if delta >= 1 and self.controller and self.controller.is_connected:
                    self._last_sent_rgb = (out_r, out_g, out_b)
                    await self.controller.set_color_rgb(out_r, out_g, out_b, immediate=True, raw=True)

                if self.on_color_update:
                    self.on_color_update((out_r, out_g, out_b))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ambient loop error: {e}")

            elapsed = time.perf_counter() - start_time
            sleep_time = max(0.010, self.update_interval - elapsed)
            await asyncio.sleep(sleep_time)
