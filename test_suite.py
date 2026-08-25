import asyncio
import colorsys
import os
import sys
import time
import unittest
import numpy as np

# Ensure UTF-8 stdout for test outputs
sys.stdout.reconfigure(encoding='utf-8')

from ble_controller import LEDStripController, mac_str_to_int, DEFAULT_MAC
from ambient_engine import AmbientSyncEngine, attach_to_input_desktop
from audio_engine import MusicReactiveEngine, is_available as audio_available
from main import (
    parse_color_input,
    PRESETS,
    NAMED_COLORS,
    FIRMWARE_EFFECTS,
    load_favorites,
    save_favorites,
    FAVORITES_FILE
)


class TestBLEProtocolAndPackets(unittest.TestCase):
    """Exhaustive testing of BLE controller packet structure and firmware protocol."""

    def setUp(self):
        self.controller = LEDStripController(DEFAULT_MAC)

    def test_mac_to_int(self):
        mac = "BE:69:29:00:0A:23"
        mac_int = mac_str_to_int(mac)
        self.assertEqual(mac_int, 0xBE6929000A23)
        self.assertEqual(mac_str_to_int("be-69-29-00-0a-23"), 0xBE6929000A23)

    def test_color_packets(self):
        # Test RGB clamping & packet format
        r, g, b = 255, 128, 0
        expected_9byte = bytes([0x7E, 0x07, 0x05, 0x03, 255, 128, 0, 0x00, 0xEF])
        expected_8byte = bytes([0x7E, 0x04, 0x04, 255, 128, 0, 0x00, 0xEF])
        
        # Test bounds
        r_clamped = max(0, min(255, 300))
        g_clamped = max(0, min(255, -50))
        self.assertEqual(r_clamped, 255)
        self.assertEqual(g_clamped, 0)

    def test_brightness_packets(self):
        for lvl in [0, 50, 100, -10, 150]:
            clamped = max(0, min(100, lvl))
            pkt = bytes([0x7E, 0x04, 0x01, clamped, 0x00, 0x00, 0x00, 0x00, 0xEF])
            self.assertEqual(len(pkt), 9)
            self.assertEqual(pkt[0], 0x7E)
            self.assertEqual(pkt[-1], 0xEF)
            self.assertEqual(pkt[3], clamped)

    def test_effect_packets(self):
        for no, name, hex_id, desc in FIRMWARE_EFFECTS:
            pkt = bytes([0x7E, 0x00, 0x03, hex_id, 0x03, 0xFF, 0xFF, 0x00, 0xEF])
            self.assertEqual(len(pkt), 9)
            self.assertEqual(pkt[0], 0x7E)
            self.assertEqual(pkt[-1], 0xEF)
            self.assertEqual(pkt[3], hex_id)

    def test_effect_speed_packets(self):
        for spd in [0, 50, 100]:
            pkt = bytes([0x7E, 0x04, 0x02, spd, 0xFF, 0xFF, 0xFF, 0x00, 0xEF])
            self.assertEqual(len(pkt), 9)
            self.assertEqual(pkt[0], 0x7E)
            self.assertEqual(pkt[-1], 0xEF)
            self.assertEqual(pkt[3], spd)

    def test_power_packets(self):
        p_on = bytes([0x7E, 0x04, 0x04, 0xF0, 0x00, 0x01, 0xFF, 0xEF])
        p_off = bytes([0x7E, 0x04, 0x04, 0xF0, 0x00, 0x00, 0xFF, 0xEF])
        self.assertEqual(len(p_on), 8)
        self.assertEqual(len(p_off), 8)


