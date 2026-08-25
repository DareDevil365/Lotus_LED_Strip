import argparse
import asyncio
import colorsys
import json
import math
import os
import sys
import time
from typing import Optional, Tuple, Union

# Enable VT100 mode on Windows Console for ANSI colors
if sys.platform == "win32":
    try:
        os.system("")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.progress import BarColumn, Progress, TextColumn

from ble_controller import LEDStripController, scan_all_ble_devices, DEFAULT_MAC
from ambient_engine import AmbientSyncEngine
from motion_engine import MotionPatternEngine

console = Console()

# ---------------------------------------------------------------------------
# Favorites file (same directory as main.py)
# ---------------------------------------------------------------------------
FAVORITES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favorites.json")

def load_favorites() -> list:
    """Load saved color favorites from disk."""
    try:
        if os.path.exists(FAVORITES_FILE):
            with open(FAVORITES_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []

def save_favorites(favs: list):
    """Save color favorites to disk."""
    try:
        with open(FAVORITES_FILE, "w") as f:
            json.dump(favs, f, indent=2)
    except Exception as e:
        console.print(f"[bold red]Could not save favorites: {e}[/bold red]")

# ---------------------------------------------------------------------------
# Presets & Named Colors
# ---------------------------------------------------------------------------
PRESETS = [
    ("cyberpunk", "Cyberpunk Pink", (255, 0, 128)),
    ("sunset", "Sunset Orange", (255, 90, 0)),
    ("ocean", "Ocean Deep Blue", (0, 180, 255)),
    ("vaporwave", "Vaporwave Purple", (180, 0, 255)),
    ("emerald", "Emerald Green", (0, 255, 128)),
    ("warm_white", "Warm White", (255, 210, 150)),
    ("pure_red", "Pure Red", (255, 0, 0)),
    ("pure_green", "Pure Green", (0, 255, 0)),
    ("pure_blue", "Pure Blue", (0, 0, 255)),
    ("cyan_glow", "Cyan Glow", (0, 255, 255)),
    ("gold", "Golden Amber", (255, 191, 0)),
    ("ice_blue", "Ice Cold White", (200, 235, 255)),
]

NAMED_COLORS = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "cyan": (0, 255, 255),
    "aqua": (0, 255, 255),
    "yellow": (255, 255, 0),
    "orange": (255, 128, 0),
    "purple": (180, 0, 255),
    "pink": (255, 105, 180),
    "white": (255, 255, 255),
    "warm white": (255, 210, 150),
    "warm": (255, 210, 150),
    "cool white": (200, 235, 255),
    "gold": (255, 191, 0),
    "amber": (255, 191, 0),
    "emerald": (0, 255, 128),
    "lime": (50, 255, 50),
    "magenta": (255, 0, 255),
    "fuchsia": (255, 0, 255),
    "violet": (238, 130, 238),
    "indigo": (75, 0, 130),
    "teal": (0, 128, 128),
    "navy": (0, 0, 128),
    "coral": (255, 127, 80),
    "turquoise": (64, 224, 208),
    "lavender": (150, 100, 255),
    "salmon": (250, 128, 114),
    "crimson": (220, 20, 60),
    "maroon": (128, 0, 0),
    "olive": (128, 128, 0),
    "sky blue": (135, 206, 235),
    "hot pink": (255, 105, 180),
    "peach": (255, 218, 185),
    "rose": (255, 0, 127),
}

# ---------------------------------------------------------------------------
# Hardware / Firmware Built-in Effects (MELK-OA10 / ELK-BLEDOM)
# ---------------------------------------------------------------------------
FIRMWARE_EFFECTS = [
    (1, "7-Color Smooth Spectrum Flow", 0x8A, "Smooth seamless crossfade across all colors"),
    (2, "3-Color RGB Smooth Flow", 0x89, "Smooth crossfade between Red, Green, Blue"),
    (3, "7-Color Rainbow Jump", 0x88, "Sharp stepping through 7 vivid colors"),
    (4, "3-Color RGB Jump", 0x87, "Sharp stepping Red -> Green -> Blue"),
    (5, "Dynamic Chase / Flow 1", 0x94, "Flowing light train along the strip"),
    (6, "Dynamic Chase / Flow 2", 0x95, "Fast flowing chasing animation"),
    (7, "Center-to-Ends Running Lights", 0x96, "Light starts in center and splits to both ends"),
    (8, "Ends-to-Center Running Lights", 0x97, "Light flows from both ends into the center"),
    (9, "Meteor / Comet Trail Flow", 0x98, "Trailing meteor effect along the strip"),
    (10, "Wave / Waterfall Motion", 0x9A, "Rippling wave flow motion"),
    (11, "7-Color Strobe / Flash", 0x92, "High energy multi-color strobe"),
    (12, "3-Color RGB Strobe / Flash", 0x93, "Red/Green/Blue alternating strobe"),
    (13, "Red Pulse / Breathe", 0x80, "Smooth pulsing breathing red"),
    (14, "Green Pulse / Breathe", 0x81, "Smooth pulsing breathing green"),
    (15, "Blue Pulse / Breathe", 0x82, "Smooth pulsing breathing blue"),
    (16, "Yellow Pulse / Breathe", 0x83, "Smooth pulsing breathing yellow"),
    (17, "Cyan Pulse / Breathe", 0x84, "Smooth pulsing breathing cyan"),
    (18, "Purple Pulse / Breathe", 0x85, "Smooth pulsing breathing purple"),
    (19, "White Pulse / Breathe", 0x86, "Smooth pulsing breathing white"),
    (20, "White Strobe / Flash", 0x91, "Pure white high-speed strobe"),
]

# ---------------------------------------------------------------------------
# Auto-off timer state (global so it persists across menu loops)
# ---------------------------------------------------------------------------
_auto_off_task: Optional[asyncio.Task] = None
_auto_off_remaining: float = 0.0


