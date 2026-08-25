import asyncio
import logging
import sys
import time
from typing import Optional, Tuple

logger = logging.getLogger("MELK_LED")

DEFAULT_MAC = "BE:69:29:00:0A:23"
WRITE_CHAR_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"

def mac_str_to_int(mac: str) -> int:
    clean = mac.replace(":", "").replace("-", "").strip()
    return int(clean, 16)

class LEDStripController:
    """
    Controller for MELK-OA10 / ELK-BLEDOM Bluetooth LED Light Strip.
    Supports native WinRT direct GATT connection & BleakClient fallback.
    Features auto-reconnect, graceful shutdown, and connection health tracking.
    """

    def __init__(self, mac_address: str = DEFAULT_MAC):
        self.mac_address = mac_address
        self.mac_int = mac_str_to_int(mac_address)
        self.is_connected = False
        self._winrt_char = None
        self._winrt_dev = None
        self._bleak_client = None
        self._last_rgb = (0, 0, 0)
        self._power_state = True
        self._brightness = 100
        self._command_queue = asyncio.Queue()
        self._worker_task = None
        self.access_denied = False

        # Connection health tracking
        self._connected_since: Optional[float] = None
        self._write_count = 0
        self._write_errors = 0
        self._reconnect_count = 0
        self._shutting_down = False

    @property
    def connection_uptime(self) -> str:
        """Human-readable connection uptime string."""
        if not self._connected_since or not self.is_connected:
            return "N/A"
        elapsed = time.time() - self._connected_since
        if elapsed < 60:
            return f"{int(elapsed)}s"
        elif elapsed < 3600:
            return f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
        else:
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            return f"{h}h {m}m"

    @property
    def connection_health(self) -> str:
        """Connection health summary string."""
        if not self.is_connected:
            return "[Disconnected]"
        total = self._write_count + self._write_errors
        if total == 0:
            return "[OK] Connected (no writes yet)"
        rate = (self._write_count / total) * 100
        if rate >= 98:
            return f"[Excellent] {rate:.0f}% success"
        elif rate >= 90:
            return f"[Good] {rate:.0f}% success"
        else:
            return f"[Poor] {rate:.0f}% success"

    async def connect(self, timeout: float = 8.0) -> bool:
        """Connect directly via WinRT address handle or Bleak fallback."""
        if self.is_connected and (self._winrt_char or (self._bleak_client and self._bleak_client.is_connected)):
            return True

        logger.info(f"Connecting to LED strip {self.mac_address}...")
        self.access_denied = False

        # Strategy 1: Direct WinRT lookup (Instantaneous on Windows)
        if sys.platform == "win32":
            try:
                import winrt.windows.devices.bluetooth as bluetooth
                dev = await asyncio.wait_for(
                    bluetooth.BluetoothLEDevice.from_bluetooth_address_async(self.mac_int),
                    timeout=5.0
                )
                if dev:
                    services_res = await dev.get_gatt_services_async()
                    if services_res and services_res.services:
                        for s in services_res.services:
                            try:
                                chars_res = await s.get_characteristics_async()
                                if chars_res and chars_res.status == 3:  # AccessDenied
                                    self.access_denied = True
                                    logger.warning("WinRT Access Denied by LED strip (device connected elsewhere).")

                                if chars_res and chars_res.characteristics:
                                    for c in chars_res.characteristics:
                                        if "fff3" in str(c.uuid).lower():
                                            self._winrt_dev = dev
                                            self._winrt_char = c
                                            self.is_connected = True
                                            self._connected_since = time.time()
                                            self._start_worker()
                                            logger.info("Connected to LED strip via native WinRT engine!")
                                            return True
                            except Exception:
                                pass
            except Exception as e:
                logger.debug(f"WinRT direct connect failed: {e}")

        # Strategy 2: BleakClient fallback
        try:
            from bleak import BleakClient, BleakScanner
            ble_dev = await asyncio.wait_for(
                BleakScanner.find_device_by_address(self.mac_address, timeout=4.0),
                timeout=5.0
            )
            target = ble_dev if ble_dev else self.mac_address
            client = BleakClient(target, timeout=timeout)
            await asyncio.wait_for(client.connect(), timeout=timeout)
            if client.is_connected:
                self._bleak_client = client
                self.is_connected = True
                self._connected_since = time.time()
                self._start_worker()
                logger.info("Connected via BleakClient fallback!")
                return True
        except Exception as ex:
            logger.error(f"BleakClient connect error: {ex}")

        self.is_connected = False
        return False

    async def _write_bytes(self, packet: bytes) -> bool:
        """Write raw bytes to LED GATT characteristic."""
        if self._winrt_char:
            try:
                from winrt.windows.storage.streams import DataWriter
                dw = DataWriter()
                dw.write_bytes(packet)
                buf = dw.detach_buffer()
                await self._winrt_char.write_value_async(buf)
                self._write_count += 1
                return True
            except Exception as e:
                self._write_errors += 1
                logger.debug(f"WinRT write error: {e}")

        if self._bleak_client and self._bleak_client.is_connected:
            try:
                await self._bleak_client.write_gatt_char(WRITE_CHAR_UUID, packet, response=False)
                self._write_count += 1
                return True
            except Exception as e:
                self._write_errors += 1
                logger.debug(f"Bleak write error: {e}")
        return False

    async def _try_reconnect(self) -> bool:
        """Attempt to silently reconnect after a connection drop."""
        if self._shutting_down:
            return False
        logger.info("BLE connection lost — attempting auto-reconnect...")
        self._reconnect_count += 1
        # Clean up stale handles
        self._winrt_char = None
        if self._winrt_dev:
            try:
                self._winrt_dev.close()
            except Exception:
                pass
            self._winrt_dev = None
        if self._bleak_client:
            try:
                await self._bleak_client.disconnect()
            except Exception:
                pass
            self._bleak_client = None
        self.is_connected = False

        # Retry with exponential backoff (up to 3 attempts)
        for attempt in range(1, 4):
            delay = min(2.0 * attempt, 6.0)
            await asyncio.sleep(delay)
            logger.info(f"Reconnect attempt {attempt}/3...")
            try:
                success = await self.connect(timeout=6.0)
                if success:
                    logger.info(f"Auto-reconnect succeeded on attempt {attempt}!")
                    return True
            except Exception as e:
                logger.debug(f"Reconnect attempt {attempt} failed: {e}")
        logger.warning("Auto-reconnect failed after 3 attempts.")
        return False

    def _start_worker(self):
        """Start background queue worker for rate-limited BLE command writing."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue())

    async def _process_queue(self):
        """Processes queued BLE commands with auto-reconnect on failures."""
        consecutive_fails = 0
        while True:
            try:
                cmd_data = await self._command_queue.get()
                if self._shutting_down:
                    self._command_queue.task_done()
                    break

                if self.is_connected:
                    success = await self._write_bytes(cmd_data)
                    if success:
                        consecutive_fails = 0
                    else:
                        consecutive_fails += 1
                        if consecutive_fails >= 3:
                            reconnected = await self._try_reconnect()
                            if reconnected:
                                consecutive_fails = 0
                                # Retry the failed command
                                await self._write_bytes(cmd_data)
                            else:
                                consecutive_fails = 0  # Reset to avoid infinite reconnect loop
                else:
                    consecutive_fails += 1
                    if consecutive_fails >= 2:
                        await self._try_reconnect()
                        consecutive_fails = 0

                self._command_queue.task_done()
                await asyncio.sleep(0.035)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue error: {e}")

    def _enqueue_command(self, data: bytes, high_priority: bool = False):
        """Add command to write queue."""
        if high_priority:
            while not self._command_queue.empty():
                try:
                    self._command_queue.get_nowait()
                    self._command_queue.task_done()
                except asyncio.QueueEmpty:
                    break
        try:
            self._command_queue.put_nowait(data)
        except asyncio.QueueFull:
            pass

    async def set_color_rgb(self, r: int, g: int, b: int, immediate: bool = False, raw: bool = False):
        """
        Set RGB Color (0-255 for each channel).
        Performs RGB scaling according to self._brightness for 5V USB LED strips.
        Sends 9-byte format (7e 07 05 03 R G B 00 ef) and 8-byte format (7e 04 04 R G B 00 ef)
        for 100% compatibility across MELK-OA10 / Lotus / ELK-BLEDOM firmware revisions.
        """
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        
        self._last_rgb = (r, g, b)

        # Apply software brightness scaling for 5V strips (unless raw is True)
        if not raw:
            scale = max(0.0, min(1.0, self._brightness / 100.0))
            eff_r = max(0, min(255, int(round(r * scale))))
            eff_g = max(0, min(255, int(round(g * scale))))
            eff_b = max(0, min(255, int(round(b * scale))))
        else:
            eff_r, eff_g, eff_b = r, g, b

        # Standard 9-byte MELK-OA10 / Lotus color packet
        packet = bytes([0x7E, 0x07, 0x05, 0x03, eff_r, eff_g, eff_b, 0x00, 0xEF])

        if immediate and self.is_connected:
            await self._write_bytes(packet)
        else:
            self._enqueue_command(packet, high_priority=True)

    async def set_power(self, state: bool, immediate: bool = True):
        """Turn strip ON (state=True) or OFF (state=False)."""
        self._power_state = state
        if state:
            p_on = bytes([0x7E, 0x04, 0x04, 0xF0, 0x00, 0x01, 0xFF, 0xEF])
            if immediate and self.is_connected:
                await self._write_bytes(p_on)
            else:
                self._enqueue_command(p_on, high_priority=True)
            
            r, g, b = self._last_rgb
            if r == 0 and g == 0 and b == 0:
                r, g, b = (255, 255, 255)
            await self.set_color_rgb(r, g, b, immediate=immediate)
        else:
            p_off = bytes([0x7E, 0x04, 0x04, 0xF0, 0x00, 0x00, 0xFF, 0xEF])
            black1 = bytes([0x7E, 0x04, 0x04, 0x00, 0x00, 0x00, 0x00, 0xEF])
            black2 = bytes([0x7E, 0x07, 0x05, 0x03, 0x00, 0x00, 0x00, 0x00, 0xEF])
            
            if immediate and self.is_connected:
                await self._write_bytes(p_off)
                await self._write_bytes(black1)
                await self._write_bytes(black2)
            else:
                self._enqueue_command(p_off, high_priority=True)
                self._enqueue_command(black1, high_priority=False)
                self._enqueue_command(black2, high_priority=False)

    async def set_brightness(self, level_percent: int, immediate: bool = True):
        """
        Set brightness (0-100%).
        Sends both firmware hardware brightness packets AND re-scales the active RGB color
        so brightness works reliably on 5V USB LED strips.
        """
        level = max(0, min(100, int(level_percent)))
        self._brightness = level

        # Hardware firmware brightness packets (variants for all chipsets)
        p1 = bytes([0x7E, 0x04, 0x01, level, 0xFF, 0xFF, 0xFF, 0x00, 0xEF])
        p2 = bytes([0x7E, 0x00, 0x01, level, 0x00, 0x00, 0x00, 0x00, 0xEF])
        p3 = bytes([0x7E, 0x04, 0x01, level, 0x00, 0x00, 0x00, 0x00, 0xEF])

        if immediate and self.is_connected:
            await self._write_bytes(p1)
            await self._write_bytes(p2)
            await self._write_bytes(p3)
        else:
            self._enqueue_command(p1, high_priority=True)
            self._enqueue_command(p2, high_priority=False)
            self._enqueue_command(p3, high_priority=False)

        # Immediately update current color with new brightness level on 5V strips
        r, g, b = self._last_rgb
        if any((r, g, b)):
            await self.set_color_rgb(r, g, b, immediate=immediate, raw=False)

    async def set_effect(self, effect_id: int, immediate: bool = True):
        """
        Activate a built-in firmware effect mode.
        effect_id: 0x80-0x9C (see FIRMWARE_EFFECTS list for mappings).
        Packet format: 7E 00 03 <effect_id> 03 FF FF 00 EF
        """
        effect_id = max(0x80, min(0x9C, int(effect_id)))
        self._current_effect = effect_id
        packet = bytes([0x7E, 0x00, 0x03, effect_id, 0x03, 0xFF, 0xFF, 0x00, 0xEF])
        if immediate and self.is_connected:
            await self._write_bytes(packet)
        else:
            self._enqueue_command(packet, high_priority=True)

    async def set_effect_speed(self, speed: int, immediate: bool = True):
        """
        Set the speed for the currently active firmware effect.
        speed: 0 (fastest) to 100 (slowest).
        Packet format: 7E 04 02 <speed> FF FF FF 00 EF
        """
        speed = max(0, min(100, int(speed)))
        packet = bytes([0x7E, 0x04, 0x02, speed, 0xFF, 0xFF, 0xFF, 0x00, 0xEF])
        if immediate and self.is_connected:
            await self._write_bytes(packet)
        else:
            self._enqueue_command(packet, high_priority=True)

    async def disconnect(self):
        """Disconnect from BLE device with graceful queue drain."""
        self._shutting_down = True

        # Drain remaining commands (with 2s timeout)
        if not self._command_queue.empty():
            try:
                await asyncio.wait_for(self._command_queue.join(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.debug("Queue drain timed out, forcing disconnect.")
            except Exception:
                pass

        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except (asyncio.CancelledError, Exception):
                pass
            self._worker_task = None

        if self._bleak_client:
            try:
                await self._bleak_client.disconnect()
            except Exception:
                pass
            self._bleak_client = None
        if self._winrt_dev:
            try:
                self._winrt_dev.close()
            except Exception:
                pass
        self._winrt_char = None
        self._winrt_dev = None
        self.is_connected = False
        self._connected_since = None
        self._shutting_down = False


async def scan_all_ble_devices(timeout: float = 5.0):
    """Scan and return all nearby BLE devices."""
    try:
        from bleak import BleakScanner
        discovered = await BleakScanner.discover(timeout=timeout, return_adv=True)
        result = []
        for address, (device, adv) in discovered.items():
            result.append({
                "name": device.name or adv.local_name or "Unknown",
                "address": device.address,
                "rssi": adv.rssi if hasattr(adv, "rssi") else "N/A"
            })
        return result
    except Exception as e:
        logger.error(f"Scan all error: {e}")
        return []
