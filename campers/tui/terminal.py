"""Terminal background color detection."""

import logging
import platform
import re
import select
import sys
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None


@dataclass
class TerminalBackground:
    """Terminal background color information.

    Attributes
    ----------
    color_hex : str
        Background color in hex format (e.g., "#1e1e1e")
    is_light : bool
        Whether the background is light (True) or dark (False)
    """

    color_hex: str
    is_light: bool


def detect_terminal_background() -> TerminalBackground:
    """Detect terminal background color using OSC 11 query.

    Returns
    -------
    TerminalBackground
        Terminal background color and lightness information
        Example: TerminalBackground("#1e1e1e", False) for dark or
                 TerminalBackground("#ffffff", True) for light
    """
    if platform.system() == "Windows" or termios is None or tty is None:
        return TerminalBackground(color_hex="#000000", is_light=False)

    if not sys.stdin.isatty():
        return TerminalBackground(color_hex="#000000", is_light=False)

    try:
        sys.stdout.write("\033]11;?\033\\")
        sys.stdout.flush()

        old_settings = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())

        try:
            response = ""
            start_time = time.time()

            while time.time() - start_time < 0.1:
                if select.select([sys.stdin], [], [], 0)[0]:
                    try:
                        char = sys.stdin.read(1)
                        if not char:
                            break
                        response += char
                        if response.endswith("\033\\") or response.endswith("\007"):
                            break
                    except OSError:
                        break

            if match := re.search(
                r"rgb:([0-9a-fA-F]{4})/([0-9a-fA-F]{4})/([0-9a-fA-F]{4})", response
            ):
                r = int(match.group(1), 16) / 65535
                g = int(match.group(2), 16) / 65535
                b = int(match.group(3), 16) / 65535

                luminance = 0.299 * r + 0.587 * g + 0.114 * b
                is_light = luminance > 0.5

                r_hex = int(r * 255)
                g_hex = int(g * 255)
                b_hex = int(b * 255)
                bg_color = f"#{r_hex:02x}{g_hex:02x}{b_hex:02x}"

                return TerminalBackground(color_hex=bg_color, is_light=is_light)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    except Exception as e:
        logger.debug("Terminal background detection failed: %s", e)

    return TerminalBackground(color_hex="#000000", is_light=False)