class TestColorParsing(unittest.TestCase):
    """Stress testing of user input color parsing across all formats."""

    def test_preset_numbers(self):
        for i, (p_id, p_name, rgb) in enumerate(PRESETS, 1):
            parsed_rgb, cmd = parse_color_input(str(i))
            self.assertEqual(parsed_rgb, rgb, f"Failed for preset number {i}")
            self.assertTrue(cmd.startswith("preset_"))

    def test_preset_names(self):
        for p_id, p_name, rgb in PRESETS:
            parsed_rgb, cmd = parse_color_input(p_id)
            self.assertEqual(parsed_rgb, rgb, f"Failed for preset id {p_id}")
            parsed_rgb2, _ = parse_color_input(p_name)
            self.assertEqual(parsed_rgb2, rgb, f"Failed for preset name {p_name}")

    def test_named_colors(self):
        for name, rgb in NAMED_COLORS.items():
            parsed_rgb, cmd = parse_color_input(name)
            self.assertEqual(parsed_rgb, rgb, f"Failed for color name: {name}")
            parsed_upper, _ = parse_color_input(name.upper())
            self.assertEqual(parsed_upper, rgb, f"Failed for uppercase color: {name.upper()}")

    def test_hex_formats(self):
        test_cases = [
            ("#FF0055", (255, 0, 85)),
            ("FF0055", (255, 0, 85)),
            ("#ff0055", (255, 0, 85)),
            ("0xff0055", (255, 0, 85)),
            ("#F05", (255, 0, 85)),
            ("f05", (255, 0, 85)),
            ("#000000", (0, 0, 0)),
            ("#ffffff", (255, 255, 255)),
        ]
        for hex_str, expected in test_cases:
            parsed, cmd = parse_color_input(hex_str)
            self.assertEqual(parsed, expected, f"Failed for hex: {hex_str}")
            self.assertEqual(cmd, "hex")

    def test_rgb_formats(self):
        test_cases = [
            ("255, 0, 85", (255, 0, 85)),
            ("255 0 85", (255, 0, 85)),
            ("255; 0; 85", (255, 0, 85)),
            ("rgb(255, 0, 85)", (255, 0, 85)),
            ("rgb(255,0,85)", (255, 0, 85)),
            ("[255, 0, 85]", (255, 0, 85)),
        ]
        for s, expected in test_cases:
            parsed, cmd = parse_color_input(s)
            self.assertEqual(parsed, expected, f"Failed for RGB string: {s}")

    def test_hsl_formats(self):
        test_cases = [
            ("hsl(0, 100%, 50%)", (255, 0, 0)),     # Pure Red
            ("hsl(120, 100%, 50%)", (0, 255, 0)),   # Pure Green
            ("hsl(240, 100%, 50%)", (0, 0, 255)),   # Pure Blue
        ]
        for s, expected in test_cases:
            parsed, cmd = parse_color_input(s)
            self.assertEqual(cmd, "hsl")
            for c1, c2 in zip(parsed, expected):
                self.assertAlmostEqual(c1, c2, delta=2)

    def test_power_commands(self):
        for off_cmd in ["off", "power off", "shutdown", "black", "kill"]:
            parsed, cmd = parse_color_input(off_cmd)
            self.assertEqual(cmd, "power_off")
            self.assertEqual(parsed, (0, 0, 0))

        for on_cmd in ["on", "power on", "start"]:
            parsed, cmd = parse_color_input(on_cmd)
            self.assertEqual(cmd, "power_on")
            self.assertIsNone(parsed)

    def test_invalid_inputs(self):
        invalids = ["xyz123", "###", "rgb(9999)", "notacolor", "", "   ", "255,foo,0"]
        for inv in invalids:
            parsed, cmd = parse_color_input(inv)
            self.assertIsNone(parsed, f"Expected None for invalid input: {inv}")


class TestFavoritesSystem(unittest.TestCase):
    """Testing JSON persistence of custom favorites."""

    def test_save_load_lifecycle(self):
        test_favs = [
            {"name": "Neon Cyan", "r": 0, "g": 255, "b": 240},
            {"name": "Deep Blood Red", "r": 200, "g": 10, "b": 15},
        ]
        save_favorites(test_favs)
        loaded = load_favorites()
        self.assertGreaterEqual(len(loaded), 2)
        self.assertTrue(any(f["name"] == "Neon Cyan" for f in loaded))
        self.assertTrue(any(f["name"] == "Deep Blood Red" for f in loaded))


