"""
WhatsAppAgent — Sends WhatsApp messages via the WhatsApp Desktop app
using Windows UI automation (pyautogui + pygetwindow + pyperclip).

No Selenium. No web scraping. Direct app automation only.
"""

import subprocess
import threading
import time
import pyautogui
import pyperclip
import pygetwindow as gw


class WhatsAppAgent:
    """
    Automates WhatsApp Desktop on Windows to send messages by contact name.
    All operations run in a background thread to avoid blocking the main pipeline.
    """

    WHATSAPP_URI = "whatsapp:"
    WINDOW_TITLE_KEYWORDS = ["WhatsApp"]
    LAUNCH_WAIT  = 4.0   # Seconds to wait after launching WhatsApp
    FOCUS_WAIT   = 1.5
    SEARCH_WAIT  = 2.0   # Seconds for search results to appear
    MESSAGE_WAIT = 0.5

    def send_message(self, contact_name: str, message: str) -> str:
        """
        Non-blocking: spawns a thread and returns immediately with a confirmation.
        The actual send runs in the background.
        """
        threading.Thread(
            target=self._send_blocking,
            args=(contact_name, message),
            daemon=True
        ).start()
        return f"Sending WhatsApp message to {contact_name}."

    def _send_blocking(self, contact_name: str, message: str):
        """
        Blocking implementation that runs on a background thread.
        Steps:
          1. Launch WhatsApp if not already open
          2. Bring window to foreground
          3. Open search with Ctrl+F (keyboard-layout safe — avoids Ctrl+Alt+N
             which injects Unicode chars like ṇ on non-US layouts)
          4. Clear the search box, paste contact name, press Enter
          5. Paste message and press Enter to send
        """
        try:
            print(f"[WhatsApp] Starting send to '{contact_name}'")

            # Step 1 — Ensure WhatsApp is running
            window = self._get_whatsapp_window()
            if window is None:
                print("[WhatsApp] WhatsApp not open. Launching...")
                subprocess.Popen(f'start "" "{self.WHATSAPP_URI}"', shell=True)
                for _ in range(int(self.LAUNCH_WAIT / 0.5)):
                    time.sleep(0.5)
                    window = self._get_whatsapp_window()
                    if window:
                        break

            if window is None:
                print("[WhatsApp] ERROR: WhatsApp window not found after launch.")
                return

            # Step 2 — Bring to foreground
            self._focus_window(window)
            time.sleep(self.FOCUS_WAIT)

            # Step 3 — Open search bar with Ctrl+F
            # NOTE: Ctrl+Alt+N was removed — it produces Unicode ṇ on Indian/
            # non-US keyboard layouts, which leaked into the message text.
            # Ctrl+F is the safe, universal WhatsApp Desktop search shortcut.
            pyautogui.hotkey("ctrl", "f")
            time.sleep(self.SEARCH_WAIT)

            # Step 4 — Clear any residual text in the search box, then paste contact
            # Ctrl+A selects all, then we overwrite with our paste.
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)

            pyperclip.copy(contact_name)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(self.SEARCH_WAIT)

            # Press Enter to open the first search result (the contact)
            pyautogui.press("enter")
            time.sleep(self.MESSAGE_WAIT)

            # Step 5 — Paste message and send
            # Using clipboard paste avoids any keyboard-layout character mapping issues.
            pyperclip.copy(message)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(self.MESSAGE_WAIT)
            pyautogui.press("enter")

            print(f"[WhatsApp] Message sent to '{contact_name}'.")

        except Exception as e:
            print(f"[WhatsApp] ERROR: {e}")
            import traceback
            traceback.print_exc()

    def _get_whatsapp_window(self):
        """Returns the first WhatsApp window found, or None."""
        for title in self.WINDOW_TITLE_KEYWORDS:
            windows = gw.getWindowsWithTitle(title)
            if windows:
                return windows[0]
        return None

    def _focus_window(self, window):
        """Brings the given window to the foreground."""
        try:
            if window.isMinimized:
                window.restore()
            window.activate()
        except Exception as e:
            print(f"[WhatsApp] Window focus error: {e}")