def parse_color_input(val: Union[str, tuple, list]) -> Tuple[Optional[Tuple[int, int, int]], Optional[str]]:
    """
    Universally parse color from:
    - Preset numbers ('1'..'12')
    - Preset names ('cyberpunk', 'cyan glow', 'cyan_glow')
    - Hex strings ('#ff0055', 'ff0055', '#f05', 'f05', '0xff0055')
    - RGB strings ('255, 0, 85', '255 0 85', 'rgb(255,0,85)')
    - HSL strings ('hsl(300, 100%, 50%)')
    - Standard color names ('red', 'green', 'warm white', 'gold', etc.)
    - Special commands ('on', 'off')

    Returns: ((r, g, b), command_type)
    """
    if isinstance(val, (list, tuple)) and len(val) == 3:
        return (max(0, min(255, int(val[0]))),
                max(0, min(255, int(val[1]))),
                max(0, min(255, int(val[2])))), "color"

    s = str(val).strip().lower()

    if s in ["off", "power off", "shutdown", "black", "kill"]:
        return (0, 0, 0), "power_off"
    if s in ["on", "power on", "start"]:
        return None, "power_on"

    # 1. Preset Number (1..N)
    if s.isdigit():
        idx = int(s)
        if 1 <= idx <= len(PRESETS):
            return PRESETS[idx - 1][2], f"preset_{PRESETS[idx - 1][1]}"

    # 2. Preset Name
    clean_s = s.replace("_", " ").replace("-", " ")
    for p_id, p_name, rgb in PRESETS:
        if s == p_id or clean_s == p_name.lower() or s == p_name.lower() or clean_s == p_id.replace("_", " "):
            return rgb, f"preset_{p_name}"

    # 3. Named Color
    if s in NAMED_COLORS:
        return NAMED_COLORS[s], f"named_{s.title()}"
    if clean_s in NAMED_COLORS:
        return NAMED_COLORS[clean_s], f"named_{clean_s.title()}"

    # 4. Hex format (#ff0055, ff0055, #f05, f05, 0xff0055)
    hex_clean = s.lstrip("#").lower()
    if hex_clean.startswith("0x"):
        hex_clean = hex_clean[2:]
    if len(hex_clean) == 3 and all(c in "0123456789abcdef" for c in hex_clean):
        hex_clean = "".join([c * 2 for c in hex_clean])
    if len(hex_clean) == 6 and all(c in "0123456789abcdef" for c in hex_clean):
        r, g, b = int(hex_clean[0:2], 16), int(hex_clean[2:4], 16), int(hex_clean[4:6], 16)
        return (r, g, b), "hex"

    # 5. HSL format: hsl(300, 100%, 50%)
    if s.startswith("hsl"):
        try:
            inner = s.replace("hsl", "").replace("(", "").replace(")", "").replace("%", "")
            parts = [p.strip() for p in inner.split(",")]
            if len(parts) == 3:
                h_deg = float(parts[0]) / 360.0
                s_val = float(parts[1]) / 100.0
                l_val = float(parts[2]) / 100.0
                # HSL to RGB
                import colorsys as _cs
                r_f, g_f, b_f = _cs.hls_to_rgb(h_deg, l_val, s_val)
                return (int(r_f * 255), int(g_f * 255), int(b_f * 255)), "hsl"
        except Exception:
            pass

    # 6. RGB separated by commas, spaces, or semicolons
    s_rgb = s.replace("rgb", "").replace("(", "").replace(")", "").replace("[", "").replace("]", "")
    for delim in [",", " ", ";"]:
        if delim in s_rgb:
            parts = [p.strip() for p in s_rgb.split(delim) if p.strip()]
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                r = max(0, min(255, int(parts[0])))
                g = max(0, min(255, int(parts[1])))
                b = max(0, min(255, int(parts[2])))
                return (r, g, b), "rgb"

    return None, None


def make_color_block(r: int, g: int, b: int, width: int = 10) -> Text:
    """Create a colored terminal block text using spaces and background color."""
    style_str = f"on rgb({r},{g},{b})"
    return Text(" " * width, style=style_str)


def make_large_color_preview(r: int, g: int, b: int) -> Text:
    """Create a big multi-line color preview block."""
    block = Text()
    line = " " * 40
    style_str = f"on rgb({r},{g},{b})"
    for _ in range(3):
        block.append(line, style=style_str)
        block.append("\n")
    return block


def render_help_panel() -> Panel:
    """Render a quick-reference help panel."""
    help_text = (
        "[bold cyan]Color Formats Accepted Everywhere:[/bold cyan]\n"
        "  [yellow]Names:[/yellow]       red, cyan, warm white, hot pink, lavender, ...\n"
        "  [yellow]Hex:[/yellow]         #FF0055, FF0055, #F05, 0xFF0055\n"
        "  [yellow]RGB:[/yellow]         255, 0, 85  |  255 0 85  |  rgb(255,0,85)\n"
        "  [yellow]HSL:[/yellow]         hsl(300, 100%, 50%)\n"
        "  [yellow]Preset #:[/yellow]    1 through 12 (see Option 3 for list)\n\n"
        "[bold cyan]Global Shortcuts (type anywhere):[/bold cyan]\n"
        "  [green]on[/green]  / [red]off[/red]     Turn strip on/off\n"
        "  [green]sync[/green]           Start ambient screen sync\n"
        "  [green]help[/green] / [green]?[/green]       Show this reference\n"
        "  [green]q[/green] / [green]back[/green]      Return to previous menu\n"
        "  Any color directly from the main menu (e.g. 'red', '#00ffff', '10')"
    )
    return Panel(help_text, title="[bold green]📖 Quick Reference[/bold green]", border_style="green")


# ---------------------------------------------------------------------------
# Effect Modes
# ---------------------------------------------------------------------------

async def run_ambient_sync_cli(controller: LEDStripController, zone: str = "full", brightness: int = 30):
    """Run intelligent stable theme ambient lighting."""
    engine = AmbientSyncEngine(controller, zone=zone, brightness=brightness)
    
    console.print(Panel(
        f"[bold cyan]🖥️ Intelligent Theme Ambient Lighting Active[/bold cyan]\n"
        f"Zone: [bold yellow]{zone.upper()}[/bold yellow] | Brightness: [bold green]{brightness}%[/bold green]\n"
        f"Behavior: [bold green]Adopts screen/movie theme color and holds rock-solid (Zero Fluctuations)[/bold green]\n"
        f"Press [bold red]Ctrl+C[/bold red] to return to menu.",
        title="[bold green]Stable Ambient Light[/bold green]", border_style="cyan"
    ))

    def on_theme_change(rgb):
        r, g, b = rgb
        console.print(f"[bold green]✨ Screen Theme:[/bold green] {engine.locked_name}  RGB({r}, {g}, {b}) ", make_color_block(r, g, b, width=12))

    engine.on_color_update = on_theme_change
    await engine.start()

    try:
        while engine.running:
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        await engine.stop()
        console.print("[yellow]Ambient Theme Lighting stopped.[/yellow]")


async def run_color_cycle(controller: LEDStripController, speed: str = "medium"):
    """Smooth rainbow / color cycle mode."""
    speed_map = {"slow": 0.003, "medium": 0.008, "fast": 0.020}
    hue_step = speed_map.get(speed, 0.008)

    console.print(Panel(
        f"[bold magenta]🌀 Rainbow Color Cycle Active[/bold magenta]\n"
        f"Speed: [bold yellow]{speed.upper()}[/bold yellow] | Press [bold red]Ctrl+C[/bold red] to stop.",
        title="[bold magenta]Rainbow Mode[/bold magenta]", border_style="magenta"
    ))

    if controller.is_connected:
        await controller.set_power(True, immediate=True)

    hue = 0.0
    try:
        with Live(console=console, refresh_per_second=15) as live:
            while True:
                r_f, g_f, b_f = colorsys.hsv_to_rgb(hue, 1.0, 0.95)
                r, g, b = int(r_f * 255), int(g_f * 255), int(b_f * 255)

                if controller.is_connected:
                    await controller.set_color_rgb(r, g, b, immediate=True)

                display = Text()
                display.append("  Hue: ", style="bold white")
                display.append(f"{int(hue * 360):3d}°", style="bold yellow")
                display.append("  Color: ", style="bold white")
                display.append(" " * 22, style=f"on rgb({r},{g},{b})")
                display.append(f"  RGB({r:3d}, {g:3d}, {b:3d})", style="dim white")

                live.update(Panel(display, title="[bold magenta]🌈 Rainbow Cycle[/bold magenta]", border_style="magenta"))

                hue = (hue + hue_step) % 1.0
                await asyncio.sleep(0.060)
    except KeyboardInterrupt:
        pass