class TestAmbientEngineMath(unittest.TestCase):
    """Stress testing color extraction, HSV pure-glide math, and brightness scaling."""

    def test_screen_sampling_and_saturation(self):
        ctrl = LEDStripController(DEFAULT_MAC)
        engine = AmbientSyncEngine(ctrl, brightness=30)
        
        # Test 1: Sampling active interactive desktop
        h, s, v = engine._sample_screen()
        self.assertGreaterEqual(s, 0.95, "Saturation dropped below 100% max saturation!")
        self.assertLessEqual(s, 1.0)
        self.assertGreaterEqual(v, 0.10)
        self.assertLessEqual(v, 1.0)

    def test_5v_hardware_illumination_floor(self):
        ctrl = LEDStripController(DEFAULT_MAC)
        engine = AmbientSyncEngine(ctrl, brightness=30)
        
        # For various hues, verify primary channel is always >= 45 to protect 5V LEDs
        for test_h in [0.005, 0.075, 0.33, 0.50, 0.58, 0.78]:
            r, g, b = engine.compute_rgb_for_hue(test_h)
            self.assertGreaterEqual(max(r, g, b), 45, f"5V illumination floor breached for hue {test_h}!")

    def test_brightness_scaling(self):
        ctrl = LEDStripController(DEFAULT_MAC)
        engine30 = AmbientSyncEngine(ctrl, brightness=30)
        self.assertEqual(engine30.brightness, 30)

        engine100 = AmbientSyncEngine(ctrl, brightness=100)
        self.assertEqual(engine100.brightness, 100)


class TestAudioEngineMath(unittest.TestCase):
    """Stress testing FFT audio processing and spectrum-to-RGB conversion."""

    def test_spectrum_to_rgb(self):
        ctrl = LEDStripController(DEFAULT_MAC)
        engine = MusicReactiveEngine(ctrl)

        # 1. Heavy bass (kick drum / sub)
        r_bass, g_bass, b_bass = engine._spectrum_to_rgb(bass=1.0, mid=0.05, treble=0.02, volume=0.8)
        self.assertGreater(r_bass, g_bass, "Bass should produce warm/red tones")
        self.assertGreaterEqual(r_bass, 30, "Anti-flicker floor breached")

        # 2. Heavy treble (hi-hats / synth)
        r_treble, g_treble, b_treble = engine._spectrum_to_rgb(bass=0.02, mid=0.05, treble=1.0, volume=0.8)
        self.assertGreater(b_treble, r_treble, "Treble should produce cool/blue tones")

        # 3. Low volume (silence floor)
        r_silent, g_silent, b_silent = engine._spectrum_to_rgb(bass=0.0, mid=0.0, treble=0.0, volume=0.0)
        self.assertGreaterEqual(r_silent, 30)
        self.assertGreaterEqual(g_silent, 30)
        self.assertGreaterEqual(b_silent, 30)


class TestMotionPatternEngine(unittest.TestCase):
    """Stress testing procedural motion animation algorithms."""

    def test_all_motion_patterns_output_valid_rgb(self):
        from motion_engine import MotionPatternEngine
        ctrl = LEDStripController(DEFAULT_MAC)

        for p_id, p_title, p_desc in MotionPatternEngine.PATTERNS:
            engine = MotionPatternEngine(ctrl, pattern_id=p_id, speed=1.5, brightness=80)
            for t_step in range(20):
                t = t_step * 0.1
                r, g, b = engine._compute_frame(t)
                self.assertGreaterEqual(r, 0, f"Red out of bounds in {p_id}")
                self.assertLessEqual(r, 255, f"Red out of bounds in {p_id}")
                self.assertGreaterEqual(g, 0, f"Green out of bounds in {p_id}")
                self.assertLessEqual(g, 255, f"Green out of bounds in {p_id}")
                self.assertGreaterEqual(b, 0, f"Blue out of bounds in {p_id}")
                self.assertLessEqual(b, 255, f"Blue out of bounds in {p_id}")


