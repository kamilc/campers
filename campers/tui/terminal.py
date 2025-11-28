"""Terminal background color detection."""

import logging
import platform
import re
import select
import sys
import time

logger = logging.getLogger(__name__)

try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None


def detect_terminal_background() -> tuple[str, bool]:
    """Detect terminal background color using OSC 11 query.

    Returns
    -------
    tuple[str, bool]
        (background_color_hex, is_light)
        Example: ("#1e1e1e", False) for dark or ("#ffffff", True) for light
    """
    if platform.system() == "Windows" or termios is None or tty is None:
        return ("#000000", False)

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
                    char = sys.stdin.read(1)
                    response += char
                    if response.endswith("\033\\") or response.endswith("\007"):
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

                return (bg_color, is_light)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    except Exception as e:
        logger.debug("Terminal background detection failed: %s", e)

    return ("#000000", False)