async def run_motion_pattern_cli(controller: LEDStripController, pattern_id: str = "rainbow_wave", speed: float = 1.0, brightness: int = 80):
    """Run procedural software motion pattern with live terminal visualization."""
    pat_name = pattern_id.title()
    for p_id, p_title, p_desc in MotionPatternEngine.PATTERNS:
        if pattern_id.lower() in [p_id, p_title.lower()] or pattern_id == p_id:
            pat_name = p_title
            break

    console.print(Panel(
        f"[bold cyan]🌊 Motion Animation Pattern Active[/bold cyan]\n"
        f"Pattern: [bold yellow]{pat_name}[/bold yellow] | Speed: [bold green]{speed}x[/bold green] | Brightness: [bold green]{brightness}%[/bold green]\n"
        f"Press [bold red]Ctrl+C[/bold red] to return to menu.",
        title="[bold green]Procedural Motion Engine[/bold green]", border_style="cyan"
    ))

    engine = MotionPatternEngine(controller, pattern_id=pattern_id, speed=speed, brightness=brightness)
    last_rgb = (0, 0, 0)

    def on_frame(rgb, pid):
        nonlocal last_rgb
        last_rgb = rgb

    engine.on_frame_update = on_frame
    await engine.start()

    try:
        with Live(console=console, refresh_per_second=15) as live:
            while engine.running:
                r, g, b = last_rgb
                color_text = Text()
                color_text.append("  Pattern: ", style="bold white")
                color_text.append(f"{pat_name:28s} ", style="bold yellow")
                color_text.append(" " * 18, style=f"on rgb({r},{g},{b})")
                color_text.append(f"  RGB({r:3d}, {g:3d}, {b:3d})  #{r:02x}{g:02x}{b:02x}", style="dim white")

                panel = Panel(color_text, title="[bold cyan]✨ Live Motion Stream[/bold cyan]", border_style="cyan")
                live.update(panel)
                await asyncio.sleep(0.060)
    except KeyboardInterrupt:
        pass
    finally:
        await engine.stop()
        console.print("[yellow]Motion pattern stopped.[/yellow]")


async def run_strobe_mode(controller: LEDStripController, color: Tuple[int, int, int] = (255, 255, 255), bpm: int = 120):
    """Strobe / flash mode at specified BPM."""
    interval = 60.0 / bpm / 2.0  # half-period for on/off

    r, g, b = color
    console.print(Panel(
        f"[bold yellow]⚡ Strobe Mode Active[/bold yellow]\n"
        f"Color: RGB({r},{g},{b}) | BPM: [bold yellow]{bpm}[/bold yellow] | Press [bold red]Ctrl+C[/bold red] to stop.",
        title="[bold yellow]Strobe / Flash[/bold yellow]", border_style="yellow"
    ))

    if controller.is_connected:
        await controller.set_power(True, immediate=True)

    on = True
    try:
        with Live(console=console, refresh_per_second=10) as live:
            while True:
                if on:
                    await controller.set_color_rgb(r, g, b, immediate=True)
                    status = Text("  ███████████████████████  ON ", style=f"bold on rgb({r},{g},{b})")
                else:
                    await controller.set_color_rgb(0, 0, 0, immediate=True)
                    status = Text("  ░░░░░░░░░░░░░░░░░░░░░  OFF", style="dim")

                live.update(Panel(status, title="[bold yellow]⚡ Strobe[/bold yellow]", border_style="yellow"))
                on = not on
                await asyncio.sleep(interval)
    except KeyboardInterrupt:
        pass
    # Restore color
    await controller.set_color_rgb(r, g, b, immediate=True)
    console.print("[yellow]Strobe stopped.[/yellow]")


async def run_breathing_mode(controller: LEDStripController, color: Tuple[int, int, int] = (0, 180, 255), cycle_time: float = 4.0):
    """Breathing / pulse effect — smooth sinusoidal brightness modulation."""
    r_base, g_base, b_base = color
    console.print(Panel(
        f"[bold blue]💫 Breathing Mode Active[/bold blue]\n"
        f"Color: RGB({r_base},{g_base},{b_base}) | Cycle: [bold yellow]{cycle_time}s[/bold yellow] | Press [bold red]Ctrl+C[/bold red] to stop.",
        title="[bold blue]Breathing / Pulse[/bold blue]", border_style="blue"
    ))

    if controller.is_connected:
        await controller.set_power(True, immediate=True)

    t = 0.0
    try:
        with Live(console=console, refresh_per_second=15) as live:
            while True:
                # Sinusoidal brightness: oscillates between 0.15 and 1.0
                brightness = 0.15 + 0.85 * (0.5 + 0.5 * math.sin(2.0 * math.pi * t / cycle_time))
                r = max(10, int(r_base * brightness))
                g = max(10, int(g_base * brightness))
                b = max(10, int(b_base * brightness))

                if controller.is_connected:
                    await controller.set_color_rgb(r, g, b, immediate=True)

                bar_len = int(brightness * 30)
                display = Text()
                display.append("  Brightness: ", style="bold white")
                display.append("█" * bar_len, style=f"rgb({r},{g},{b})")
                display.append("░" * (30 - bar_len), style="dim")
                display.append(f"  {int(brightness * 100):3d}%", style="bold white")
                display.append("  ", style="")
                display.append(" " * 12, style=f"on rgb({r},{g},{b})")

                live.update(Panel(display, title="[bold blue]💫 Breathing[/bold blue]", border_style="blue"))

                t += 0.050
                await asyncio.sleep(0.050)
    except KeyboardInterrupt:
        pass
    # Restore full brightness
    await controller.set_color_rgb(r_base, g_base, b_base, immediate=True)
    console.print("[yellow]Breathing mode stopped.[/yellow]")


async def run_music_reactive(controller: LEDStripController):
    """Music reactive mode using microphone input."""
    try:
        from audio_engine import MusicReactiveEngine, is_available
    except ImportError:
        console.print("[bold red]audio_engine.py not found![/bold red]")
        return

    if not is_available():
        console.print(Panel(
            "[bold red]sounddevice is not installed![/bold red]\n\n"
            "Install it with:\n"
            "  [bold cyan]pip install sounddevice[/bold cyan]\n\n"
            "This is required for the Music Reactive mode to capture microphone audio.",
            title="[bold red]Missing Dependency[/bold red]", border_style="red"
        ))
        await asyncio.sleep(2.0)
        return

    console.print(Panel(
        "[bold green]🎵 Music Reactive Mode Active[/bold green]\n"
        "Listening to microphone / system audio...\n"
        "Press [bold red]Ctrl+C[/bold red] to stop.",
        title="[bold green]Music Reactive Lighting[/bold green]", border_style="green"
    ))

    engine = MusicReactiveEngine(controller)
    last_rgb = (80, 40, 120)
    last_levels = (0.0, 0.0, 0.0, 0.0)

    def on_color(rgb):
        nonlocal last_rgb
        last_rgb = rgb

    def on_levels(bass, mid, treble, vol):
        nonlocal last_levels
        last_levels = (bass, mid, treble, vol)

    engine.on_color_update = on_color
    engine.on_level_update = on_levels

    await engine.start()

    try:
        with Live(console=console, refresh_per_second=15) as live:
            while engine.running:
                r, g, b = last_rgb
                bass, mid, treble, vol = last_levels

                display = Text()
                # Color preview
                display.append("  Color: ", style="bold white")
                display.append(" " * 22, style=f"on rgb({r},{g},{b})")
                display.append(f"  RGB({r:3d}, {g:3d}, {b:3d})\n", style="dim white")

                # Spectrum bars
                def bar(label, value, color):
                    filled = int(value * 25)
                    display.append(f"  {label}: ", style="bold white")
                    display.append("█" * filled, style=color)
                    display.append("░" * (25 - filled), style="dim")
                    display.append(f"  {int(value * 100):3d}%\n", style="dim white")

                bar("Bass  ", bass, "bold red")
                bar("Mid   ", mid, "bold green")
                bar("Treble", treble, "bold blue")
                bar("Volume", vol, "bold yellow")

                live.update(Panel(display, title="[bold green]🎵 Music Reactive[/bold green]", border_style="green"))
                await asyncio.sleep(0.060)
    except KeyboardInterrupt:
        pass
    finally:
        await engine.stop()
    console.print("[yellow]Music Reactive mode stopped.[/yellow]")