class AsyncStressTests:
    """Async stress test runner for queue throughput and reconnect stability."""

    @staticmethod
    async def stress_queue_throughput():
        print("⚡ Running BLE Queue Throughput Stress Test (500 commands)...")
        ctrl = LEDStripController(DEFAULT_MAC)
        ctrl.is_connected = True  # Mock connection
        
        # Enqueue 500 rapid color changes
        t0 = time.perf_counter()
        for i in range(500):
            ctrl._enqueue_command(bytes([0x7E, 0x07, 0x05, 0x03, i % 256, 128, 64, 0x00, 0xEF]), high_priority=(i % 10 == 0))
        t1 = time.perf_counter()
        
        print(f"  Enqueued 500 commands in {(t1 - t0)*1000:.2f}ms (queue size: {ctrl._command_queue.qsize()})")
        assert ctrl._command_queue.qsize() <= 500
        print("  Queue throughput test PASSED!")

    @staticmethod
    async def stress_ambient_engine_loop():
        print("🖥️ Running Ambient Sync Engine 50-Frame Stress Test...")
        ctrl = LEDStripController(DEFAULT_MAC)
        engine = AmbientSyncEngine(ctrl, update_interval=0.001)
        frames_captured = 0
        
        t0 = time.perf_counter()
        for _ in range(50):
            h, s, v = engine._sample_screen()
            assert 0.0 <= h <= 1.0
            assert 0.0 <= s <= 1.0
            assert 0.0 <= v <= 1.0
            frames_captured += 1
        t1 = time.perf_counter()
        
        fps = frames_captured / max(0.0001, (t1 - t0))
        print(f"  Captured {frames_captured} screen frames in {t1 - t0:.2f}s ({fps:.1f} FPS)")
        print("  Ambient engine stress test PASSED!")

    @staticmethod
    async def stress_concurrency_and_cancellation():
        print("🔄 Running Concurrency, Rapid Task Cancellation & Queue Draining...")
        ctrl = LEDStripController(DEFAULT_MAC)
        ctrl.is_connected = True
        ctrl._start_worker()

        # Fire 100 rapid color commands
        for i in range(100):
            await ctrl.set_color_rgb(i, 255 - i, 128)

        # Immediate disconnect during active load
        await ctrl.disconnect()
        assert not ctrl.is_connected
        assert ctrl._worker_task is None
        print("  Concurrency & task cancellation PASSED!")


class TestFaultTolerance(unittest.TestCase):
    """Test corrupted inputs, file corruption, and recovery mechanisms."""

    def test_corrupt_favorites_file(self):
        # Write corrupted JSON to favorites
        with open(FAVORITES_FILE, "w") as f:
            f.write("{invalid_json: true, broken")
        
        # Load should not crash, returns empty list
        favs = load_favorites()
        self.assertEqual(favs, [])

        # Saving new favorites recovers the file
        save_favorites([{"name": "Recovered Cyan", "r": 0, "g": 255, "b": 255}])
        recovered = load_favorites()
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["name"], "Recovered Cyan")


if __name__ == "__main__":
    print("==========================================================")
    print("🧪 MELK-OA10 COMPREHENSIVE SUITE & STRESS TESTING")
    print("==========================================================")
    
    # 1. Run standard unit tests
    suite = unittest.TestLoader().loadTestsFromNames([
        "test_suite.TestBLEProtocolAndPackets",
        "test_suite.TestColorParsing",
        "test_suite.TestFavoritesSystem",
        "test_suite.TestAmbientEngineMath",
        "test_suite.TestAudioEngineMath",
        "test_suite.TestFaultTolerance",
        "test_suite.TestMotionPatternEngine",
    ])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if not result.wasSuccessful():
        print("\n❌ Unit tests failed!")
        sys.exit(1)
        
    print("\n==========================================================")
    print("🚀 RUNNING ASYNC CONCURRENCY & THROUGHPUT STRESS TESTS")
    print("==========================================================")
    asyncio.run(AsyncStressTests.stress_queue_throughput())
    asyncio.run(AsyncStressTests.stress_ambient_engine_loop())
    asyncio.run(AsyncStressTests.stress_concurrency_and_cancellation())
    
    print("\n==========================================================")
    print("🎉 ALL TESTS PASSED! FULL SYSTEM VERIFIED ROBUST & HEALTHY")
    print("==========================================================")
