import asyncio
import colorsys
import logging
import math
import time
from typing import Callable, Optional, Tuple

import numpy as np

logger = logging.getLogger("MusicSync")

# Safe import — sounddevice is optional
_HAS_SOUNDDEVICE = False
try:
    import sounddevice as sd
    _HAS_SOUNDDEVICE = True
except ImportError:
    logger.debug("sounddevice not installed — music reactive mode unavailable.")


def is_available() -> bool:
    """Check if music reactive mode dependencies are present."""
    return _HAS_SOUNDDEVICE


class MusicReactiveEngine:
    """
    Real-time audio-reactive LED engine.
    Uses laptop microphone / system audio to drive LED colors:
      - Bass energy  → warm colors (red/orange)
      - Mid energy   → green tones
      - Treble energy → cool colors (blue/cyan)
      - Volume       → overall brightness
    
    Includes smooth transitions to prevent jarring flicker.
    """

    # Frequency band boundaries (Hz)
    BASS_RANGE = (20, 250)
    MID_RANGE = (250, 2000)
    TREBLE_RANGE = (2000, 8000)

    SAMPLE_RATE = 22050
    CHUNK_SIZE = 1024  # ~46ms per chunk at 22050Hz

    def __init__(self, ble_controller, sensitivity: float = 1.0, transition_speed: float = 0.25):
        self.controller = ble_controller
        self.sensitivity = max(0.1, min(3.0, sensitivity))
        self.transition_speed = transition_speed

        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._stream = None

        # Smooth state
        self.current_r = 80.0
        self.current_g = 40.0
        self.current_b = 120.0
        self._last_sent_rgb = (-1, -1, -1)

        # Audio buffer (ring buffer)
        self._audio_buffer = np.zeros(self.CHUNK_SIZE, dtype=np.float32)
        self._buffer_ready = False

        # Callbacks
        self.on_color_update: Optional[Callable[[Tuple[int, int, int]], None]] = None
        self.on_level_update: Optional[Callable[[float, float, float, float], None]] = None  # bass, mid, treble, vol

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice callback — runs in audio thread."""
        if status:
            logger.debug(f"Audio status: {status}")
        # Take mono mix
        mono = indata[:, 0] if indata.ndim > 1 else indata.flatten()
        self._audio_buffer[:len(mono)] = mono[:self.CHUNK_SIZE]
        self._buffer_ready = True

    def _analyze_spectrum(self) -> Tuple[float, float, float, float]:
        """
        FFT the audio buffer and extract bass/mid/treble energy levels.
        Returns (bass, mid, treble, volume) each in 0.0-1.0 range.
        """
        data = self._audio_buffer.copy()
        # Apply Hanning window to reduce spectral leakage
        windowed = data * np.hanning(len(data))

        fft_mag = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(len(windowed), 1.0 / self.SAMPLE_RATE)

        def band_energy(low, high):
            mask = (freqs >= low) & (freqs <= high)
            if np.any(mask):
                return float(np.mean(fft_mag[mask]))
            return 0.0

        bass = band_energy(*self.BASS_RANGE)
        mid = band_energy(*self.MID_RANGE)
        treble = band_energy(*self.TREBLE_RANGE)
        volume = float(np.sqrt(np.mean(data ** 2)))  # RMS volume

        # Normalize with sensitivity
        scale = self.sensitivity * 8.0
        bass = min(1.0, bass * scale)
        mid = min(1.0, mid * scale * 1.2)
        treble = min(1.0, treble * scale * 1.5)
        volume = min(1.0, volume * self.sensitivity * 5.0)

        return bass, mid, treble, volume

    def _spectrum_to_rgb(self, bass: float, mid: float, treble: float, volume: float) -> Tuple[int, int, int]:
        """
        Map frequency spectrum to RGB color.
        Bass → red/orange warmth, Mid → green, Treble → blue/cyan.
        Volume controls brightness.
        """
        # Weighted hue calculation
        total = bass + mid + treble + 0.001
        # Hue mapping: bass=0.0 (red), mid=0.33 (green), treble=0.58 (blue)
        hue = (bass * 0.02 + mid * 0.30 + treble * 0.60) / total

        # Higher energy = more saturated
        sat = min(1.0, max(0.65, (total / 2.0) * 1.3))

        # Volume drives brightness (floor at 0.35 to prevent off)
        val = min(1.0, max(0.35, volume * 1.5 + 0.35))

        r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
        return (
            max(30, min(255, int(r * 255))),
            max(30, min(255, int(g * 255))),
            max(30, min(255, int(b * 255))),
        )

    async def start(self):
        """Start the music reactive engine."""
        if not _HAS_SOUNDDEVICE:
            raise RuntimeError("sounddevice is not installed. Run: pip install sounddevice")
        if self.running:
            return

        self.running = True
        # Ensure strip is on
        if self.controller and self.controller.is_connected:
            await self.controller.set_power(True, immediate=True)

        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            blocksize=self.CHUNK_SIZE,
            dtype='float32',
            callback=self._audio_callback,
        )
        self._stream.start()
        self._task = asyncio.create_task(self._loop())
        logger.info("Music Reactive Engine started.")

    async def stop(self):
        """Stop the music reactive engine."""
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        logger.info("Music Reactive Engine stopped.")

    async def _loop(self):
        """Main processing loop — runs at ~30fps."""
        while self.running:
            start_t = time.perf_counter()
            try:
                if self._buffer_ready:
                    self._buffer_ready = False
                    bass, mid, treble, volume = self._analyze_spectrum()

                    target_r, target_g, target_b = self._spectrum_to_rgb(bass, mid, treble, volume)

                    # Smooth interpolation
                    self.current_r += (target_r - self.current_r) * self.transition_speed
                    self.current_g += (target_g - self.current_g) * self.transition_speed
                    self.current_b += (target_b - self.current_b) * self.transition_speed

                    out_r = max(30, min(255, int(round(self.current_r))))
                    out_g = max(30, min(255, int(round(self.current_g))))
                    out_b = max(30, min(255, int(round(self.current_b))))

                    last_r, last_g, last_b = self._last_sent_rgb
                    delta = abs(out_r - last_r) + abs(out_g - last_g) + abs(out_b - last_b)

                    if delta >= 3 and self.controller and self.controller.is_connected:
                        self._last_sent_rgb = (out_r, out_g, out_b)
                        await self.controller.set_color_rgb(out_r, out_g, out_b, immediate=True)

                    if self.on_color_update:
                        self.on_color_update((out_r, out_g, out_b))
                    if self.on_level_update:
                        self.on_level_update(bass, mid, treble, volume)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Music loop error: {e}")

            elapsed = time.perf_counter() - start_t
            await asyncio.sleep(max(0.010, 0.033 - elapsed))