# ---------------------------------------------------------------------------
# Auto-Off Timer
# ---------------------------------------------------------------------------

async def _auto_off_countdown(controller: LEDStripController, minutes: float):
    """Background task that powers off the strip after N minutes."""
    global _auto_off_remaining
    _auto_off_remaining = minutes * 60.0
    try:
        while _auto_off_remaining > 0:
            await asyncio.sleep(1.0)
            _auto_off_remaining -= 1.0
        # Time's up — power off
        if controller.is_connected:
            await controller.set_power(False, immediate=True)
        console.print(f"\n[bold yellow]⏰ Auto-off timer expired — LED strip powered OFF.[/bold yellow]")
    except asyncio.CancelledError:
        pass
    finally:
        _auto_off_remaining = 0.0


def start_auto_off(controller: LEDStripController, minutes: float):
    """Start (or restart) the auto-off timer."""
    global _auto_off_task
    if _auto_off_task and not _auto_off_task.done():
        _auto_off_task.cancel()
    _auto_off_task = asyncio.create_task(_auto_off_countdown(controller, minutes))


def cancel_auto_off():
    """Cancel any running auto-off timer."""
    global _auto_off_task, _auto_off_remaining
    if _auto_off_task and not _auto_off_task.done():
        _auto_off_task.cancel()
    _auto_off_task = None
    _auto_off_remaining = 0.0


# ---------------------------------------------------------------------------
# UI Rendering
# ---------------------------------------------------------------------------

def render_presets_table() -> Table:
    """Render a clean, colorful table of available presets with numbers."""
    table = Table(title="🌈 Available Color Presets", box=None, padding=(0, 2))
    table.add_column("No.", style="bold yellow", justify="right")
    table.add_column("Preset Name", style="bold white")
    table.add_column("RGB", style="dim white")
    table.add_column("Preview", style="white")

    for i, (p_id, p_name, rgb) in enumerate(PRESETS, 1):
        table.add_row(f"[bold yellow]{i}.[/bold yellow]", p_name, f"{rgb[0]:3d}, {rgb[1]:3d}, {rgb[2]:3d}", make_color_block(rgb[0], rgb[1], rgb[2]))
    return table


def render_favorites_table(favs: list) -> Table:
    """Render a table of saved favorites."""
    table = Table(title="⭐ Your Saved Favorites", box=None, padding=(0, 2))
    table.add_column("No.", style="bold yellow", justify="right")
    table.add_column("Name", style="bold white")
    table.add_column("RGB", style="dim white")
    table.add_column("Preview", style="white")

    for i, fav in enumerate(favs, 1):
        r, g, b = fav["r"], fav["g"], fav["b"]
        table.add_row(f"[bold yellow]{i}.[/bold yellow]", fav.get("name", "Untitled"), f"{r:3d}, {g:3d}, {b:3d}", make_color_block(r, g, b))
    return table


def render_firmware_effects_table() -> Table:
    """Render a table of built-in firmware hardware effects."""
    table = Table(title="✨ Hardware Firmware Dynamic Effects (20 Modes)", box=None, padding=(0, 2))
    table.add_column("No.", style="bold yellow", justify="right")
    table.add_column("Effect Name", style="bold white")
    table.add_column("Description", style="dim white")

    for no, name, hex_id, desc in FIRMWARE_EFFECTS:
        table.add_row(f"[bold yellow]{no}.[/bold yellow]", name, desc)
    return table


def render_motion_patterns_table() -> Table:
    """Render a table of procedural software motion patterns."""
    table = Table(title="🌊 Procedural Motion Patterns (11 Dynamic Animations)", box=None, padding=(0, 2))
    table.add_column("No.", style="bold yellow", justify="right")
    table.add_column("Pattern Name", style="bold white")
    table.add_column("Description", style="dim white")

    for i, (p_id, p_name, p_desc) in enumerate(MotionPatternEngine.PATTERNS, 1):
        table.add_row(f"[bold yellow]{i}.[/bold yellow]", p_name, p_desc)
    return table



