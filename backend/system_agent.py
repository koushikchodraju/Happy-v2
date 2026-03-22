"""
SystemAgent — Windows OS controller for HAPPY.
Uses a dynamic action registry (no hard-coded if/elif chains).
"""

import asyncio
import subprocess
import datetime
import os
from pathlib import Path


class SystemAgent:
    """
    Executes Windows system commands via subprocess + PowerShell.
    
    Design principles:
    - Dynamic action dispatch via ACTION_MAP (no hard-coded if/elif)
    - on_frontend_event callback for camera/hand-gesture voice control
    - All blocking calls are thread-safe via asyncio.to_thread
    - Returns actual OS output — no hardcoded success strings
    """

    def __init__(self, on_frontend_event=None):
        """
        :param on_frontend_event: Optional callback(payload: dict) invoked for
               frontend_control actions (camera_on/off, hand_gesture_on/off).
               The server passes a lambda that emits a Socket.IO event.
        """
        self.on_frontend_event = on_frontend_event

        # ── Dynamic intent → handler map ──────────────────────────────────
        self._INTENT_MAP = {
            "system_power":       self._handle_power,
            "system_control":     self._handle_control,
            "network_control":    self._handle_network,
            "application_control": self._handle_app,
            "system_query":       self._handle_query,
            "utility":            self._handle_utility,
            "frontend_control":   self._handle_frontend,
        }

    # ─────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────

    async def execute(self, intent: str, action: str, target: str = None, value=None) -> str:
        """
        Routes intent → handler using the dynamic intent map.
        Returns a result string that ADA speaks back to the user.
        """
        print(f"[SYSTEM] execute: intent={intent} action={action} target={target} value={value}")
        handler = self._INTENT_MAP.get(intent)
        if handler is None:
            return f"Unknown intent category: {intent}"
        try:
            return await handler(action, target=target, value=value)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error executing {action}: {str(e)}"

    # ─────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────

    async def _run_powershell(self, script: str) -> str:
        result = await asyncio.to_thread(
            subprocess.run,
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True
        )
        output = (result.stdout + result.stderr).strip()
        print(f"[SYSTEM] PS output: {output[:300]}")
        return output

    async def _run_cmd(self, args: list) -> str:
        result = await asyncio.to_thread(
            subprocess.run, args, capture_output=True, text=True
        )
        return (result.stdout + result.stderr).strip()

    def _ps_escape(self, text: str) -> str:
        return text.replace("`", "``").replace('"', '`"').replace("$", "`$")

    # ─────────────────────────────────────────────
    # FRONTEND CONTROL (camera, hand gesture)
    # ─────────────────────────────────────────────

    async def _handle_frontend(self, action: str, **_) -> str:
        """
        Triggers a frontend state change via the on_frontend_event callback.
        The server turns this into a Socket.IO emit to the React frontend.
        """
        VALID_ACTIONS = {"camera_on", "camera_off", "hand_gesture_on", "hand_gesture_off"}
        if action not in VALID_ACTIONS:
            return f"Unknown frontend control action: {action}"

        payload = {"type": "frontend_control", "action": action}
        if self.on_frontend_event:
            self.on_frontend_event(payload)
            print(f"[SYSTEM] Frontend event emitted: {payload}")
        else:
            print(f"[SYSTEM] WARNING: on_frontend_event callback not set — action={action} not dispatched")

        label_map = {
            "camera_on":         "Camera activated.",
            "camera_off":        "Camera deactivated.",
            "hand_gesture_on":   "Hand gesture mode enabled.",
            "hand_gesture_off":  "Hand gesture mode disabled.",
        }
        return label_map[action]

    # ─────────────────────────────────────────────
    # SYSTEM POWER
    # ─────────────────────────────────────────────

    async def _handle_power(self, action: str, **_) -> str:
        POWER_ACTIONS = {
            "lock":            lambda: (subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"]), "PC locked.")[1],
            "shutdown":        lambda: (subprocess.run(["shutdown", "/s", "/t", "10"]), "Shutting down in 10 seconds.")[1],
            "restart":         lambda: (subprocess.run(["shutdown", "/r", "/t", "10"]), "Restarting in 10 seconds.")[1],
            "cancel_shutdown": lambda: self._cancel_shutdown_sync(),
        }
        if action in ("sleep", "hibernate"):
            return await self._handle_sleep_hibernate(action)

        fn = POWER_ACTIONS.get(action)
        if fn:
            return await asyncio.to_thread(fn)
        return f"Unknown power action: {action}"

    def _cancel_shutdown_sync(self):
        result = subprocess.run(["shutdown", "/a"], capture_output=True, text=True)
        out = (result.stdout + result.stderr).strip()
        return "Shutdown cancelled." if result.returncode == 0 else f"No shutdown pending. ({out})"

    async def _handle_sleep_hibernate(self, action: str) -> str:
        if action == "sleep":
            await self._run_powershell(
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"
            )
            return "Going to sleep."
        result = await self._run_cmd(["shutdown", "/h"])
        if "not supported" in result.lower() or "error" in result.lower():
            return "Hibernate is not enabled. Enable it via Power Settings."
        return "Hibernating now."

    # ─────────────────────────────────────────────
    # SYSTEM CONTROL (volume, brightness)
    # ─────────────────────────────────────────────

    def _get_volume_control(self):
        from pycaw.pycaw import AudioUtilities
        return AudioUtilities.GetSpeakers().EndpointVolume

    async def _handle_control(self, action: str, value=None, **_) -> str:
        # Volume actions
        VOLUME_ACTIONS = {"set_volume", "mute", "unmute", "volume_up", "volume_down"}
        BRIGHTNESS_ACTIONS = {"set_brightness", "brightness_up", "brightness_down"}

        if action in VOLUME_ACTIONS:
            return await self._handle_volume(action, value)
        if action in BRIGHTNESS_ACTIONS:
            return await self._handle_brightness(action, value)
        return f"Unknown system_control action: {action}"

    async def _handle_volume(self, action: str, value=None) -> str:
        try:
            vol = await asyncio.to_thread(self._get_volume_control)
            if action == "set_volume":
                level = max(0, min(100, int(value or 50)))
                vol.SetMasterVolumeLevelScalar(level / 100.0, None)
                return f"Volume set to {round(vol.GetMasterVolumeLevelScalar() * 100)}%."
            elif action == "mute":
                vol.SetMute(1, None); return "Audio muted."
            elif action == "unmute":
                vol.SetMute(0, None); return "Audio unmuted."
            elif action == "volume_up":
                step = int(value or 10) / 100.0
                new = min(1.0, vol.GetMasterVolumeLevelScalar() + step)
                vol.SetMasterVolumeLevelScalar(new, None)
                return f"Volume increased to {round(new * 100)}%."
            elif action == "volume_down":
                step = int(value or 10) / 100.0
                new = max(0.0, vol.GetMasterVolumeLevelScalar() - step)
                vol.SetMasterVolumeLevelScalar(new, None)
                return f"Volume decreased to {round(new * 100)}%."
        except Exception as e:
            return f"Volume control failed: {e}"

    async def _handle_brightness(self, action: str, value=None) -> str:
        if action == "set_brightness":
            level = max(0, min(100, int(value or 70)))
            script = f"""
try {{
    $m = Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods -ErrorAction Stop
    if ($m) {{ $m | ForEach-Object {{ $_.WmiSetBrightness(1, {level}) }}; Write-Output "Brightness set to {level}%." }}
    else {{ Write-Output "UNSUPPORTED" }}
}} catch {{ Write-Output "UNSUPPORTED" }}"""
        else:
            step = int(value or 10)
            direction = "+" if action == "brightness_up" else "-"
            script = f"""
try {{
    $m = Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods -ErrorAction Stop
    $c = (Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness -ErrorAction Stop).CurrentBrightness
    $n = [math]::Max(0, [math]::Min(100, $c {direction} {step}))
    $m | ForEach-Object {{ $_.WmiSetBrightness(1, $n) }}
    Write-Output "Brightness set to $n%."
}} catch {{ Write-Output "UNSUPPORTED" }}"""
        result = await self._run_powershell(script)
        if "UNSUPPORTED" in result:
            return "Brightness control is not supported on external monitors. Adjust brightness using your monitor's buttons."
        return result

    # ─────────────────────────────────────────────
    # NETWORK CONTROL (Wi-Fi, Bluetooth)
    # ─────────────────────────────────────────────

    async def _handle_network(self, action: str, value=None, **_) -> str:
        if action in ("wifi_on", "wifi_off"):
            state = "enable" if action == "wifi_on" else "disable"
            script = f"""
$a = Get-NetAdapter | Where-Object {{$_.PhysicalMediaType -eq 'Native 802.11' -or $_.InterfaceDescription -like '*Wireless*' -or $_.Name -like '*Wi-Fi*'}} | Select-Object -First 1
if ($a) {{
    try {{ {state.capitalize()}-NetAdapter -Name $a.Name -Confirm:$false -ErrorAction Stop; Write-Output "Wi-Fi ($($a.Name)) {state}d." }}
    catch {{ Write-Output "ERROR: $($_.Exception.Message)" }}
}} else {{ Write-Output "No Wi-Fi adapter found." }}"""
            result = await self._run_powershell(script)
            if result.startswith("ERROR:") or "denied" in result.lower():
                return "Wi-Fi control requires administrator privileges."
            return result

        elif action in ("bluetooth_on", "bluetooth_off"):
            state = "On" if action == "bluetooth_on" else "Off"
            script = f"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
function Await($WinRtTask, $ResultType) {{
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}}
[Windows.Devices.Radios.Radio,Windows.Devices.Radios,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.Devices.Radios,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioState,Windows.Devices.Radios,ContentType=WindowsRuntime] | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$bt = $radios | Where-Object {{ $_.Kind -eq [Windows.Devices.Radios.RadioKind]::Bluetooth }}
if ($bt) {{
    $status = Await ($bt.SetStateAsync([Windows.Devices.Radios.RadioState]::{state})) ([Windows.Devices.Radios.RadioAccessStatus])
    if ($status -eq 'Success') {{ Write-Output "Bluetooth turned {state.lower()}." }}
    else {{ Write-Output "Bluetooth toggle returned: $status." }}
}} else {{ Write-Output "No Bluetooth radio detected." }}"""
            result = await self._run_powershell(script)
            if "DeniedBySystem" in result or "denied" in result.lower():
                return "Bluetooth control was denied. Allow radio access in Settings → Privacy → Radios."
            return result

        return f"Unknown network action: {action}"

    # ── App aliases for common abbreviations (NOT launch paths) ──────────
    # Maps what the user says → what to search for in the Start Menu.
    # Add entries here ONLY for abbreviations, not to hardcode exe paths.
    APP_ALIASES = {
        "chrome":           "Google Chrome",
        "google chrome":    "Google Chrome",
        "edge":             "Microsoft Edge",
        "microsoft edge":   "Microsoft Edge",
        "vscode":           "Visual Studio Code",
        "vs code":          "Visual Studio Code",
        "visual studio code": "Visual Studio Code",
        "word":             "Microsoft Word",
        "excel":            "Microsoft Excel",
        "powerpoint":       "Microsoft PowerPoint",
        "file explorer":    "File Explorer",
        "files":            "File Explorer",
        "cmd":              "Command Prompt",
        "command prompt":   "Command Prompt",
        "task manager":     "Task Manager",
        "snip":             "Snipping Tool",
        "snipping tool":    "Snipping Tool",
        "paint":            "Paint",
        "calc":             "Calculator",
        "calculator":       "Calculator",
        "notepad":          "Notepad",
        "settings":         "Settings",
        "photos":           "Photos",
    }

    # Protocol/URI launchers — these open via the OS protocol handler directly.
    APP_PROTOCOLS = {
        "whatsapp":         "whatsapp:",
        "spotify":          "spotify:",
        "ms-settings":      "ms-settings:",
        "windows settings": "ms-settings:",
    }

    # Process name hints for close_app — maps display name → process exe name.
    # Only needed when the process name differs wildly from the display name.
    PROC_HINTS = {
        "google chrome":    "chrome",
        "chrome":           "chrome",
        "microsoft edge":   "msedge",
        "edge":             "msedge",
        "visual studio code": "code",
        "vscode":           "code",
        "vs code":          "code",
        "file explorer":    "explorer",
        "files":            "explorer",
        "microsoft word":   "winword",
        "word":             "winword",
        "microsoft excel":  "excel",
        "microsoft powerpoint": "powerpnt",
        "powerpoint":       "powerpnt",
        "task manager":     "taskmgr",
        "command prompt":   "cmd",
        "snipping tool":    "snippingtool",
    }

    async def _find_and_launch(self, search_name: str) -> tuple[bool, str]:
        """
        Stage 2: Query Windows Start Menu index (Get-StartApps) for any installed
        app matching search_name, then launch it. Works for UWP, desktop, and
        packaged apps — no hardcoded paths needed.
        Returns (success, message).
        """
        safe = self._ps_escape(search_name)
        script = f"""
$apps = Get-StartApps | Where-Object {{ $_.Name -like '*{safe}*' }} | Select-Object -First 1
if ($apps) {{
    Start-Process $apps.AppID -ErrorAction SilentlyContinue
    Write-Output "FOUND:$($apps.Name)"
}} else {{
    Write-Output "NOTFOUND"
}}"""
        result = await self._run_powershell(script)
        if result.startswith("FOUND:"):
            found_name = result[6:].strip()
            return True, f"Opening {found_name}."
        return False, ""

    async def _handle_app(self, action: str, target: str = None, **_) -> str:
        if not target:
            return f"Please specify which app to {action.replace('_', ' ')}."

        name_raw = target.strip()
        name_lower = name_raw.lower()

        # ── OPEN APP ──────────────────────────────────────────────────────
        if action == "open_app":
            # Stage 1a: Protocol / URI handler (whatsapp:, spotify:, ms-settings:, http...)
            protocol = self.APP_PROTOCOLS.get(name_lower)
            if not protocol and (name_raw.startswith("http") or name_raw.endswith(":")):
                protocol = name_raw

            if protocol:
                try:
                    subprocess.Popen(f'start "" "{protocol}"', shell=True)
                    return f"Opening {name_raw}."
                except Exception as e:
                    return f"Couldn't open {name_raw}: {e}"

            # Stage 1b: Known Windows built-ins that respond to direct exe names on PATH
            DIRECT_CMDS = {
                "notepad": "notepad", "paint": "mspaint", "calculator": "calc",
                "task manager": "taskmgr", "powershell": "powershell",
                "cmd": "cmd", "command prompt": "cmd",
                "snipping tool": "snippingtool", "snip": "snippingtool",
                "file explorer": "explorer", "files": "explorer", "explorer": "explorer",
                "wordpad": "wordpad", "regedit": "regedit",
            }
            direct_cmd = DIRECT_CMDS.get(name_lower)
            if direct_cmd:
                try:
                    subprocess.Popen(direct_cmd, shell=True)
                    return f"Opening {name_raw}."
                except Exception as e:
                    return f"Couldn't open {name_raw}: {e}"

            # Stage 2: Windows Start Menu index search (catches all installed apps)
            search_term = self.APP_ALIASES.get(name_lower, name_raw)
            ok, msg = await self._find_and_launch(search_term)
            if ok:
                return msg

            # Stage 2b: Try the raw name in start menu (user may have said the exact name)
            if search_term != name_raw:
                ok, msg = await self._find_and_launch(name_raw)
                if ok:
                    return msg

            # Stage 3: Last resort — let Windows shell resolve it (PATH, association)
            try:
                subprocess.Popen(f'start "" "{self._ps_escape(name_raw)}"', shell=True)
                return f"Attempting to open {name_raw}."
            except Exception as e:
                return f"Couldn't open {name_raw}. Make sure it's installed. ({e})"

        # ── CLOSE APP ──────────────────────────────────────────────────────
        elif action == "close_app":
            # Resolve process name: use hint if available, else derive from name
            proc_hint = self.PROC_HINTS.get(name_lower)
            if not proc_hint:
                # Derive: take first word, strip spaces — covers common cases
                proc_hint = name_lower.split()[0].replace(" ", "")

            safe_target = self._ps_escape(name_raw)
            safe_proc   = self._ps_escape(proc_hint)

            # Smart close: try exact process name first, then title-based, then pattern
            script = f"""
$closed = $false

# 1. Try exact process name match (fastest)
$p = Get-Process -Name '{safe_proc}' -ErrorAction SilentlyContinue
if ($p) {{
    $p | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Output "Closed {safe_target}."
    $closed = $true
}}

if (-not $closed) {{
    # 2. Try window-title match (catches apps with different exe names)
    $p2 = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{safe_target}*' }} -ErrorAction SilentlyContinue
    if ($p2) {{
        $p2 | Stop-Process -Force -ErrorAction SilentlyContinue
        Write-Output "Closed {safe_target}."
        $closed = $true
    }}
}}

if (-not $closed) {{
    # 3. Broad process name pattern match
    $p3 = Get-Process | Where-Object {{ $_.Name -like '*{safe_proc}*' }} -ErrorAction SilentlyContinue
    if ($p3) {{
        $p3 | Stop-Process -Force -ErrorAction SilentlyContinue
        Write-Output "Closed {safe_target}."
        $closed = $true
    }}
}}

if (-not $closed) {{
    Write-Output "{safe_target} does not appear to be running."
}}"""
            return await self._run_powershell(script)

        elif action == "minimize_all":
            await self._run_powershell(
                "(New-Object -ComObject Shell.Application).MinimizeAll(); Write-Output 'Done.'"
            )
            return "All windows minimized."

        elif action == "show_desktop":
            await self._run_powershell(
                "(New-Object -ComObject Shell.Application).ToggleDesktop(); Write-Output 'Done.'"
            )
            return "Showing desktop."

        elif action == "switch_window":
            await self._run_powershell(
                "(New-Object -ComObject WScript.Shell).SendKeys('%{TAB}')"
            )
            return "Switched window."

        return f"Unknown app action: {action}"


    # ─────────────────────────────────────────────
    # SYSTEM QUERIES
    # ─────────────────────────────────────────────

    async def _handle_query(self, action: str, **_) -> str:
        QUERY_SCRIPTS = {
            "get_time": None,  # Handled inline below (no PS needed)
            "get_battery": """
$b = Get-WmiObject Win32_Battery -ErrorAction SilentlyContinue
if ($b) { $c = if ($b.BatteryStatus -eq 2) {"charging"} else {"not charging"}; Write-Output "Battery at $($b.EstimatedChargeRemaining)%, $c." }
else { Write-Output "No battery detected — running on AC power." }""",
            "get_cpu_usage": """
$cpu = (Get-WmiObject Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
Write-Output "CPU usage is at $([math]::Round($cpu))%." """,
            "get_ram_usage": """
$os = Get-WmiObject Win32_OperatingSystem
$t = [math]::Round($os.TotalVisibleMemorySize / 1048576, 1)
$f = [math]::Round($os.FreePhysicalMemory / 1048576, 1)
$u = [math]::Round($t - $f, 1)
Write-Output "RAM: $u GB used of $t GB — $([math]::Round(($u/$t)*100))% usage." """,
            "get_storage": """
$d = Get-WmiObject Win32_LogicalDisk -Filter "DriveType=3 AND DeviceID='C:'"
if ($d) { Write-Output "C: drive: $([math]::Round(($d.Size-$d.FreeSpace)/1GB,1)) GB used of $([math]::Round($d.Size/1GB,1)) GB." }
else { Write-Output "Could not read disk info." }""",
            "get_ip": """
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*' -and $_.IPAddress -notlike '169.*'} | Select-Object -First 1).IPAddress
if ($ip) { Write-Output "Your local IP is $ip." } else { Write-Output "Could not determine local IP." }""",
            "get_wifi_status": """
$w = Get-NetAdapter | Where-Object {$_.PhysicalMediaType -eq 'Native 802.11' -or $_.Name -like '*Wi-Fi*'}
if ($w) { Write-Output "Wi-Fi ($($w.Name)) is $($w.Status)." } else { Write-Output "No Wi-Fi adapter found." }""",
        }

        if action == "get_time":
            now = datetime.datetime.now()
            return f"It's {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')}."

        script = QUERY_SCRIPTS.get(action)
        if script:
            return await self._run_powershell(script)
        return f"Unknown query: {action}"

    # ─────────────────────────────────────────────
    # UTILITY
    # ─────────────────────────────────────────────

    async def _handle_utility(self, action: str, target: str = None, value=None, **_) -> str:
        if action == "screenshot":
            try:
                import mss, datetime as dt
                ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                save_dir = Path.home() / "Pictures"
                save_dir.mkdir(exist_ok=True)
                path = str(save_dir / f"screenshot_{ts}.png")
                with mss.mss() as sct:
                    sct.shot(output=path)
                return f"Screenshot saved to Pictures/screenshot_{ts}.png."
            except Exception as e:
                return f"Screenshot failed: {e}"

        elif action == "open_folder":
            path = target or str(Path.home())
            if not os.path.exists(path):
                return f"Folder not found: {path}"
            subprocess.Popen(["explorer", path])
            return f"Opened folder: {path}."

        elif action == "open_file":
            path = target or value or ""
            if not path:
                return "Please specify the file path to open."
            if not os.path.exists(path):
                return f"File not found: {path}"
            os.startfile(path)  # Opens with default app (Windows)
            return f"Opened file: {os.path.basename(path)}."

        elif action == "reveal_file":
            # Opens the containing folder and selects the file in Explorer
            path = target or value or ""
            if not os.path.exists(path):
                return f"File not found: {path}"
            subprocess.Popen(f'explorer /select,"{path}"', shell=True)
            return f"Revealed {os.path.basename(path)} in File Explorer."

        elif action == "search":
            query = str(target or value or "").strip()
            if not query:
                return "Please tell me what to search for."
            import urllib.parse
            subprocess.Popen(
                f'start "" "https://www.google.com/search?q={urllib.parse.quote(query)}"', shell=True
            )
            return f"Searching Google for: {query}."

        elif action == "clipboard_set":
            text = str(value or target or "")
            script = f'Set-Clipboard -Value "{self._ps_escape(text)}"; Write-Output "Copied to clipboard."'
            return await self._run_powershell(script)

        elif action == "clipboard_get":
            result = await self._run_powershell("Get-Clipboard")
            return f"Clipboard: {result}" if result else "Clipboard is empty."

        elif action == "empty_recycle_bin":
            return await self._run_powershell(
                "Clear-RecycleBin -Force -ErrorAction SilentlyContinue; Write-Output 'Recycle bin emptied.'"
            )

        return f"Unknown utility action: {action}"