def render_header(controller: LEDStripController) -> Panel:
    """Render the main menu header with connection status, color, and health."""
    status_str = "[bold green]CONNECTED[/bold green]" if controller.is_connected else "[bold red]DISCONNECTED[/bold red]"
    power_str = "[bold green]ON[/bold green]" if controller._power_state else "[bold red]OFF[/bold red]"

    r, g, b = controller._last_rgb
    color_preview = make_color_block(r, g, b, width=8) if any((r, g, b)) else Text("(none)", style="dim")

    # Connection health
    health = controller.connection_health
    uptime = controller.connection_uptime

    # Auto-off timer status
    timer_str = ""
    if _auto_off_remaining > 0:
        mins_left = int(_auto_off_remaining // 60)
        secs_left = int(_auto_off_remaining % 60)
        timer_str = f" | ⏰ Auto-off: [bold yellow]{mins_left}m {secs_left}s[/bold yellow]"

    header = Text()
    header.append("💡 MELK-OA10 Bluetooth LED Strip Controller\n", style="bold cyan")
    header.append(f"Device: ", style="")
    header.append(f"{controller.mac_address}", style="yellow")
    header.append(f" | Status: ")
    header.append_text(Text.from_markup(status_str))
    header.append(f" | Power: ")
    header.append_text(Text.from_markup(power_str))
    header.append(f"\n")
    header.append(f"Current Color: ", style="")
    header.append_text(color_preview)
    header.append(f" RGB({r}, {g}, {b}) #{r:02x}{g:02x}{b:02x}", style="dim white")
    header.append(f" | Brightness: {controller._brightness}%", style="")
    header.append(f"\nHealth: {health} | Uptime: {uptime}", style="dim")
    if timer_str:
        header.append_text(Text.from_markup(timer_str))

    return Panel(header, border_style="bright_blue")


# ---------------------------------------------------------------------------
# Interactive Menu
# ---------------------------------------------------------------------------

async def interactive_menu(controller: LEDStripController):
    """Run interactive terminal menu UI."""
    while True:
        console.clear()
        console.print(render_header(controller))

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[bold yellow]1.[/bold yellow]  🖥️  Ambient Screen Sync", "Match lights to PC screen content")
        table.add_row("[bold yellow]2.[/bold yellow]  🎨  Set Custom Color", "Hex, RGB, HSL, or Name")
        table.add_row("[bold yellow]3.[/bold yellow]  🌈  Color Presets", "12 presets (type number or name)")
        table.add_row("[bold yellow]4.[/bold yellow]  🔆  Brightness", "Set brightness level 0-100%")
        table.add_row("[bold yellow]5.[/bold yellow]  ⚡  Power Control", "ON / OFF / Toggle / Auto-Off Timer")
        table.add_row("[bold yellow]6.[/bold yellow]  🔍  Scan Bluetooth", "Search nearby BLE devices")
        table.add_row("[bold yellow]7.[/bold yellow]  🔌  Reconnect", "Retry connection to strip")
        table.add_row("[bold yellow]8.[/bold yellow]  🌀  Rainbow Cycle", "Smooth auto color cycling")
        table.add_row("[bold yellow]9.[/bold yellow]  ⚡  Strobe / Flash", "Rapid flashing effect")
        table.add_row("[bold yellow]10.[/bold yellow] 💫  Breathing / Pulse", "Smooth brightness pulsation")
        table.add_row("[bold yellow]11.[/bold yellow] 🎵  Music Reactive", "Audio-reactive lighting (mic)")
        table.add_row("[bold yellow]12.[/bold yellow] ⭐  Favorites", "Save & load custom colors")
        table.add_row("[bold yellow]13.[/bold yellow] ✨  Hardware Dynamic Effects", "Chase, spectrum flow, center-out (20 modes)")
        table.add_row("[bold yellow]14.[/bold yellow] 🌊  Motion Patterns", "Aurora, Fire, Ocean, Cyberpunk, Police, Waves (11 modes)")
        table.add_row("[bold yellow]0.[/bold yellow]  🚪  Exit", "Quit application")
        
        console.print(table)
        console.print("\n[dim]Tip: Type 'on', 'off', 'sync', 'help', a color ('red', '#ff0055'), or a preset number (1-12) anytime.[/dim]")

        raw_choice = Prompt.ask("\nSelect option or command", default="1").strip()
        choice_lower = raw_choice.lower()

        # ------- Global direct commands from main menu -------
        if choice_lower in ["0", "exit", "quit", "q"]:
            cancel_auto_off()
            console.print("[bold red]Exiting...[/bold red]")
            await controller.disconnect()
            sys.exit(0)

        elif choice_lower in ["help", "?"]:
            console.print(render_help_panel())
            Prompt.ask("\nPress Enter to return to menu...")
            continue

        elif choice_lower in ["off", "power off", "shutdown"]:
            if not controller.is_connected:
                await controller.connect()
            await controller.set_power(False, immediate=True)
            console.print("[bold red]⚡ Power turned OFF[/bold red]")
            await asyncio.sleep(1.2)
            continue

        elif choice_lower in ["on", "power on"]:
            if not controller.is_connected:
                await controller.connect()
            await controller.set_power(True, immediate=True)
            console.print("[bold green]⚡ Power turned ON[/bold green]")
            await asyncio.sleep(1.2)
            continue

        elif choice_lower in ["sync", "ambient"]:
            raw_choice = "1"

        # ------- Option 1: Ambient Sync -------
        if raw_choice == "1":
            if not controller.is_connected:
                console.print("[bold cyan]Connecting to LED strip...[/bold cyan]")
                await controller.connect()
            
            zone = Prompt.ask("Choose capture region [full/center/top/bottom/left/right]", choices=["full", "center", "top", "bottom", "left", "right", "q", "off", "on"], default="full")
            if zone == "q":
                continue
            elif zone == "off":
                await controller.set_power(False, immediate=True)
                console.print("[bold red]⚡ Power turned OFF[/bold red]")
                await asyncio.sleep(1.2)
                continue
            elif zone == "on":
                await controller.set_power(True, immediate=True)
                console.print("[bold green]⚡ Power turned ON[/bold green]")
                await asyncio.sleep(1.2)
                continue

            bright_in = Prompt.ask("Ambient Brightness % (10-100, default 30)", default="30").strip()
            if bright_in.lower() in ["q", "back"]:
                continue
            bright_val = int(bright_in.rstrip("%")) if bright_in.rstrip("%").isdigit() else 30
            bright_val = max(10, min(100, bright_val))

            await run_ambient_sync_cli(controller, zone=zone, brightness=bright_val)
            Prompt.ask("\nPress Enter to return to menu...")

        # ------- Option 2: Set Color -------
        elif raw_choice == "2":
            if not controller.is_connected:
                await controller.connect()
            
            color_in = Prompt.ask("Enter Color (Hex '#ff0055', RGB '255,0,85', HSL 'hsl(300,100%,50%)', Name 'cyan', Preset 1-12, or 'on'/'off')")
            if color_in.lower() in ["q", "back", "cancel"]:
                continue
            
            rgb, cmd = parse_color_input(color_in)
            if cmd == "power_off":
                await controller.set_power(False, immediate=True)
                console.print("[bold red]⚡ Power turned OFF[/bold red]")
            elif cmd == "power_on":
                await controller.set_power(True, immediate=True)
                console.print("[bold green]⚡ Power turned ON[/bold green]")
            elif rgb:
                r, g, b = rgb
                await controller.set_color_rgb(r, g, b, immediate=True)
                console.print(f"[bold green]Set Color to RGB({r}, {g}, {b})  #{r:02x}{g:02x}{b:02x}[/bold green]")
                console.print(make_large_color_preview(r, g, b))

                # Offer to save to favorites
                save_q = Prompt.ask("Save to favorites? (y/n)", default="n").lower()
                if save_q in ["y", "yes"]:
                    name = Prompt.ask("Favorite name", default=f"Color #{r:02x}{g:02x}{b:02x}")
                    favs = load_favorites()
                    favs.append({"name": name, "r": r, "g": g, "b": b})
                    save_favorites(favs)
                    console.print(f"[bold green]⭐ Saved '{name}' to favorites![/bold green]")
            else:
                console.print(f"[bold red]Could not recognize color input: '{color_in}'[/bold red]")
            await asyncio.sleep(1.4)

        # ------- Option 3: Presets -------
        elif raw_choice == "3":
            if not controller.is_connected:
                await controller.connect()
            
            console.print()
            console.print(render_presets_table())
            console.print("[dim]Type a number (1-12), preset name ('sunset'), color, or 'on'/'off' ('q' to go back)[/dim]")

            preset_in = Prompt.ask("Select preset or color", default="10")
            if preset_in.lower() in ["q", "back", "cancel"]:
                continue
            
            rgb, cmd = parse_color_input(preset_in)
            if cmd == "power_off":
                await controller.set_power(False, immediate=True)
                console.print("[bold red]⚡ Power turned OFF[/bold red]")
            elif cmd == "power_on":
                await controller.set_power(True, immediate=True)
                console.print("[bold green]⚡ Power turned ON[/bold green]")
            elif rgb:
                r, g, b = rgb
                await controller.set_color_rgb(r, g, b, immediate=True)
                console.print(f"[bold green]Applied: RGB({r}, {g}, {b})  #{r:02x}{g:02x}{b:02x}[/bold green]")
                console.print(make_large_color_preview(r, g, b))
            else:
                console.print(f"[bold red]Unknown preset: '{preset_in}'[/bold red]")
            await asyncio.sleep(1.4)

        # ------- Option 4: Brightness -------
        elif raw_choice == "4":
            if not controller.is_connected:
                await controller.connect()
            b_in = Prompt.ask("Set brightness (0-100%, or 'on'/'off')", default=str(controller._brightness))
            if b_in.lower() in ["q", "back"]:
                continue
            elif b_in.lower() in ["off"]:
                await controller.set_power(False, immediate=True)
                console.print("[bold red]⚡ Power turned OFF[/bold red]")
            elif b_in.lower() == "on":
                await controller.set_power(True, immediate=True)
                console.print("[bold green]⚡ Power turned ON[/bold green]")
            elif b_in.rstrip("%").isdigit():
                level = max(0, min(100, int(b_in.rstrip("%"))))
                if level == 0:
                    await controller.set_power(False, immediate=True)
                    console.print("[bold red]⚡ Brightness 0% — Power turned OFF[/bold red]")
                else:
                    await controller.set_brightness(level, immediate=True)
                    console.print(f"[bold green]Brightness set to {level}%[/bold green]")
            else:
                console.print("[bold red]Please enter a valid percentage 0-100[/bold red]")
            await asyncio.sleep(1.3)

        # ------- Option 5: Power Control -------
        elif raw_choice == "5":
            if not controller.is_connected:
                await controller.connect()

            console.print("\n[bold]Power Options:[/bold]")
            console.print("  [yellow]on[/yellow]      — Turn strip ON")
            console.print("  [yellow]off[/yellow]     — Turn strip OFF")
            console.print("  [yellow]toggle[/yellow]  — Toggle current state")
            console.print("  [yellow]timer N[/yellow] — Auto-off after N minutes")
            console.print("  [yellow]cancel[/yellow]  — Cancel auto-off timer")
            if _auto_off_remaining > 0:
                mins = int(_auto_off_remaining // 60)
                secs = int(_auto_off_remaining % 60)
                console.print(f"\n  [dim]⏰ Active timer: {mins}m {secs}s remaining[/dim]")

            p_in = Prompt.ask("\nPower command", default="toggle").lower().strip()
            if p_in in ["q", "back"]:
                continue

            if p_in.startswith("timer"):
                parts = p_in.split()
                if len(parts) >= 2 and parts[1].replace(".", "").isdigit():
                    mins = float(parts[1])
                    start_auto_off(controller, mins)
                    console.print(f"[bold green]⏰ Auto-off timer set for {mins} minute{'s' if mins != 1 else ''}.[/bold green]")
                else:
                    timer_mins = Prompt.ask("Minutes until auto-off", default="30")
                    if timer_mins.replace(".", "").isdigit():
                        start_auto_off(controller, float(timer_mins))
                        console.print(f"[bold green]⏰ Auto-off timer set for {timer_mins} minutes.[/bold green]")
                    else:
                        console.print("[bold red]Invalid number.[/bold red]")
            elif p_in == "cancel":
                cancel_auto_off()
                console.print("[bold yellow]⏰ Auto-off timer cancelled.[/bold yellow]")
            elif p_in in ["toggle", "t"]:
                target_state = not controller._power_state
                await controller.set_power(target_state, immediate=True)
                console.print(f"[bold {'green' if target_state else 'red'}]Power set to {'ON' if target_state else 'OFF'}[/bold {'green' if target_state else 'red'}]")
            elif p_in in ["on", "1", "yes", "true"]:
                await controller.set_power(True, immediate=True)
                console.print("[bold green]⚡ Power turned ON[/bold green]")
            else:
                await controller.set_power(False, immediate=True)
                console.print("[bold red]⚡ Power turned OFF[/bold red]")
            await asyncio.sleep(1.3)

        # ------- Option 6: Scan Bluetooth -------
        elif raw_choice == "6":
            console.print("[bold yellow]Scanning for BLE devices (5 sec)...[/bold yellow]")
            devs = await scan_all_ble_devices(timeout=5.0)
            dev_table = Table(title="Discovered Bluetooth BLE Devices")
            dev_table.add_column("#", style="bold yellow", justify="right")
            dev_table.add_column("Name", style="bold white")
            dev_table.add_column("MAC / Address", style="yellow")
            dev_table.add_column("RSSI (dBm)", style="cyan")

            for i, d in enumerate(devs, 1):
                dev_table.add_row(str(i), d["name"], d["address"], str(d["rssi"]))
            console.print(dev_table)
            Prompt.ask("\nPress Enter to return to menu...")

        # ------- Option 7: Reconnect -------
        elif raw_choice == "7":
            console.print("[bold yellow]Reconnecting to BLE device...[/bold yellow]")
            await controller.disconnect()
            success = await controller.connect()
            if success:
                console.print("[bold green]Successfully connected![/bold green]")
            else:
                console.print("[bold red]Connection failed. Make sure PC Bluetooth is ON and phone apps are closed.[/bold red]")
            await asyncio.sleep(1.8)

        # ------- Option 8: Rainbow Cycle -------
        elif raw_choice == "8":
            if not controller.is_connected:
                console.print("[bold cyan]Connecting...[/bold cyan]")
                await controller.connect()

            speed = Prompt.ask("Cycle speed [slow/medium/fast]", choices=["slow", "medium", "fast", "q"], default="medium")
            if speed == "q":
                continue
            await run_color_cycle(controller, speed=speed)
            Prompt.ask("\nPress Enter to return to menu...")

        # ------- Option 9: Strobe -------
        elif raw_choice == "9":
            if not controller.is_connected:
                console.print("[bold cyan]Connecting...[/bold cyan]")
                await controller.connect()

            color_in = Prompt.ask("Strobe color (name, hex, rgb, or 'white')", default="white")
            rgb, _ = parse_color_input(color_in)
            if not rgb:
                rgb = (255, 255, 255)

            bpm_in = Prompt.ask("BPM (beats per minute)", default="120")
            bpm = int(bpm_in) if bpm_in.isdigit() else 120
            bpm = max(30, min(600, bpm))

            await run_strobe_mode(controller, color=rgb, bpm=bpm)
            Prompt.ask("\nPress Enter to return to menu...")

        # ------- Option 10: Breathing -------
        elif raw_choice == "10":
            if not controller.is_connected:
                console.print("[bold cyan]Connecting...[/bold cyan]")
                await controller.connect()

            color_in = Prompt.ask("Breathing color (name, hex, rgb)", default="ocean")
            rgb, _ = parse_color_input(color_in)
            if not rgb:
                rgb = (0, 180, 255)

            cycle_in = Prompt.ask("Cycle time in seconds", default="4")
            try:
                cycle_time = max(1.0, min(30.0, float(cycle_in)))
            except ValueError:
                cycle_time = 4.0

            await run_breathing_mode(controller, color=rgb, cycle_time=cycle_time)
            Prompt.ask("\nPress Enter to return to menu...")

        # ------- Option 11: Music Reactive -------
        elif raw_choice == "11":
            if not controller.is_connected:
                console.print("[bold cyan]Connecting...[/bold cyan]")
                await controller.connect()
            await run_music_reactive(controller)
            Prompt.ask("\nPress Enter to return to menu...")

        # ------- Option 12: Favorites -------
        elif raw_choice == "12":
            if not controller.is_connected:
                await controller.connect()

            favs = load_favorites()
            if not favs:
                console.print("[dim]No saved favorites yet. Set a color (Option 2) and save it![/dim]")
                Prompt.ask("\nPress Enter to return to menu...")
                continue

            console.print()
            console.print(render_favorites_table(favs))
            console.print("[dim]Type a number to apply, 'delete N' to remove, or 'q' to go back.[/dim]")

            fav_in = Prompt.ask("Select favorite", default="1").strip().lower()
            if fav_in in ["q", "back"]:
                continue
            elif fav_in.startswith("delete") or fav_in.startswith("del") or fav_in.startswith("remove"):
                parts = fav_in.split()
                if len(parts) >= 2 and parts[-1].isdigit():
                    idx = int(parts[-1]) - 1
                    if 0 <= idx < len(favs):
                        removed = favs.pop(idx)
                        save_favorites(favs)
                        console.print(f"[bold yellow]Deleted favorite '{removed.get('name', 'Untitled')}'[/bold yellow]")
                    else:
                        console.print("[bold red]Invalid favorite number.[/bold red]")
                else:
                    console.print("[bold red]Usage: delete N (e.g., 'delete 2')[/bold red]")
            elif fav_in.isdigit():
                idx = int(fav_in) - 1
                if 0 <= idx < len(favs):
                    fav = favs[idx]
                    r, g, b = fav["r"], fav["g"], fav["b"]
                    await controller.set_color_rgb(r, g, b, immediate=True)
                    console.print(f"[bold green]Applied '{fav.get('name', 'Untitled')}': RGB({r}, {g}, {b})[/bold green]")
                    console.print(make_large_color_preview(r, g, b))
                else:
                    console.print("[bold red]Invalid favorite number.[/bold red]")
            else:
                # Try as a color input
                rgb, cmd = parse_color_input(fav_in)
                if rgb:
                    r, g, b = rgb
                    await controller.set_color_rgb(r, g, b, immediate=True)
                    console.print(f"[bold green]Set Color to RGB({r}, {g}, {b})[/bold green]")
                else:
                    console.print(f"[bold red]Unknown input: '{fav_in}'[/bold red]")
            await asyncio.sleep(1.4)

        # ------- Option 13: Firmware Hardware Dynamic Effects -------
        elif raw_choice == "13" or choice_lower in ["effects", "modes", "effect", "mode"]:
            if not controller.is_connected:
                console.print("[bold cyan]Connecting to LED strip...[/bold cyan]")
                await controller.connect()

            console.print()
            console.print(render_firmware_effects_table())
            console.print("[dim]Type a mode number (1-20), effect name, or 'q' to go back.[/dim]")

            eff_in = Prompt.ask("Select hardware effect mode", default="1").strip().lower()
            if eff_in in ["q", "back", "cancel"]:
                continue

            selected_eff = None
            if eff_in.isdigit():
                idx = int(eff_in)
                if 1 <= idx <= len(FIRMWARE_EFFECTS):
                    selected_eff = FIRMWARE_EFFECTS[idx - 1]
            else:
                for item in FIRMWARE_EFFECTS:
                    no, name, hex_id, desc = item
                    if eff_in in name.lower() or eff_in in desc.lower():
                        selected_eff = item
                        break

            if selected_eff:
                no, name, hex_id, desc = selected_eff
                speed_in = Prompt.ask("Animation speed (0-100%, 0=fastest, 100=slowest)", default="50").strip()
                speed_val = int(speed_in) if speed_in.isdigit() else 50
                speed_val = max(0, min(100, speed_val))

                await controller.set_power(True, immediate=True)
                await controller.set_effect(hex_id, immediate=True)
                await controller.set_effect_speed(speed_val, immediate=True)

                console.print(f"[bold green]✨ Activated Hardware Mode: {name} (Speed: {speed_val}%)[/bold green]")
                console.print(f"[dim]{desc}[/dim]")
            else:
                console.print(f"[bold red]Unknown effect mode: '{eff_in}'[/bold red]")
            await asyncio.sleep(1.8)

        # ------- Option 14: Procedural Motion Patterns -------
        elif raw_choice == "14" or choice_lower in ["motion", "pattern", "patterns", "wave", "waves"]:
            if not controller.is_connected:
                console.print("[bold cyan]Connecting to LED strip...[/bold cyan]")
                await controller.connect()

            console.print()
            console.print(render_motion_patterns_table())
            console.print("[dim]Type a pattern number (1-11), name ('aurora', 'fire', 'ocean', 'cyberpunk'), or 'q' to go back.[/dim]")

            pat_in = Prompt.ask("Select motion pattern", default="1").strip().lower()
            if pat_in in ["q", "back", "cancel"]:
                continue

            selected_pid = None
            if pat_in.isdigit():
                idx = int(pat_in)
                if 1 <= idx <= len(MotionPatternEngine.PATTERNS):
                    selected_pid = MotionPatternEngine.PATTERNS[idx - 1][0]
            else:
                for p_id, p_name, p_desc in MotionPatternEngine.PATTERNS:
                    if pat_in in p_id or pat_in in p_name.lower():
                        selected_pid = p_id
                        break

            if not selected_pid:
                selected_pid = "rainbow_wave"

            speed_in = Prompt.ask("Pattern Speed Multiplier (0.2 to 3.0, default 1.0)", default="1.0").strip()
            try:
                speed_val = float(speed_in)
            except ValueError:
                speed_val = 1.0

            bright_in = Prompt.ask("Pattern Brightness % (10-100, default 80)", default="80").strip()
            bright_val = int(bright_in.rstrip("%")) if bright_in.rstrip("%").isdigit() else 80

            await run_motion_pattern_cli(controller, pattern_id=selected_pid, speed=speed_val, brightness=bright_val)
            Prompt.ask("\nPress Enter to return to menu...")

        # ------- Direct color / preset entered in main menu -------
        else:
            rgb, cmd = parse_color_input(raw_choice)
            if cmd == "power_off":
                if not controller.is_connected:
                    await controller.connect()
                await controller.set_power(False, immediate=True)
                console.print("[bold red]⚡ Power turned OFF[/bold red]")
                await asyncio.sleep(1.2)
            elif cmd == "power_on":
                if not controller.is_connected:
                    await controller.connect()
                await controller.set_power(True, immediate=True)
                console.print("[bold green]⚡ Power turned ON[/bold green]")
                await asyncio.sleep(1.2)
            elif rgb:
                if not controller.is_connected:
                    await controller.connect()
                r, g, b = rgb
                await controller.set_color_rgb(r, g, b, immediate=True)
                console.print(f"[bold green]Set Color to RGB({r}, {g}, {b})  #{r:02x}{g:02x}{b:02x}[/bold green]")
                console.print(make_large_color_preview(r, g, b))
                await asyncio.sleep(1.4)
            else:
                console.print(f"[bold red]Unknown option: '{raw_choice}'. Type 'help' for reference.[/bold red]")
                await asyncio.sleep(1.0)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="MELK-OA10 Bluetooth LED Strip Controller & Ambient Screen Sync")
    parser.add_argument("--mac", type=str, default=DEFAULT_MAC, help="MAC address of the BLE LED strip")
    
    subparsers = parser.add_subparsers(dest="command", help="Direct CLI commands")
    
    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Start ambient screen color sync")
    sync_parser.add_argument("--zone", type=str, default="full", choices=["full", "center", "top", "bottom", "left", "right"], help="Screen capture zone")
    sync_parser.add_argument("--brightness", type=int, default=30, help="Ambient brightness percentage (default: 30)")

    # Color command
    color_parser = subparsers.add_parser("color", help="Set color (Hex, RGB, HSL, Name, or Preset #)")
    color_parser.add_argument("val", type=str, nargs="+", help="Hex (#ff0055), RGB (255 0 85), Name (cyan), or Preset # (1-12)")

    # Preset command
    preset_parser = subparsers.add_parser("preset", help="Apply color preset (number 1-12 or name)")
    preset_parser.add_argument("name", type=str, help="Preset number (1-12) or preset name ('cyan_glow', 'sunset')")

    # Power command
    power_parser = subparsers.add_parser("power", help="Turn strip ON or OFF")
    power_parser.add_argument("state", type=str, choices=["on", "off", "toggle"], help="Power state")

    # Shortcuts for ON / OFF
    subparsers.add_parser("on", help="Turn strip ON")
    subparsers.add_parser("off", help="Turn strip OFF")

    # Brightness command
    bright_parser = subparsers.add_parser("brightness", help="Set brightness level 0-100")
    bright_parser.add_argument("level", type=int, help="Brightness percentage 0-100")

    # Rainbow command
    rainbow_parser = subparsers.add_parser("rainbow", help="Start rainbow color cycle")
    rainbow_parser.add_argument("--speed", type=str, default="medium", choices=["slow", "medium", "fast"], help="Cycle speed")

    # Effect command (firmware hardware animations)
    effect_parser = subparsers.add_parser("effect", help="Activate built-in hardware dynamic animation (1-20)")
    effect_parser.add_argument("mode", type=str, help="Effect mode number (1-20) or name ('spectrum', 'chase', 'running')")
    effect_parser.add_argument("--speed", type=int, default=50, help="Animation speed 0-100 (0=fastest, 100=slowest)")

    # Pattern command (software motion animations)
    pattern_parser = subparsers.add_parser("pattern", help="Start procedural motion animation (aurora, fire, ocean, cyberpunk...)")
    pattern_parser.add_argument("name", type=str, default="rainbow_wave", nargs="?", help="Pattern name or number 1-11 ('aurora', 'fire', 'ocean', 'cyberpunk', 'police', 'sunset', 'heartbeat', 'lightning')")
    pattern_parser.add_argument("--speed", type=float, default=1.0, help="Speed multiplier 0.2 to 3.0 (default 1.0)")
    pattern_parser.add_argument("--brightness", type=int, default=80, help="Brightness 10-100 (default 80)")

    # Scan command
    subparsers.add_parser("scan", help="Scan nearby Bluetooth BLE devices")

    args = parser.parse_args()

    controller = LEDStripController(mac_address=args.mac)

    if args.command is None:
        # Interactive mode
        console.print("[cyan]Connecting to MELK-OA10 LED Strip...[/cyan]")
        connected = await controller.connect()
        if not connected:
            console.print(Panel(
                "[bold red]Could not connect to MELK-OA10 LED Strip![/bold red]\n\n"
                "[bold yellow]Troubleshooting Tips:[/bold yellow]\n"
                "1. Ensure your PC's [bold]Bluetooth is turned ON[/bold].\n"
                "2. Ensure the [bold]LED Strip is plugged in and powered ON[/bold].\n"
                "3. [bold]Disconnect any Smartphone App[/bold] (e.g., HappyLighting or Lotus Lantern) — BLE strips allow only 1 connection at a time!\n"
                "4. Move closer to the LED strip if signal is weak.",
                title="[bold red]Bluetooth Connection Tip[/bold red]",
                border_style="red"
            ))
            Prompt.ask("\nPress Enter to open menu anyway...")
        await interactive_menu(controller)
    else:
        # Direct CLI command mode
        if args.command in ["on", "off"]:
            connected = await controller.connect()
            if not connected:
                console.print("[bold red]Connection failed. Check Bluetooth and strip power.[/bold red]")
                sys.exit(1)
            await controller.set_power(args.command == "on", immediate=True)
            console.print(f"[bold {'green' if args.command == 'on' else 'red'}]Power set to {args.command.upper()}[/bold {'green' if args.command == 'on' else 'red'}]")
            await controller.disconnect()
            return

        connected = await controller.connect()
        if not connected and args.command != "scan":
            console.print(Panel(
                "[bold red]Could not connect to MELK-OA10 LED Strip![/bold red]\n\n"
                "[bold yellow]Please check:[/bold yellow]\n"
                "• PC Bluetooth is ON\n"
                "• LED strip is powered\n"
                "• Close any mobile app connected to the strip",
                border_style="red"
            ))
            sys.exit(1)

        if args.command == "sync":
            await run_ambient_sync_cli(controller, zone=args.zone, brightness=args.brightness)
        elif args.command == "color":
            joined_val = " ".join(args.val)
            rgb, cmd = parse_color_input(joined_val)
            if cmd == "power_off":
                await controller.set_power(False, immediate=True)
                console.print("[bold red]Power set to OFF[/bold red]")
            elif cmd == "power_on":
                await controller.set_power(True, immediate=True)
                console.print("[bold green]Power set to ON[/bold green]")
            elif rgb:
                r, g, b = rgb
                await controller.set_color_rgb(r, g, b, immediate=True)
                console.print(f"[bold green]Color set to RGB({r}, {g}, {b})[/bold green] ", make_color_block(r, g, b))
            else:
                console.print(f"[bold red]Cannot parse color from '{joined_val}'[/bold red]")
                sys.exit(1)
        elif args.command == "preset":
            rgb, cmd = parse_color_input(args.name)
            if rgb:
                r, g, b = rgb
                await controller.set_color_rgb(r, g, b, immediate=True)
                console.print(f"[bold green]Preset applied: RGB({r}, {g}, {b})[/bold green] ", make_color_block(r, g, b))
            else:
                console.print(f"[bold red]Cannot parse preset from '{args.name}'[/bold red]")
                sys.exit(1)
        elif args.command == "power":
            state = (args.state == "on")
            await controller.set_power(state, immediate=True)
            console.print(f"[bold green]Power set to {args.state.upper()}[/bold green]")
        elif args.command == "brightness":
            await controller.set_brightness(args.level, immediate=True)
            console.print(f"[bold green]Brightness set to {args.level}%[/bold green]")
        elif args.command == "rainbow":
            await run_color_cycle(controller, speed=args.speed)
        elif args.command == "effect":
            eff_arg = args.mode.lower().strip()
            selected_eff = None
            if eff_arg.isdigit():
                idx = int(eff_arg)
                if 1 <= idx <= len(FIRMWARE_EFFECTS):
                    selected_eff = FIRMWARE_EFFECTS[idx - 1]
            else:
                for item in FIRMWARE_EFFECTS:
                    no, name, hex_id, desc = item
                    if eff_arg in name.lower() or eff_arg in desc.lower():
                        selected_eff = item
                        break

            if selected_eff:
                no, name, hex_id, desc = selected_eff
                speed = max(0, min(100, args.speed))
                await controller.set_power(True, immediate=True)
                await controller.set_effect(hex_id, immediate=True)
                await controller.set_effect_speed(speed, immediate=True)
                console.print(f"[bold green]✨ Activated Hardware Effect: {name} (Speed: {speed}%)[/bold green]")
                console.print(f"[dim]{desc}[/dim]")
            else:
                console.print(f"[bold red]Unknown effect '{args.mode}'. Choose 1-{len(FIRMWARE_EFFECTS)}.[/bold red]")
                sys.exit(1)
        elif args.command == "pattern":
            pat_arg = args.name.lower().strip() if args.name else "rainbow_wave"
            selected_pid = "rainbow_wave"
            if pat_arg.isdigit():
                idx = int(pat_arg)
                if 1 <= idx <= len(MotionPatternEngine.PATTERNS):
                    selected_pid = MotionPatternEngine.PATTERNS[idx - 1][0]
            else:
                for p_id, p_name, p_desc in MotionPatternEngine.PATTERNS:
                    if pat_arg in p_id or pat_arg in p_name.lower():
                        selected_pid = p_id
                        break
            await run_motion_pattern_cli(controller, pattern_id=selected_pid, speed=args.speed, brightness=args.brightness)
        elif args.command == "scan":
            devs = await scan_all_ble_devices()
            dev_table = Table(title="Discovered Bluetooth Devices")
            dev_table.add_column("Name", style="white")
            dev_table.add_column("MAC / Address", style="yellow")
            dev_table.add_column("RSSI", style="cyan")
            for d in devs:
                dev_table.add_row(d["name"], d["address"], str(d["rssi"]))
            console.print(dev_table)

        await controller.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Program closed by user.[/yellow]")
