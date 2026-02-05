import webview
import threading
import time
import os
import ctypes
from ctypes import wintypes
import sys
import logging
import json
import html
from urllib.parse import urlparse
from typing import Optional, Dict, List, Any

# ============================================================
# Logging Setup - Konfigurierbar über Umgebungsvariable
# ============================================================
LOG_LEVEL = os.environ.get('AI_SLIDEBAR_LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ai_slidebar.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# DPI-Awareness
# ============================================================
def set_dpi_awareness():
    """Setzt DPI-Awareness für hochauflösende Displays"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        logger.info("DPI-Awareness gesetzt (Shcore)")
    except AttributeError:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            logger.info("DPI-Awareness gesetzt (User32)")
        except Exception as e:
            logger.warning(f"DPI-Awareness konnte nicht gesetzt werden: {e}")
    except Exception as e:
        logger.warning(f"Unerwarteter Fehler bei DPI-Awareness: {e}")

set_dpi_awareness()
user32 = ctypes.windll.user32

# Win32 Konstanten
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_FRAMECHANGED = 0x0020
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATE = 0x0010

# ============================================================
# Verfügbare LLM-Dienste
# ============================================================
AVAILABLE_LLMS: Dict[str, Dict[str, str]] = {
    'chatgpt': {'name': 'ChatGPT', 'url': 'https://chatgpt.com', 'domain': 'chatgpt.com'},
    'claude': {'name': 'Claude', 'url': 'https://claude.ai', 'domain': 'claude.ai'},
    'gemini': {'name': 'Gemini', 'url': 'https://gemini.google.com', 'domain': 'gemini.google.com'},
    'perplexity': {'name': 'Perplexity', 'url': 'https://www.perplexity.ai', 'domain': 'perplexity.ai'},
    'grok': {'name': 'Grok', 'url': 'https://x.com/i/grok', 'domain': 'x.com'},
    'pi': {'name': 'Pi', 'url': 'https://pi.ai', 'domain': 'pi.ai'},
    'huggingface': {'name': 'HuggingChat', 'url': 'https://huggingface.co/chat', 'domain': 'huggingface.co'},
    'mistral': {'name': 'Mistral', 'url': 'https://chat.mistral.ai', 'domain': 'mistral.ai'},
    'poe': {'name': 'Poe', 'url': 'https://poe.com', 'domain': 'poe.com'},
    'copilot': {'name': 'Copilot', 'url': 'https://copilot.microsoft.com', 'domain': 'copilot.microsoft.com'},
    'claude-code': {'name': 'Claude Code', 'url': 'https://claude.ai/code', 'domain': 'claude.ai'},
    'you': {'name': 'You.com', 'url': 'https://you.com', 'domain': 'you.com'},
}

VALID_LLM_KEYS = frozenset(AVAILABLE_LLMS.keys())


class SettingsValidator:
    """Validiert und sanitiert Einstellungen"""
    
    @staticmethod
    def validate_monitor_index(index: Any, max_monitors: int) -> int:
        try:
            idx = int(index)
            if 0 <= idx < max_monitors:
                return idx
        except (TypeError, ValueError):
            pass
        return 0
    
    @staticmethod
    def validate_font_size(size: Any) -> int:
        try:
            s = int(size)
            return max(50, min(200, s))
        except (TypeError, ValueError):
            return 100
    
    @staticmethod
    def validate_llm_list(llms: Any) -> List[str]:
        default = ['chatgpt', 'claude', 'gemini']
        if not isinstance(llms, list):
            return default
        validated = []
        for llm in llms[:3]:
            if isinstance(llm, str) and llm in VALID_LLM_KEYS:
                validated.append(llm)
        while len(validated) < 3:
            for default_llm in default:
                if default_llm not in validated:
                    validated.append(default_llm)
                    break
        return validated[:3]
    
    @staticmethod
    def sanitize_string(s: Any, max_length: int = 1000) -> str:
        if not isinstance(s, str):
            return ""
        return s[:max_length]
    
    @staticmethod
    def validate_prompt(prompt: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(prompt, dict):
            return None
        name = prompt.get('name', '')
        content = prompt.get('content', '')
        fast_access = prompt.get('fast_access', True)
        if not isinstance(name, str) or not isinstance(content, str):
            return None
        if not name.strip() or not content.strip():
            return None
        return {
            'name': name[:150].strip(),
            'content': content[:2000].strip(),
            'fast_access': bool(fast_access)
        }


class MonitorEnumerator:
    """Klasse zum Ermitteln aller angeschlossenen Monitore"""
    
    def __init__(self):
        self.monitors: List[Dict[str, int]] = []
    
    def callback(self, hMonitor, hdcMonitor, lprcMonitor, dwData):
        rect = lprcMonitor.contents
        monitor_info = {
            'left': rect.left,
            'top': rect.top,
            'right': rect.right,
            'bottom': rect.bottom,
            'width': rect.right - rect.left,
            'height': rect.bottom - rect.top
        }
        self.monitors.append(monitor_info)
        return 1
    
    def get_monitors(self) -> List[Dict[str, int]]:
        self.monitors = []
        MONITOR_ENUM_PROC = ctypes.WINFUNCTYPE(
            ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
            ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
        )
        callback = MONITOR_ENUM_PROC(self.callback)
        user32.EnumDisplayMonitors(None, None, callback, 0)
        self.monitors.sort(key=lambda m: m['left'])
        logger.info(f"Gefundene Monitore: {len(self.monitors)}")
        for i, mon in enumerate(self.monitors):
            logger.info(f"  Monitor {i+1}: {mon['width']}x{mon['height']} @ ({mon['left']}, {mon['top']})")
        return self.monitors


class AISidebarSystem:
    """Hauptklasse für das AI Slidebar System"""
    
    SETTINGS_FILE = 'ai_slidebar_settings.json'
    PROMPTS_FILE = 'ai_prompts.json'
    NAV_HEIGHT = 150
    SIDEBAR_WIDTH_RATIO = 0.30
    ENFORCER_INTERVAL_ACTIVE = 0.016
    ENFORCER_INTERVAL_IDLE = 0.1
    
    def __init__(self):
        self._lock = threading.RLock()
        self._settings_save_timer: Optional[threading.Timer] = None
        self._pending_timers: List[threading.Timer] = []
        
        self.monitor_enum = MonitorEnumerator()
        self.monitors = self.monitor_enum.get_monitors()
        
        self.settings = self._load_settings()
        self.selected_monitor = SettingsValidator.validate_monitor_index(
            self.settings.get('selected_monitor', 0), len(self.monitors) or 1
        )
        self.selected_llms = SettingsValidator.validate_llm_list(self.settings.get('selected_llms'))
        self.current_font_size = SettingsValidator.validate_font_size(self.settings.get('font_size', 100))
        
        self.remain_in_chat = self.settings.get('remain_in_chat', 0)
        if self.remain_in_chat not in [0, 10, 30]:
            self.remain_in_chat = 0
        
        self.sidebar_side = self.settings.get('sidebar_side', 'right')
        if self.sidebar_side not in ['left', 'right']:
            self.sidebar_side = 'right'
        
        self._llm_last_urls: Dict[str, Dict[str, Any]] = {}
        self.prompts = self._load_prompts()
        self.current_active_llm = 0
        self.is_visible = False
        self._last_visible_state: Optional[bool] = None
        
        self._update_monitor_settings()
        
        self.title_nav = "AI_NAV_BAR_99"
        self.title_browser = "AI_BROWSER_BODY_99"
        self.hwnd_nav: Optional[int] = None
        self.hwnd_browser: Optional[int] = None
        self._locked_hwnds: set = set()
        self._target_positions: Dict[int, Dict[str, int]] = {}
        
        self.is_running = True
        self._windows_created = False
        self._needs_nav_reload = False
        self._nav_expanded = False
        self._is_pinned = False
        
        self.nav_window = None
        self.browser_window = None
        
        # Download folder - use user's Downloads directory
        self.download_folder = os.path.join(os.path.expanduser('~'), 'Downloads')
        if not os.path.exists(self.download_folder):
            try:
                os.makedirs(self.download_folder)
            except Exception as e:
                logger.warning(f"Konnte Download-Ordner nicht erstellen: {e}")
                self.download_folder = os.getcwd()

        logger.info(f"AI Slidebar initialisiert - Monitor {self.selected_monitor + 1}")
        logger.info(f"Ausgewählte LLMs: {self.selected_llms}")
        logger.info(f"Remain in chat: {self.remain_in_chat} Minuten")
        logger.info(f"Sidebar-Seite: {self.sidebar_side}")

    def _load_settings(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    if isinstance(settings, dict):
                        logger.info("Einstellungen geladen")
                        return settings
        except json.JSONDecodeError as e:
            logger.warning(f"Ungültige JSON in Einstellungen: {e}")
        except Exception as e:
            logger.warning(f"Fehler beim Laden der Einstellungen: {e}")
        return {}

    def _save_settings_debounced(self):
        with self._lock:
            if self._settings_save_timer:
                self._settings_save_timer.cancel()
            
            def do_save():
                with self._lock:
                    self._settings_save_timer = None
                    try:
                        settings = {
                            'selected_monitor': self.selected_monitor,
                            'font_size': self.current_font_size,
                            'selected_llms': self.selected_llms,
                            'remain_in_chat': self.remain_in_chat,
                            'sidebar_side': self.sidebar_side
                        }
                        with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                            json.dump(settings, f, indent=2)
                        logger.debug("Einstellungen gespeichert")
                    except Exception as e:
                        logger.error(f"Fehler beim Speichern der Einstellungen: {e}")
            
            self._settings_save_timer = threading.Timer(1.0, do_save)
            self._settings_save_timer.daemon = True
            self._settings_save_timer.start()
            self._pending_timers.append(self._settings_save_timer)

    def _load_prompts(self) -> List[Dict[str, str]]:
        try:
            if os.path.exists(self.PROMPTS_FILE):
                with open(self.PROMPTS_FILE, 'r', encoding='utf-8') as f:
                    prompts = json.load(f)
                    if isinstance(prompts, list):
                        validated = []
                        for p in prompts:
                            valid = SettingsValidator.validate_prompt(p)
                            if valid:
                                validated.append(valid)
                        logger.info(f"Prompts geladen: {len(validated)} Einträge")
                        return validated
        except Exception as e:
            logger.warning(f"Fehler beim Laden der Prompts: {e}")

        default_prompts = [
            {"name": "General Task", "content": "Act as an expert in [domain]. Perform the following task: [task]. Respond for a [beginner/intermediate/expert] audience in a clear, structured format with short sections and bullet points where helpful.", "fast_access": True},
            {"name": "Step-by-Step", "content": "Solve this problem step by step. First restate the problem, then outline a brief plan, then execute the plan, and finally give a 1–2 sentence final answer under the heading 'Answer'.", "fast_access": True},
            {"name": "Specific Format", "content": "Your task is to [task]. Always respond in this exact format: [describe format, e.g. markdown table with columns X, Y, Z]. Do not add extra sections or text outside this format.", "fast_access": True},
            {"name": "Teach/Explain", "content": "Explain [concept] to a [level, e.g. 12-year-old / non-technical manager]. Use simple language, short sentences, and one concrete example. End with three key bullet-point takeaways.", "fast_access": True},
            {"name": "Review & Improve", "content": "Here is my draft prompt: [PASTE PROMPT] Rewrite it to be clearer and more precise. Clarify the task, specify the desired format, and remove ambiguity, then show only the improved prompt.", "fast_access": True},
        ]
        self._save_prompts(default_prompts)
        return default_prompts

    def _save_prompts(self, prompts: List[Dict[str, str]]) -> bool:
        try:
            with open(self.PROMPTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(prompts, f, ensure_ascii=False, indent=2)
            logger.debug(f"Prompts gespeichert: {len(prompts)} Einträge")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Prompts: {e}")
            return False

    def _update_monitor_settings(self):
        if not self.monitors:
            self.monitor_left = 0
            self.monitor_top = 0
            self.monitor_right = user32.GetSystemMetrics(0)
            self.monitor_width = user32.GetSystemMetrics(0)
            self.monitor_height = user32.GetSystemMetrics(1)
        else:
            monitor = self.monitors[self.selected_monitor]
            self.monitor_left = monitor['left']
            self.monitor_top = monitor['top']
            self.monitor_right = monitor['right']
            self.monitor_width = monitor['width']
            self.monitor_height = monitor['height']
        
        # Calculate sidebar width - UI scales responsively to fit any width
        self.win_width_px = int(self.monitor_width * self.SIDEBAR_WIDTH_RATIO)
        
        if self.sidebar_side == 'left':
            self.edge_x_px = self.monitor_left
            self.park_x_px = self.monitor_left - self.win_width_px - 500
        else:
            self.edge_x_px = self.monitor_right - self.win_width_px
            self.park_x_px = self.monitor_right + 500
        
        logger.debug(f"Monitor {self.selected_monitor + 1}: {self.monitor_width}x{self.monitor_height} @ ({self.monitor_left}, {self.monitor_top})")

    def _lock_window_style(self, hwnd: int):
        if not hwnd or hwnd in self._locked_hwnds:
            return
        try:
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style &= ~(WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style |= WS_EX_TOOLWINDOW
            ex_style &= ~WS_EX_APPWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
            self._locked_hwnds.add(hwnd)
            logger.debug(f"Fensterstil für HWND {hwnd} gesperrt")
        except Exception as e:
            logger.error(f"Fehler beim Sperren des Fensterstils: {e}")

    def _get_window_rect(self, hwnd: int) -> Optional[Dict[str, int]]:
        try:
            rect = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return {'x': rect.left, 'y': rect.top, 'width': rect.right - rect.left, 'height': rect.bottom - rect.top}
        except Exception:
            pass
        return None

    def _enforce_window_position(self, hwnd: int, target: Dict[str, int]) -> bool:
        try:
            if not user32.IsWindow(hwnd):
                return False
            current = self._get_window_rect(hwnd)
            if not current:
                return False
            tolerance = 2
            needs_correction = (
                abs(current['x'] - target['x']) > tolerance or
                abs(current['y'] - target['y']) > tolerance or
                abs(current['width'] - target['w']) > tolerance or
                abs(current['height'] - target['h']) > tolerance
            )
            if needs_correction:
                user32.SetWindowPos(hwnd, 0, target['x'], target['y'], target['w'], target['h'], SWP_NOZORDER | SWP_NOACTIVATE)
                return True
        except Exception as e:
            logger.error(f"Fehler beim Erzwingen der Position: {e}")
        return False

    def _find_window_handles(self):
        try:
            if not self.hwnd_nav:
                self.hwnd_nav = user32.FindWindowW(None, self.title_nav)
                if self.hwnd_nav:
                    self._lock_window_style(self.hwnd_nav)
                    if not self._windows_created:
                        self._hide_window(self.hwnd_nav)
                    logger.info(f"Navigation-Fenster gefunden: HWND {self.hwnd_nav}")
            if not self.hwnd_browser:
                self.hwnd_browser = user32.FindWindowW(None, self.title_browser)
                if self.hwnd_browser:
                    self._lock_window_style(self.hwnd_browser)
                    if not self._windows_created:
                        self._hide_window(self.hwnd_browser)
                    logger.info(f"Browser-Fenster gefunden: HWND {self.hwnd_browser}")
            if self.hwnd_nav and self.hwnd_browser and not self._windows_created:
                self._windows_created = True
                logger.info("Beide Fenster initialisiert")
        except Exception as e:
            logger.error(f"Fehler beim Ermitteln der Fenster-Handles: {e}")

    def _set_window_position(self, hwnd: int, x: int, y: int, w: int, h: int, show: bool = True):
        try:
            flags = SWP_NOZORDER | SWP_NOACTIVATE
            if show:
                flags |= SWP_SHOWWINDOW
            user32.SetWindowPos(hwnd, 0, x, y, w, h, flags)
            with self._lock:
                self._target_positions[hwnd] = {'x': x, 'y': y, 'w': w, 'h': h}
        except Exception as e:
            logger.error(f"Fehler beim Setzen der Fensterposition: {e}")

    def _hide_window(self, hwnd: int):
        try:
            user32.ShowWindow(hwnd, 0)
            with self._lock:
                self._target_positions.pop(hwnd, None)
        except Exception as e:
            logger.error(f"Fehler beim Verstecken des Fensters: {e}")

    def _show_window(self, hwnd: int):
        try:
            user32.ShowWindow(hwnd, 4)
        except Exception as e:
            logger.error(f"Fehler beim Anzeigen des Fensters: {e}")

    def _show_windows(self):
        target_x = self.edge_x_px
        nav_y = self.monitor_top
        expanded_height = 520
        nav_height = expanded_height if self._nav_expanded else self.NAV_HEIGHT
        browser_y = self.monitor_top + self.NAV_HEIGHT
        browser_h = self.monitor_height - self.NAV_HEIGHT
        
        # WICHTIG: Erst positionieren (ohne anzuzeigen), dann anzeigen
        # Dies verhindert Flackern, weil das Fenster nicht kurz an der alten Position erscheint
        
        if self._nav_expanded:
            browser_y_adjusted = self.monitor_top + expanded_height
            browser_h_adjusted = self.monitor_height - expanded_height
            # Erst positionieren ohne anzuzeigen
            self._set_window_position(self.hwnd_nav, target_x, nav_y, self.win_width_px, nav_height, show=False)
            self._set_window_position(self.hwnd_browser, target_x, browser_y_adjusted, self.win_width_px, browser_h_adjusted, show=False)
            # Dann beide Fenster gleichzeitig anzeigen
            self._show_window(self.hwnd_nav)
            self._show_window(self.hwnd_browser)
            self._sync_settings_overlay_state(True)
        else:
            # Erst positionieren ohne anzuzeigen
            self._set_window_position(self.hwnd_nav, target_x, nav_y, self.win_width_px, nav_height, show=False)
            self._set_window_position(self.hwnd_browser, target_x, browser_y, self.win_width_px, browser_h, show=False)
            # Dann beide Fenster gleichzeitig anzeigen
            self._show_window(self.hwnd_nav)
            self._show_window(self.hwnd_browser)

    def _sync_settings_overlay_state(self, should_be_open: bool):
        try:
            if self.nav_window:
                if should_be_open:
                    self.nav_window.evaluate_js("document.getElementById('settings-overlay').classList.add('open');")
                else:
                    self.nav_window.evaluate_js("document.getElementById('settings-overlay').classList.remove('open');")
        except Exception as e:
            logger.debug(f"Settings-Overlay Sync fehlgeschlagen: {e}")

    def _hide_windows(self):
        self._hide_window(self.hwnd_nav)
        self._hide_window(self.hwnd_browser)

    def _inject_anti_drag_css(self):
        fix_script = """
        (function() {
            if (document.getElementById('anti-drag-fix')) return;
            const style = document.createElement('style');
            style.id = 'anti-drag-fix';
            style.innerHTML = `
                * { -webkit-app-region: no-drag !important; app-region: no-drag !important;
                    user-select: text !important; -webkit-user-select: text !important; }
                body, html { cursor: auto !important; user-select: text !important; }
                [draggable="true"] { -webkit-app-region: no-drag !important; }
            `;
            document.head.appendChild(style);
        })();
        """
        try:
            if self.browser_window:
                self.browser_window.evaluate_js(fix_script)
            if self.nav_window:
                self.nav_window.evaluate_js(fix_script)
        except Exception as e:
            logger.debug(f"Anti-drag injection fehlgeschlagen: {e}")

    def _schedule_delayed_action(self, delay: float, action: callable):
        timer = threading.Timer(delay, action)
        timer.daemon = True
        timer.start()
        with self._lock:
            self._pending_timers = [t for t in self._pending_timers if t.is_alive()]
            self._pending_timers.append(timer)

    def _generate_llm_buttons_html(self) -> str:
        buttons = []
        for i, llm_key in enumerate(self.selected_llms):
            if llm_key not in AVAILABLE_LLMS:
                continue
            llm = AVAILABLE_LLMS[llm_key]
            active = "active" if i == self.current_active_llm else ""
            safe_url = html.escape(llm['url'])
            safe_domain = html.escape(llm['domain'])
            safe_name = html.escape(llm['name'])
            buttons.append(f'''<button id="nav-{html.escape(llm_key)}-{i}" class="gpt-btn {active}" onclick="changeApp('{safe_url}', this, {i})"><img class="icon" src="https://www.google.com/s2/favicons?sz=64&domain={safe_domain}"><span class="label">{safe_name}</span></button>''')
        return '\n'.join(buttons)

    def _reload_nav(self):
        if not self.nav_window:
            return
        try:
            buttons_html = self._generate_llm_buttons_html()
            escaped_html = buttons_html.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
            self.nav_window.evaluate_js(f"""
                (function() {{
                    const group = document.querySelector('.gpt-group');
                    if (group) group.innerHTML = `{escaped_html}`;
                }})();
            """)
            self._needs_nav_reload = False
            logger.debug("Navigation aktualisiert")
        except Exception as e:
            logger.error(f"Fehler beim Neuladen der Navigation: {e}")

    def load_url(self, url: str):
        if not isinstance(url, str) or not url.startswith('https://'):
            logger.warning("Ungültige URL abgelehnt (kein https)")
            return
        try:
            parsed = urlparse(url)
            url_host = (parsed.hostname or "").lower()
            if parsed.scheme != "https":
                return
            if not url_host:
                return
            if url_host.startswith('www.'):
                url_host = url_host[4:]
            allowed_domains = set()
            for llm in AVAILABLE_LLMS.values():
                domain = llm['domain'].lower()
                if domain.startswith('www.'):
                    domain = domain[4:]
                allowed_domains.add(domain)
            url_valid = False
            for allowed in allowed_domains:
                if url_host == allowed or url_host.endswith(f".{allowed}"):
                    url_valid = True
                    break
            if not url_valid:
                logger.warning(f"URL-Domain nicht in Whitelist: {url_host}")
                return
        except Exception as e:
            logger.warning(f"URL-Parsing fehlgeschlagen: {e}")
            return
        try:
            self.browser_window.load_url(url)
            logger.info(f"URL geladen: {url_host}{parsed.path}")
            self._schedule_delayed_action(1.0, self._inject_anti_drag_css)
            self._schedule_delayed_action(1.1, lambda: self._apply_font_size())
        except Exception as e:
            logger.error(f"Fehler beim Laden der URL: {e}")

    def _apply_font_size(self):
        try:
            if self.browser_window:
                self.browser_window.evaluate_js(f"document.body.style.zoom = '{self.current_font_size}%';")
        except Exception:
            pass

    def set_font_size(self, size: int) -> int:
        self.current_font_size = SettingsValidator.validate_font_size(size)
        self._apply_font_size()
        self._save_settings_debounced()
        return self.current_font_size

    def set_remain_in_chat(self, minutes: int) -> int:
        if minutes not in [0, 10, 30]:
            minutes = 0
        self.remain_in_chat = minutes
        self._save_settings_debounced()
        logger.info(f"Remain in chat gesetzt auf: {minutes} Minuten")
        return self.remain_in_chat

    def get_remain_in_chat(self) -> int:
        return self.remain_in_chat

    def set_sidebar_side(self, side: str) -> str:
        if side not in ['left', 'right']:
            side = 'right'
        if side == self.sidebar_side:
            return self.sidebar_side
        with self._lock:
            self.sidebar_side = side
            self._update_monitor_settings()
            self._save_settings_debounced()
            if self.hwnd_nav and self.hwnd_browser:
                if self.is_visible:
                    self._show_windows()
                else:
                    self._hide_windows()
            logger.info(f"Sidebar-Seite gewechselt zu: {side}")
        return self.sidebar_side

    def get_sidebar_side(self) -> str:
        return self.sidebar_side

    def switch_to_llm(self, slot: int) -> bool:
        if not (0 <= slot < 3):
            return False
        llm_key = self.selected_llms[slot]
        if llm_key not in AVAILABLE_LLMS:
            return False
        self.current_active_llm = slot
        base_url = AVAILABLE_LLMS[llm_key]['url']
        url_to_load = base_url
        if self.remain_in_chat > 0 and llm_key in self._llm_last_urls:
            last_data = self._llm_last_urls[llm_key]
            last_url = last_data.get('url', '')
            last_time = last_data.get('timestamp', 0)
            elapsed_minutes = (time.time() - last_time) / 60
            if elapsed_minutes < self.remain_in_chat and last_url:
                url_to_load = last_url
                logger.info(f"Verwende letzte URL für {llm_key}: {last_url[:50]}... (vor {elapsed_minutes:.1f} Min)")
        self.load_url(url_to_load)
        return True

    def _save_current_url(self, llm_key: str):
        try:
            if self.browser_window:
                current_url = self.browser_window.get_current_url()
                if current_url:
                    self._llm_last_urls[llm_key] = {'url': current_url, 'timestamp': time.time()}
                    logger.debug(f"URL gespeichert für {llm_key}: {current_url[:50]}...")
        except Exception as e:
            logger.debug(f"Konnte URL nicht speichern: {e}")

    def set_active_llm(self, slot: int) -> bool:
        if 0 <= slot < 3:
            if self.remain_in_chat > 0:
                old_llm_key = self.selected_llms[self.current_active_llm]
                self._save_current_url(old_llm_key)
            self.current_active_llm = slot
            return True
        return False

    def change_monitor(self, monitor_index: int) -> bool:
        validated_index = SettingsValidator.validate_monitor_index(monitor_index, len(self.monitors))
        if validated_index == self.selected_monitor:
            return False
        with self._lock:
            logger.info(f"Wechsle zu Monitor {validated_index + 1}")
            self.selected_monitor = validated_index
            self._update_monitor_settings()
            self._save_settings_debounced()
            if self.hwnd_nav and self.hwnd_browser:
                self._hide_window(self.hwnd_nav)
                self._hide_window(self.hwnd_browser)
                if self._is_pinned:
                    self.is_visible = True
                    self._last_visible_state = None
                    self._schedule_delayed_action(0.1, self._show_windows)
                else:
                    self.is_visible = False
                    self._last_visible_state = None
        return True

    def change_llm(self, slot: int, llm_key: str) -> bool:
        if not (0 <= slot < 3) or llm_key not in VALID_LLM_KEYS:
            return False
        if self.selected_llms[slot] == llm_key:
            return False
        with self._lock:
            self.selected_llms[slot] = llm_key
            self._save_settings_debounced()
            if slot == self.current_active_llm:
                self.load_url(AVAILABLE_LLMS[llm_key]['url'])
            self._needs_nav_reload = True
        return True

    def get_monitor_list(self) -> List[Dict[str, Any]]:
        return [
            {'index': i, 'name': f"Monitor {i + 1}", 'resolution': f"{mon['width']}x{mon['height']}", 'selected': i == self.selected_monitor}
            for i, mon in enumerate(self.monitors)
        ]

    def refresh_monitors(self) -> List[Dict[str, Any]]:
        """Aktualisiert die Monitor-Liste und gibt sie zurück"""
        old_count = len(self.monitors)
        self.monitors = self.monitor_enum.get_monitors()
        new_count = len(self.monitors)
        
        # Wenn der ausgewählte Monitor nicht mehr existiert, auf Monitor 0 wechseln
        if self.selected_monitor >= new_count:
            logger.info(f"Ausgewählter Monitor {self.selected_monitor + 1} nicht mehr verfügbar, wechsle zu Monitor 1")
            self.selected_monitor = 0
            self._update_monitor_settings()
            self._save_settings_debounced()
        
        if old_count != new_count:
            logger.info(f"Monitor-Anzahl geändert: {old_count} -> {new_count}")
            # Aktualisiere Monitor-Einstellungen falls nötig
            self._update_monitor_settings()
        
        return self.get_monitor_list()

    def get_llm_list(self) -> List[Dict[str, str]]:
        return [{'key': k, 'name': v['name']} for k, v in AVAILABLE_LLMS.items()]

    def get_prompts(self) -> List[Dict[str, Any]]:
        return self.prompts.copy()

    def get_fast_access_prompts(self) -> List[Dict[str, Any]]:
        return [p for p in self.prompts if p.get('fast_access', True)]

    def add_prompt(self, name: str, content: str, fast_access: bool = True) -> bool:
        validated = SettingsValidator.validate_prompt({'name': name, 'content': content, 'fast_access': fast_access})
        if not validated:
            logger.warning("Ungültiger Prompt abgelehnt")
            return False
        with self._lock:
            self.prompts.append(validated)
            self._save_prompts(self.prompts)
            self._needs_nav_reload = True
        logger.info(f"Neuer Prompt hinzugefügt: {validated['name']}")
        return True

    def update_prompt(self, index: int, name: str = None, content: str = None, fast_access: bool = None) -> bool:
        with self._lock:
            if 0 <= index < len(self.prompts):
                prompt = self.prompts[index]
                if name is not None:
                    prompt['name'] = name[:150].strip()
                if content is not None:
                    prompt['content'] = content[:2000].strip()
                if fast_access is not None:
                    prompt['fast_access'] = bool(fast_access)
                self._save_prompts(self.prompts)
                self._needs_nav_reload = True
                logger.info(f"Prompt aktualisiert: {prompt['name']}")
                return True
        return False

    def toggle_prompt_fast_access(self, index: int) -> bool:
        with self._lock:
            if 0 <= index < len(self.prompts):
                current = self.prompts[index].get('fast_access', True)
                self.prompts[index]['fast_access'] = not current
                self._save_prompts(self.prompts)
                self._needs_nav_reload = True
                logger.info(f"Prompt '{self.prompts[index]['name']}' fast_access: {not current}")
                return not current
        return False

    def delete_prompt(self, index: int) -> bool:
        with self._lock:
            if 0 <= index < len(self.prompts):
                removed = self.prompts.pop(index)
                self._save_prompts(self.prompts)
                self._needs_nav_reload = True
                logger.info(f"Prompt gelöscht: {removed['name']}")
                return True
        return False

    def expand_nav(self, expanded: bool) -> bool:
        with self._lock:
            self._nav_expanded = expanded
            if self.is_visible and self.hwnd_nav and self.hwnd_browser:
                target_x = self.edge_x_px
                nav_y = self.monitor_top
                if expanded:
                    expanded_height = 520
                    self._set_window_position(self.hwnd_nav, target_x, nav_y, self.win_width_px, expanded_height)
                    browser_y = self.monitor_top + expanded_height
                    browser_h = self.monitor_height - expanded_height
                    self._set_window_position(self.hwnd_browser, target_x, browser_y, self.win_width_px, browser_h)
                else:
                    browser_y = self.monitor_top + self.NAV_HEIGHT
                    browser_h = self.monitor_height - self.NAV_HEIGHT
                    self._set_window_position(self.hwnd_browser, target_x, browser_y, self.win_width_px, browser_h)
                    self._set_window_position(self.hwnd_nav, target_x, nav_y, self.win_width_px, self.NAV_HEIGHT)
            return True

    def bring_nav_to_front(self) -> bool:
        if self.hwnd_nav:
            self._bring_to_front(self.hwnd_nav)
            return True
        return False

    def toggle_pin(self) -> bool:
        with self._lock:
            self._is_pinned = not self._is_pinned
            logger.info(f"Sidebar {'fixiert' if self._is_pinned else 'nicht fixiert'}")
            if self._is_pinned and not self.is_visible:
                self.is_visible = True
                if self.hwnd_nav and self.hwnd_browser:
                    self._show_windows()
                    self._last_visible_state = True
            return self._is_pinned

    def _bring_to_front(self, hwnd: int):
        try:
            user32.BringWindowToTop(hwnd)
        except Exception as e:
            logger.error(f"Fehler beim In-den-Vordergrund-Bringen: {e}")

    def inject_prompt(self, prompt_text: str) -> bool:
        """Injiziert einen Prompt in das aktuelle LLM-Eingabefeld"""
        if not isinstance(prompt_text, str):
            logger.warning("inject_prompt: Kein gültiger Text")
            return False
        
        if not self.browser_window:
            logger.warning("inject_prompt: Kein Browser-Fenster verfügbar")
            return False
            
        safe_text = SettingsValidator.sanitize_string(prompt_text, 10000)
        escaped_text = json.dumps(safe_text)
        
        injection_script = f"""
        (function() {{
            const text = {escaped_text};
            
            // Helper: Simulate typing for React/Vue controlled inputs
            function simulateTyping(el, text) {{
                try {{
                    el.focus();
                    
                    // For React controlled components, we need to use native input setter
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set 
                        || Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                    
                    if (nativeInputValueSetter) {{
                        nativeInputValueSetter.call(el, text);
                    }} else {{
                        el.value = text;
                    }}
                    
                    // Dispatch events that React listens to
                    el.dispatchEvent(new Event('input', {{ bubbles: true, cancelable: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true, cancelable: true }}));
                    
                    // For some frameworks - InputEvent
                    try {{
                        el.dispatchEvent(new InputEvent('input', {{
                            bubbles: true,
                            cancelable: true,
                            inputType: 'insertText',
                            data: text
                        }}));
                    }} catch(e) {{}}
                    
                    return true;
                }} catch(e) {{
                    console.log('AI Slidebar: simulateTyping error:', e);
                    return false;
                }}
            }}
            
            // Helper: Insert into contenteditable using safe methods (no innerHTML)
            function insertIntoContentEditable(el, text) {{
                try {{
                    el.focus();
                    
                    // Select all existing content
                    const selection = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    selection.removeAllRanges();
                    selection.addRange(range);
                    
                    // Try execCommand insertText (safest method)
                    if (document.execCommand('insertText', false, text)) {{
                        console.log('AI Slidebar: execCommand insertText successful');
                        return true;
                    }}
                }} catch(e) {{
                    console.log('AI Slidebar: execCommand failed:', e);
                }}
                
                try {{
                    el.focus();
                    
                    // Clear using safe methods
                    while (el.firstChild) {{
                        el.removeChild(el.firstChild);
                    }}
                    
                    // Insert text node
                    const textNode = document.createTextNode(text);
                    el.appendChild(textNode);
                    
                    // Place cursor at end
                    const selection = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(el);
                    range.collapse(false);
                    selection.removeAllRanges();
                    selection.addRange(range);
                    
                    // Dispatch input events
                    el.dispatchEvent(new Event('input', {{ bubbles: true, cancelable: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true, cancelable: true }}));
                    
                    try {{
                        el.dispatchEvent(new InputEvent('input', {{
                            bubbles: true,
                            cancelable: true,
                            inputType: 'insertText',
                            data: text
                        }}));
                    }} catch(e) {{}}
                    
                    console.log('AI Slidebar: textNode insertion successful');
                    return true;
                }} catch(e) {{
                    console.log('AI Slidebar: insertIntoContentEditable error:', e);
                    return false;
                }}
            }}
            
            // Helper: Check if element is visible
            function isVisible(el) {{
                if (!el) return false;
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetParent !== null;
            }}
            
            // Get hostname
            let hostname = window.location.hostname.toLowerCase();
            if (hostname.startsWith('www.')) hostname = hostname.substring(4);
            
            console.log('AI Slidebar: Attempting injection on ' + hostname);
            
            // ============================================
            // ChatGPT - Uses React with special textarea/contenteditable
            // ============================================
            if (hostname.includes('chatgpt.com') || hostname.includes('chat.openai.com')) {{
                console.log('AI Slidebar: ChatGPT detected');
                
                // Try contenteditable first (newer UI)
                const contentEditable = document.querySelector('#prompt-textarea[contenteditable="true"]')
                    || document.querySelector('div[contenteditable="true"][data-placeholder]')
                    || document.querySelector('[contenteditable="true"][id*="prompt"]');
                
                if (contentEditable && isVisible(contentEditable)) {{
                    if (insertIntoContentEditable(contentEditable, text)) {{
                        console.log('AI Slidebar: ChatGPT contenteditable injection successful');
                        return true;
                    }}
                }}
                
                // Try textarea
                const textarea = document.querySelector('#prompt-textarea')
                    || document.querySelector('textarea[data-id]')
                    || document.querySelector('form textarea');
                
                if (textarea && isVisible(textarea) && textarea.tagName === 'TEXTAREA') {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: ChatGPT textarea injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // Claude - Uses ProseMirror contenteditable
            // ============================================
            if (hostname.includes('claude.ai')) {{
                console.log('AI Slidebar: Claude detected');
                
                const proseMirror = document.querySelector('div.ProseMirror[contenteditable="true"]')
                    || document.querySelector('[contenteditable="true"].ProseMirror')
                    || document.querySelector('fieldset [contenteditable="true"]')
                    || document.querySelector('[contenteditable="true"]');
                
                if (proseMirror && isVisible(proseMirror)) {{
                    if (insertIntoContentEditable(proseMirror, text)) {{
                        console.log('AI Slidebar: Claude injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // Gemini - Uses rich-textarea with contenteditable
            // ============================================
            if (hostname.includes('gemini.google.com')) {{
                console.log('AI Slidebar: Gemini detected');
                
                // Gemini uses contenteditable divs
                const richTextarea = document.querySelector('rich-textarea [contenteditable="true"]')
                    || document.querySelector('.ql-editor[contenteditable="true"]')
                    || document.querySelector('[contenteditable="true"][role="textbox"]')
                    || document.querySelector('[contenteditable="true"][aria-label]')
                    || document.querySelector('div[contenteditable="true"]');
                
                if (richTextarea && isVisible(richTextarea)) {{
                    if (insertIntoContentEditable(richTextarea, text)) {{
                        console.log('AI Slidebar: Gemini injection successful');
                        return true;
                    }}
                }}
                
                // Fallback textarea
                const textarea = document.querySelector('textarea');
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: Gemini textarea fallback successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // Perplexity - Uses textarea (React)
            // ============================================
            if (hostname.includes('perplexity.ai')) {{
                console.log('AI Slidebar: Perplexity detected');
                
                const textarea = document.querySelector('textarea[placeholder*="Ask"]')
                    || document.querySelector('textarea[placeholder*="Frag"]')
                    || document.querySelector('textarea[placeholder*="Search"]')
                    || document.querySelector('textarea.overflow-auto')
                    || document.querySelector('main textarea')
                    || document.querySelector('textarea');
                
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: Perplexity injection successful');
                        return true;
                    }}
                }}
                
                // Perplexity might also use contenteditable
                const contentEditable = document.querySelector('[contenteditable="true"]');
                if (contentEditable && isVisible(contentEditable)) {{
                    if (insertIntoContentEditable(contentEditable, text)) {{
                        console.log('AI Slidebar: Perplexity contenteditable injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // Grok (X.com)
            // ============================================
            if (hostname.includes('x.com') || hostname.includes('twitter.com') || hostname.includes('grok')) {{
                console.log('AI Slidebar: Grok/X detected');
                
                const textarea = document.querySelector('textarea[data-testid="grokTextarea"]')
                    || document.querySelector('[data-testid="grokComposer"] textarea')
                    || document.querySelector('textarea[placeholder*="Grok"]')
                    || document.querySelector('textarea[placeholder*="grok"]')
                    || document.querySelector('textarea');
                
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: Grok injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // Copilot (Microsoft)
            // ============================================
            if (hostname.includes('copilot.microsoft.com') || hostname.includes('bing.com')) {{
                console.log('AI Slidebar: Copilot detected');
                
                const textarea = document.querySelector('#userInput')
                    || document.querySelector('textarea[name="searchbox"]')
                    || document.querySelector('#searchbox')
                    || document.querySelector('textarea[placeholder*="message" i]')
                    || document.querySelector('textarea');
                
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: Copilot injection successful');
                        return true;
                    }}
                }}
                
                const contentEditable = document.querySelector('[contenteditable="true"]');
                if (contentEditable && isVisible(contentEditable)) {{
                    if (insertIntoContentEditable(contentEditable, text)) {{
                        console.log('AI Slidebar: Copilot contenteditable injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // Mistral
            // ============================================
            if (hostname.includes('mistral.ai') || hostname.includes('chat.mistral')) {{
                console.log('AI Slidebar: Mistral detected');
                
                const textarea = document.querySelector('textarea[placeholder*="Message"]')
                    || document.querySelector('textarea[placeholder*="Nachricht"]')
                    || document.querySelector('textarea');
                
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: Mistral injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // HuggingChat
            // ============================================
            if (hostname.includes('huggingface.co')) {{
                console.log('AI Slidebar: HuggingChat detected');
                
                const textarea = document.querySelector('textarea.scrollbar-custom')
                    || document.querySelector('textarea[placeholder*="Ask"]')
                    || document.querySelector('textarea');
                
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: HuggingChat injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // Poe
            // ============================================
            if (hostname.includes('poe.com')) {{
                console.log('AI Slidebar: Poe detected');
                
                const textarea = document.querySelector('textarea[class*="TextArea"]')
                    || document.querySelector('textarea.GrowingTextArea_textArea__eadlu')
                    || document.querySelector('textarea');
                
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: Poe injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // Pi.ai
            // ============================================
            if (hostname.includes('pi.ai')) {{
                console.log('AI Slidebar: Pi detected');
                
                const textarea = document.querySelector('textarea[placeholder]')
                    || document.querySelector('textarea');
                
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: Pi injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // You.com
            // ============================================
            if (hostname.includes('you.com')) {{
                console.log('AI Slidebar: You.com detected');
                
                const textarea = document.querySelector('textarea[placeholder*="Ask"]')
                    || document.querySelector('textarea');
                
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: You.com injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // DeepSeek
            // ============================================
            if (hostname.includes('deepseek.com') || hostname.includes('chat.deepseek')) {{
                console.log('AI Slidebar: DeepSeek detected');
                
                const textarea = document.querySelector('textarea[placeholder]')
                    || document.querySelector('textarea');
                
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: DeepSeek injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // Le Chat (Mistral alternative)
            // ============================================
            if (hostname.includes('chat.mistral') || hostname.includes('lechat')) {{
                console.log('AI Slidebar: Le Chat detected');
                
                const textarea = document.querySelector('textarea');
                if (textarea && isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: Le Chat injection successful');
                        return true;
                    }}
                }}
            }}
            
            // ============================================
            // Generic fallback
            // ============================================
            console.log('AI Slidebar: Trying generic fallback');
            
            // Try visible textareas first
            const textareas = document.querySelectorAll('textarea:not([readonly]):not([disabled])');
            for (const textarea of textareas) {{
                if (isVisible(textarea)) {{
                    if (simulateTyping(textarea, text)) {{
                        console.log('AI Slidebar: Generic textarea injection successful');
                        return true;
                    }}
                }}
            }}
            
            // Try contenteditables
            const editables = document.querySelectorAll('[contenteditable="true"]');
            for (const el of editables) {{
                if (isVisible(el)) {{
                    if (insertIntoContentEditable(el, text)) {{
                        console.log('AI Slidebar: Generic contenteditable injection successful');
                        return true;
                    }}
                }}
            }}
            
            console.log('AI Slidebar: No suitable input element found');
            return false;
        }})();
        """
        
        try:
            result = self.browser_window.evaluate_js(injection_script)
            if result:
                logger.info(f"Prompt erfolgreich injiziert (Länge: {len(safe_text)} Zeichen)")
            else:
                logger.warning("Prompt-Injection: Kein passendes Eingabefeld gefunden")
            return bool(result)
        except Exception as e:
            logger.error(f"Fehler beim Injizieren des Prompts: {e}")
        return False

    def _handle_download(self, url: str, suggested_filename: str, content: bytes) -> bool:
        """Handler für Downloads aus dem Browser-Fenster"""
        try:
            if not suggested_filename:
                # Extract filename from URL if not provided
                from urllib.parse import unquote
                suggested_filename = unquote(url.split('/')[-1].split('?')[0]) or 'download'
            
            # Ensure safe filename
            safe_filename = "".join(c for c in suggested_filename if c.isalnum() or c in '._- ')
            if not safe_filename:
                safe_filename = 'download'
            
            filepath = os.path.join(self.download_folder, safe_filename)
            
            # Handle duplicate filenames
            base, ext = os.path.splitext(filepath)
            counter = 1
            while os.path.exists(filepath):
                filepath = f"{base}_{counter}{ext}"
                counter += 1
            
            with open(filepath, 'wb') as f:
                f.write(content)
            
            logger.info(f"Download gespeichert: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Download: {e}")
            return False

    def exit_all(self):
        logger.info("Anwendung wird beendet...")
        self.is_running = False
        with self._lock:
            for timer in self._pending_timers:
                try:
                    timer.cancel()
                except:
                    pass
            self._pending_timers.clear()
        try:
            if self.browser_window:
                self.browser_window.destroy()
        except:
            pass
        try:
            if self.nav_window:
                self.nav_window.destroy()
        except:
            pass
        time.sleep(0.3)
        logger.info("Anwendung beendet")
        sys.exit(0)

    def _position_enforcer_thread(self):
        logger.info("Position-Enforcer gestartet")
        while self.is_running:
            try:
                with self._lock:
                    targets = dict(self._target_positions)
                    is_active = bool(targets)
                if is_active:
                    for hwnd, target in targets.items():
                        if hwnd:
                            self._enforce_window_position(hwnd, target)
                    time.sleep(self.ENFORCER_INTERVAL_ACTIVE)
                else:
                    time.sleep(self.ENFORCER_INTERVAL_IDLE)
            except Exception as e:
                logger.error(f"Fehler im Position-Enforcer: {e}")
                time.sleep(0.1)
        logger.info("Position-Enforcer beendet")

    def _get_adjacent_monitor_info(self) -> Optional[Dict[str, Any]]:
        """
        Checks if the sidebar is positioned at an inner edge between two monitors.
        Returns info about the adjacent monitor if found, None otherwise.
        """
        if len(self.monitors) < 2:
            return None
        
        current_monitor = self.monitors[self.selected_monitor]
        
        for i, mon in enumerate(self.monitors):
            if i == self.selected_monitor:
                continue
            
            # Check if monitors share vertical space (Y overlap)
            y_overlap = (mon['top'] < current_monitor['bottom'] and 
                        mon['bottom'] > current_monitor['top'])
            
            if not y_overlap:
                continue
            
            if self.sidebar_side == 'left':
                # Sidebar is on left side of current monitor
                # Check if adjacent monitor is to the LEFT (its right edge touches our left edge)
                if abs(mon['right'] - current_monitor['left']) <= 5:
                    return {
                        'index': i,
                        'monitor': mon,
                        'position': 'left'  # Adjacent monitor is to the left
                    }
            else:
                # Sidebar is on right side of current monitor
                # Check if adjacent monitor is to the RIGHT (its left edge touches our right edge)
                if abs(mon['left'] - current_monitor['right']) <= 5:
                    return {
                        'index': i,
                        'monitor': mon,
                        'position': 'right'  # Adjacent monitor is to the right
                    }
        
        return None

    def _mouse_monitor_thread(self):
        time.sleep(1.5)
        logger.info("Maus-Monitor gestartet")
        while self.is_running and not (self.hwnd_nav and self.hwnd_browser):
            self._find_window_handles()
            time.sleep(0.1)
        if not self.is_running:
            return
        self._hide_window(self.hwnd_nav)
        self._hide_window(self.hwnd_browser)
        time.sleep(0.3)
        self._inject_anti_drag_css()
        enforcer = threading.Thread(target=self._position_enforcer_thread, daemon=True)
        enforcer.start()
        
        while self.is_running:
            try:
                if self._needs_nav_reload:
                    self._reload_nav()
                pt = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                
                # Check if sidebar is at inner edge between monitors
                adjacent_info = self._get_adjacent_monitor_info()
                
                # Check if cursor is within the selected monitor's Y range
                in_monitor_y = (self.monitor_top <= pt.y < self.monitor_top + self.monitor_height)
                
                # Check if cursor is fully within the selected monitor
                in_monitor_area = (self.monitor_left <= pt.x <= self.monitor_right) and in_monitor_y
                
                # Determine if cursor is in the sidebar area (when visible)
                if self.sidebar_side == 'left':
                    in_sidebar_area = (pt.x >= self.monitor_left) and (pt.x <= self.monitor_left + self.win_width_px) and in_monitor_y
                else:
                    in_sidebar_area = (pt.x >= self.edge_x_px) and (pt.x <= self.monitor_right) and in_monitor_y

                # Trigger zone logic - SIMPLIFIED for inner edges
                # Edge trigger on sidebar's own monitor is only 5px wide
                EDGE_TRIGGER_WIDTH = 5
                
                if self.sidebar_side == 'left':
                    # Trigger at left edge of this monitor (5px zone)
                    at_edge = (pt.x >= self.monitor_left) and (pt.x <= self.monitor_left + EDGE_TRIGGER_WIDTH) and in_monitor_y
                    
                    if adjacent_info and adjacent_info['position'] == 'left':
                        # Sidebar is at inner edge - trigger when cursor is ANYWHERE on the adjacent monitor
                        adj_mon = adjacent_info['monitor']
                        adj_in_y = (adj_mon['top'] <= pt.y < adj_mon['bottom'])
                        on_adjacent_monitor = (pt.x >= adj_mon['left']) and (pt.x < adj_mon['right']) and adj_in_y
                    else:
                        # Sidebar is at outer edge - small trigger zone only
                        on_adjacent_monitor = False
                    
                    trigger_zone = at_edge or on_adjacent_monitor
                else:
                    # Trigger at right edge of this monitor (5px zone)
                    at_edge = (pt.x >= self.monitor_right - EDGE_TRIGGER_WIDTH) and (pt.x <= self.monitor_right) and in_monitor_y
                    
                    if adjacent_info and adjacent_info['position'] == 'right':
                        # Sidebar is at inner edge - trigger when cursor is ANYWHERE on the adjacent monitor
                        adj_mon = adjacent_info['monitor']
                        adj_in_y = (adj_mon['top'] <= pt.y < adj_mon['bottom'])
                        on_adjacent_monitor = (pt.x > adj_mon['left']) and (pt.x <= adj_mon['right']) and adj_in_y
                    else:
                        # Sidebar is at outer edge - small trigger zone only
                        on_adjacent_monitor = False
                    
                    trigger_zone = at_edge or on_adjacent_monitor

                # Extended sidebar area - includes adjacent monitor when at inner edge
                if self.sidebar_side == 'left':
                    if adjacent_info and adjacent_info['position'] == 'left':
                        adj_mon = adjacent_info['monitor']
                        adj_in_y = (adj_mon['top'] <= pt.y < adj_mon['bottom'])
                        # Sidebar area extends to include the entire adjacent monitor
                        on_adjacent = (pt.x >= adj_mon['left']) and (pt.x < adj_mon['right']) and adj_in_y
                        extended_sidebar_area = on_adjacent or in_sidebar_area
                    else:
                        extended_sidebar_area = in_sidebar_area
                else:
                    if adjacent_info and adjacent_info['position'] == 'right':
                        adj_mon = adjacent_info['monitor']
                        adj_in_y = (adj_mon['top'] <= pt.y < adj_mon['bottom'])
                        # Sidebar area extends to include the entire adjacent monitor
                        on_adjacent = (pt.x > adj_mon['left']) and (pt.x <= adj_mon['right']) and adj_in_y
                        extended_sidebar_area = on_adjacent or in_sidebar_area
                    else:
                        extended_sidebar_area = in_sidebar_area

                # Hide conditions - only hide when moved away on the SAME monitor as the sidebar
                if self.sidebar_side == 'left':
                    hide_boundary = self.monitor_left + self.win_width_px + 50
                    # Only hide when cursor moves away on the sidebar's own monitor
                    moved_away_on_same_monitor = (pt.x > hide_boundary) and in_monitor_y and (pt.x <= self.monitor_right)
                else:
                    hide_boundary = self.edge_x_px - 50
                    # Only hide when cursor moves away on the sidebar's own monitor
                    moved_away_on_same_monitor = (pt.x < hide_boundary) and in_monitor_y and (pt.x >= self.monitor_left)
                
                # Hide if cursor moves outside the Y range of both monitors
                moved_outside_y = not in_monitor_y
                if adjacent_info:
                    adj_mon = adjacent_info['monitor']
                    adj_in_y = (adj_mon['top'] <= pt.y < adj_mon['bottom'])
                    moved_outside_y = not in_monitor_y and not adj_in_y
                
                if not self._is_pinned:
                    if not self.is_visible:
                        # Show when in trigger zone (edge or anywhere on adjacent monitor)
                        if trigger_zone:
                            self.is_visible = True
                    else:
                        # Hide only when moved away on the sidebar's own monitor or outside Y range
                        if not extended_sidebar_area:
                            if moved_away_on_same_monitor or moved_outside_y:
                                self.is_visible = False
                
                if self.hwnd_nav and self.hwnd_browser:
                    if self.is_visible and self._last_visible_state != True:
                        self._show_windows()
                        self._last_visible_state = True
                    elif not self.is_visible and self._last_visible_state != False:
                        self._hide_windows()
                        self._last_visible_state = False
                
                time.sleep(0.016)
            except Exception as e:
                logger.error(f"Fehler im Maus-Monitor: {e}")
                time.sleep(0.1)
        logger.info("Maus-Monitor beendet")

    def run(self):
        """Startet die Anwendung"""
        monitor_options_html = ""
        for mon in self.get_monitor_list():
            selected = "selected" if mon['selected'] else ""
            monitor_options_html += f'<option value="{mon["index"]}" {selected}>{mon["name"]} ({mon["resolution"]})</option>'
        
        llm_options_html = {0: "", 1: "", 2: ""}
        for llm in self.get_llm_list():
            for slot in range(3):
                selected = "selected" if self.selected_llms[slot] == llm['key'] else ""
                safe_name = html.escape(llm['name'])
                safe_key = html.escape(llm['key'])
                llm_options_html[slot] += f'<option value="{safe_key}" {selected}>{safe_name}</option>'
        
        prompt_options_html = '<option value="-1">Quick Prompts...</option>'
        for i, prompt in enumerate(self.prompts):
            if prompt.get('fast_access', True):
                safe_name = html.escape(prompt['name'])
                prompt_options_html += f'<option value="{i}">{safe_name}</option>'
        
        all_prompts_options_html = '<option value="-1">-- Select Prompt --</option>'
        for i, prompt in enumerate(self.prompts):
            safe_name = html.escape(prompt['name'])
            all_prompts_options_html += f'<option value="{i}">{safe_name}</option>'
        
        llm_buttons_html = self._generate_llm_buttons_html()
        side_left_selected = "selected" if self.sidebar_side == "left" else ""
        side_right_selected = "selected" if self.sidebar_side == "right" else ""
        
        nav_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {{ 
                    --bg-color: #1e1e1e; 
                    --text-color: #d4d4d4; 
                    --btn-bg: #2d2d2d; 
                    --border: #444;
                    --hover-bg: #3a3a3a;
                }}
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{ 
                    background: var(--bg-color); 
                    color: var(--text-color); 
                    font-family: 'Segoe UI', sans-serif; 
                    overflow: hidden; 
                    user-select: none; 
                    -webkit-user-select: none;
                    height: 100%; 
                    width: 100%; 
                    -webkit-app-region: no-drag !important; 
                }}
                html {{ height: 100%; overflow: hidden; }}
                
                /* Main container - 2 rows */
                .main-nav {{ 
                    display: flex; 
                    flex-direction: column; 
                    padding: 8px; 
                    gap: 8px;
                    background: var(--bg-color); 
                    border-bottom: 1px solid var(--border);
                    height: 100%;
                }}
                
                /* Row 1: LLM buttons + utility buttons */
                .row-1 {{ 
                    display: flex; 
                    gap: 6px; 
                    align-items: stretch;
                    height: 44px;
                    flex-shrink: 0;
                }}
                
                /* Row 2: Prompts dropdown + inject button */
                .row-2 {{ 
                    display: flex; 
                    gap: 6px; 
                    align-items: stretch;
                    height: 36px;
                    flex-shrink: 0;
                }}
                
                /* LLM button group */
                .gpt-group {{ 
                    display: flex; 
                    gap: 6px; 
                    flex: 1;
                    min-width: 0;
                }}
                
                /* LLM buttons - rectangular with icon left of text */
                .gpt-btn {{ 
                    flex: 1 1 0;
                    height: 100%;
                    min-width: 0;
                    display: flex;
                    flex-direction: row;
                    align-items: center;
                    justify-content: center;
                    gap: 6px;
                    padding: 0 10px;
                    background: var(--btn-bg); 
                    border: 1px solid var(--border); 
                    border-radius: 8px; 
                    color: var(--text-color);
                    cursor: pointer; 
                    transition: all 0.15s ease;
                    font-size: 12px;
                    font-weight: 500;
                }}
                .gpt-btn:hover {{ 
                    background: var(--hover-bg); 
                    border-color: #555;
                }}
                .gpt-btn.active {{ 
                    background: #4a9eff !important; 
                    border-color: #3a8eef !important; 
                    color: white !important;
                }}
                .gpt-btn .icon {{ 
                    width: 18px; 
                    height: 18px; 
                    flex-shrink: 0;
                    pointer-events: none;
                }}
                .gpt-btn .label {{ 
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    pointer-events: none;
                }}
                
                /* Utility buttons group */
                .utility-group {{ 
                    display: flex; 
                    gap: 6px; 
                    flex-shrink: 0;
                }}
                
                /* Utility buttons - square, same height as LLM buttons */
                .util-btn {{ 
                    width: 44px; 
                    height: 44px; 
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: var(--btn-bg); 
                    border: 1px solid var(--border); 
                    border-radius: 8px; 
                    color: var(--text-color);
                    cursor: pointer; 
                    transition: all 0.15s ease;
                    font-size: 18px;
                    flex-shrink: 0;
                }}
                .util-btn:hover {{ 
                    background: var(--hover-bg); 
                    border-color: #555;
                }}
                .util-btn.active {{ 
                    background: #4a9eff !important; 
                    border-color: #3a8eef !important; 
                    color: white !important;
                }}
                .util-btn.danger:hover {{ 
                    background: #e94560 !important; 
                    border-color: #c73e54 !important; 
                    color: white !important;
                }}
                
                /* Prompt group */
                .prompt-group {{ 
                    display: flex; 
                    gap: 6px; 
                    flex: 1;
                    align-items: stretch;
                }}
                
                /* Prompt dropdown */
                .prompt-select {{ 
                    flex: 1;
                    background: var(--btn-bg); 
                    color: var(--text-color); 
                    border: 1px solid var(--border);
                    border-radius: 6px; 
                    padding: 0 10px; 
                    font-size: 12px; 
                    font-family: 'Segoe UI', sans-serif;
                    cursor: pointer; 
                    outline: none;
                }}
                .prompt-select:hover {{ background: var(--hover-bg); }}
                .prompt-select:focus {{ border-color: #4a9eff; }}
                .prompt-select option {{
                    background: var(--btn-bg);
                    color: var(--text-color);
                }}
                
                /* Inject button */
                .inject-btn {{ 
                    width: 36px; 
                    height: 36px; 
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: #28a745; 
                    border: 1px solid #218838; 
                    border-radius: 6px; 
                    color: white;
                    cursor: pointer; 
                    transition: all 0.15s ease;
                    font-size: 14px;
                    flex-shrink: 0;
                }}
                .inject-btn:hover {{ background: #218838; }}
                
                /* Settings overlay */
                #settings-overlay {{ 
                    position: absolute; 
                    top: 110px; 
                    left: 0; 
                    right: 0;
                    background: var(--bg-color); 
                    display: none; 
                    flex-direction: column; 
                    padding: 12px; 
                    z-index: 50; 
                    gap: 10px;
                    overflow-y: auto;
                    max-height: calc(100vh - 110px);
                    border-bottom: 1px solid var(--border);
                }}
                #settings-overlay.open {{ display: flex; }}
                
                .settings-row {{ 
                    display: flex; 
                    align-items: center; 
                    gap: 10px; 
                    width: 100%;
                }}
                
                .settings-label {{
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 80px;
                    color: var(--text-color);
                }}
                
                .settings-select {{
                    flex: 1;
                    background: var(--btn-bg); 
                    color: var(--text-color); 
                    border: 1px solid var(--border);
                    border-radius: 6px; 
                    padding: 10px 12px; 
                    font-size: 13px; 
                    font-family: 'Segoe UI', sans-serif;
                    cursor: pointer; 
                    outline: none;
                }}
                .settings-select:hover {{ background: var(--hover-bg); }}
                .settings-select:focus {{ border-color: #4a9eff; }}
                .settings-select option {{
                    background: var(--btn-bg);
                    color: var(--text-color);
                }}
                
                .zoom-control {{
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }}
                
                .mode-btn {{
                    width: 44px;
                    height: 44px;
                }}
                
                .font-btn {{ 
                    width: 28px; 
                    height: 28px; 
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: var(--btn-bg); 
                    border: 1px solid var(--border); 
                    border-radius: 4px; 
                    color: var(--text-color);
                    cursor: pointer; 
                    font-size: 14px;
                }}
                .font-btn:hover {{ background: var(--hover-bg); }}
                #font-val {{ min-width: 40px; text-align: center; font-weight: 600; }}
                
                .prompt-repository {{ 
                    width: 100%; 
                    margin-top: 8px; 
                    padding-top: 8px; 
                    border-top: 1px solid var(--border); 
                }}
                .prompt-repo-header {{ 
                    display: flex; 
                    align-items: center; 
                    gap: 8px; 
                    margin-bottom: 8px; 
                }}
                .prompt-repo-header label {{ font-weight: 600; font-size: 13px; }}
                .prompt-repo-row {{ 
                    display: flex; 
                    align-items: center; 
                    gap: 6px; 
                    margin-bottom: 6px; 
                    flex-wrap: wrap; 
                }}
                .prompt-repo-row select {{ 
                    min-width: 150px; 
                    max-width: 200px;
                    background: var(--btn-bg);
                    color: var(--text-color);
                    border: 1px solid var(--border);
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-size: 12px;
                    font-family: 'Segoe UI', sans-serif;
                }}
                .prompt-repo-row select option {{
                    background: var(--btn-bg);
                    color: var(--text-color);
                }}
                .prompt-repo-row input[type="text"] {{ 
                    background: var(--btn-bg); 
                    color: var(--text-color);
                    border: 1px solid var(--border); 
                    border-radius: 6px; 
                    padding: 6px 10px; 
                    font-size: 12px;
                    font-family: 'Segoe UI', sans-serif; 
                    min-width: 120px; 
                    outline: none; 
                }}
                .prompt-repo-row input[type="checkbox"] {{ 
                    width: 18px; 
                    height: 18px; 
                    cursor: pointer; 
                    accent-color: #4a9eff; 
                }}
                .prompt-label {{ 
                    font-weight: 500; 
                    font-size: 12px; 
                    min-width: 85px; 
                    flex-shrink: 0; 
                }}
                .prompt-textarea {{ 
                    flex: 1; 
                    height: 80px; 
                    min-height: 80px; 
                    max-height: 120px; 
                    background: var(--btn-bg);
                    color: var(--text-color); 
                    border: 1px solid var(--border); 
                    border-radius: 6px; 
                    padding: 8px 10px;
                    font-size: 12px; 
                    font-family: 'Segoe UI', sans-serif; 
                    resize: none; 
                    outline: none;
                    overflow-y: auto; 
                    line-height: 1.4; 
                }}
                .prompt-textarea:focus {{ border-color: #4a9eff; }}
                .prompt-btn {{ 
                    padding: 6px 12px; 
                    font-size: 12px; 
                    height: 32px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 6px;
                    cursor: pointer;
                    border: 1px solid;
                }}
                .prompt-btn.add {{ background: #28a745; border-color: #218838; color: white; }}
                .prompt-btn.delete {{ background: #dc3545; border-color: #c82333; color: white; }}
                .prompt-btn.save {{ background: #4a9eff; border-color: #3a8eef; color: white; }}
                .prompt-btn:hover {{ opacity: 0.9; }}
                
                * {{ -webkit-app-region: no-drag !important; }}
            </style>
        </head>
        <body>
            <div class="main-nav">
                <!-- Row 1: LLM buttons + Settings + Pin + Close -->
                <div class="row-1">
                    <div class="gpt-group">{llm_buttons_html}</div>
                    <div class="utility-group">
                        <button class="util-btn" onclick="toggleSettings()" title="Settings">⚙</button>
                        <button class="util-btn" id="pin-btn" onclick="togglePin()" title="Pin Sidebar">📌</button>
                        <button class="util-btn danger" onclick="window.pywebview.api.exit_all()" title="Close">✕</button>
                    </div>
                </div>
                <!-- Row 2: Quick Prompts + Inject -->
                <div class="row-2">
                    <div class="prompt-group">
                        <select class="prompt-select" id="quick-prompt-select" onchange="selectPrompt(this.value)">{prompt_options_html}</select>
                        <button class="inject-btn" onclick="insertSelectedPrompt()" title="Insert Prompt">▶</button>
                    </div>
                </div>
            </div>
            
            <div id="settings-overlay">
                <!-- Monitor setting -->
                <div class="settings-row">
                    <label class="settings-label">Monitor:</label>
                    <select id="monitor-select" class="settings-select" onchange="selectMonitor(this.value)">{monitor_options_html}</select>
                </div>
                <!-- Side setting -->
                <div class="settings-row">
                    <label class="settings-label">Side:</label>
                    <select id="side-select" class="settings-select" onchange="setSidebarSide(this.value)">
                        <option value="left" {side_left_selected}>Left</option>
                        <option value="right" {side_right_selected}>Right</option>
                    </select>
                </div>
                <!-- Zoom setting -->
                <div class="settings-row">
                    <label class="settings-label">Zoom:</label>
                    <div class="zoom-control">
                        <button class="font-btn" onclick="adjustFont(-10)">−</button>
                        <span id="font-val">{self.current_font_size}%</span>
                        <button class="font-btn" onclick="adjustFont(10)">+</button>
                    </div>
                </div>
                <!-- Dark mode toggle with label -->
                <div class="settings-row">
                    <label class="settings-label">UI Design:</label>
                    <button class="util-btn mode-btn" onclick="toggleMode()" title="Light/Dark Mode">🌓</button>
                </div>
                <!-- LLM 1 -->
                <div class="settings-row">
                    <label class="settings-label">LLM 1:</label>
                    <select class="settings-select" onchange="changeLLM(0, this.value)">{llm_options_html[0]}</select>
                </div>
                <!-- LLM 2 -->
                <div class="settings-row">
                    <label class="settings-label">LLM 2:</label>
                    <select class="settings-select" onchange="changeLLM(1, this.value)">{llm_options_html[1]}</select>
                </div>
                <!-- LLM 3 -->
                <div class="settings-row">
                    <label class="settings-label">LLM 3:</label>
                    <select class="settings-select" onchange="changeLLM(2, this.value)">{llm_options_html[2]}</select>
                </div>
                <!-- Keep Chat -->
                <div class="settings-row">
                    <label class="settings-label">Keep Chat:</label>
                    <select class="settings-select" onchange="setRemainInChat(this.value)">
                        <option value="0" {"selected" if self.remain_in_chat == 0 else ""}>Off</option>
                        <option value="10" {"selected" if self.remain_in_chat == 10 else ""}>10 Min</option>
                        <option value="30" {"selected" if self.remain_in_chat == 30 else ""}>30 Min</option>
                    </select>
                </div>
                <!-- Prompt Repository -->
                <div class="prompt-repository">
                    <div class="prompt-repo-header"><label>📝 Quick Prompt Repository</label></div>
                    <div class="prompt-repo-row">
                        <select id="prompt-repo-select" onchange="loadPromptDetails(this.value)">{all_prompts_options_html}</select>
                        <label style="font-size:11px; margin-left:8px;"><input type="checkbox" id="prompt-fast-access" onchange="toggleFastAccess()"> Fast Access</label>
                    </div>
                    <div class="prompt-repo-row" style="margin-top: 8px;">
                        <label class="prompt-label">Quick Prompt:</label>
                        <input type="text" id="prompt-name-input" placeholder="Enter name..." maxlength="150" style="flex:1; max-width: 220px;">
                        <button class="prompt-btn delete" onclick="deleteSelectedPrompt()">🗑 Delete</button>
                        <button class="prompt-btn add" onclick="addNewPrompt()">+ Add</button>
                        <button class="prompt-btn save" onclick="savePromptChanges()">💾 Save</button>
                    </div>
                    <div class="prompt-repo-row" style="margin-top: 8px; align-items: flex-start;">
                        <label class="prompt-label" style="padding-top: 6px;">Full Prompt:</label>
                        <textarea id="prompt-content-input" class="prompt-textarea" placeholder="Add full prompt here..." maxlength="2000" oninput="autoResizeTextarea(this)"></textarea>
                    </div>
                </div>
            </div>
            <script>
                document.addEventListener('mousedown', function(e) {{
                    if (window.pywebview && window.pywebview.api.bring_nav_to_front) window.pywebview.api.bring_nav_to_front();
                }});
                function toggleSettings() {{
                    const overlay = document.getElementById('settings-overlay');
                    const isCurrentlyOpen = overlay.classList.contains('open');
                    
                    if (isCurrentlyOpen) {{
                        // Close settings
                        overlay.classList.remove('open');
                        if (window.pywebview && window.pywebview.api.expand_nav) window.pywebview.api.expand_nav(false);
                    }} else {{
                        // Open settings
                        overlay.classList.add('open'); 
                        if (window.pywebview && window.pywebview.api.expand_nav) window.pywebview.api.expand_nav(true);
                        // Refresh monitor list when settings are opened
                        if (window.pywebview && window.pywebview.api.refresh_monitors) {{
                            window.pywebview.api.refresh_monitors().then(monitors => {{
                                const select = document.getElementById('monitor-select');
                                if (select && monitors) {{
                                    select.innerHTML = '';
                                    monitors.forEach(mon => {{
                                        const option = document.createElement('option');
                                        option.value = mon.index;
                                        option.textContent = mon.name + ' (' + mon.resolution + ')';
                                        if (mon.selected) option.selected = true;
                                        select.appendChild(option);
                                    }});
                                }}
                            }});
                        }}
                    }}
                }}
                function adjustFont(delta) {{
                    let current = parseInt(document.getElementById('font-val').innerText);
                    window.pywebview.api.set_font_size(current + delta).then(res => {{ document.getElementById('font-val').innerText = res + '%'; }});
                }}
                function toggleMode() {{ 
                    const root = document.documentElement;
                    const isLight = root.style.getPropertyValue('--bg-color') === '#f4f4f4';
                    if (isLight) {{
                        // Switch to dark mode
                        root.style.setProperty('--bg-color', '#1e1e1e');
                        root.style.setProperty('--text-color', '#d4d4d4');
                        root.style.setProperty('--btn-bg', '#2d2d2d');
                        root.style.setProperty('--border', '#444');
                        root.style.setProperty('--hover-bg', '#3a3a3a');
                    }} else {{
                        // Switch to light mode
                        root.style.setProperty('--bg-color', '#f4f4f4');
                        root.style.setProperty('--text-color', '#1a1a1a');
                        root.style.setProperty('--btn-bg', '#e0e0e0');
                        root.style.setProperty('--border', '#ccc');
                        root.style.setProperty('--hover-bg', '#d0d0d0');
                    }}
                }}
                function togglePin() {{
                    window.pywebview.api.toggle_pin().then(isPinned => {{
                        const btn = document.getElementById('pin-btn');
                        if (isPinned) {{ 
                            btn.classList.add('active');
                            btn.title = 'Unpin Sidebar'; 
                        }} else {{ 
                            btn.classList.remove('active');
                            btn.title = 'Pin Sidebar'; 
                        }}
                    }});
                }}
                function changeApp(url, el, slot) {{
                    document.querySelectorAll('.gpt-btn').forEach(btn => btn.classList.remove('active'));
                    el.classList.add('active');
                    window.pywebview.api.set_active_llm(slot);
                    window.pywebview.api.switch_to_llm(slot);
                }}
                function setRemainInChat(minutes) {{ window.pywebview.api.set_remain_in_chat(parseInt(minutes)); }}
                function selectMonitor(index) {{ window.pywebview.api.change_monitor(parseInt(index)); }}
                function setSidebarSide(side) {{ window.pywebview.api.set_sidebar_side(side); }}
                function changeLLM(slot, llmKey) {{ window.pywebview.api.change_llm(slot, llmKey); }}
                
                // Quick Prompt selection - simplified and consistent behavior
                let selectedPromptIndex = -1;
                let repoSelectedIndex = -1;
                
                // Called when user selects a prompt from dropdown - just stores the selection
                function selectPrompt(index) {{ 
                    selectedPromptIndex = parseInt(index);
                    console.log('Prompt selected: ' + selectedPromptIndex);
                }}
                
                // Called when user clicks the inject button - injects the selected prompt
                function insertSelectedPrompt() {{
                    const selectElement = document.getElementById('quick-prompt-select');
                    const currentIndex = parseInt(selectElement.value);
                    
                    console.log('Insert clicked, index: ' + currentIndex);
                    
                    if (currentIndex < 0) {{
                        console.log('No prompt selected');
                        return;
                    }}
                    
                    window.pywebview.api.get_prompts().then(prompts => {{
                        if (currentIndex < prompts.length) {{
                            const promptContent = prompts[currentIndex].content;
                            console.log('Injecting prompt: ' + prompts[currentIndex].name);
                            
                            window.pywebview.api.inject_prompt(promptContent).then(success => {{
                                console.log('Injection result: ' + success);
                                // Keep the selection after injection - don't reset
                                // User can inject the same prompt multiple times if needed
                            }});
                        }}
                    }});
                }}
                function loadPromptDetails(index) {{
                    repoSelectedIndex = parseInt(index);
                    const textarea = document.getElementById('prompt-content-input');
                    if (repoSelectedIndex < 0) {{
                        document.getElementById('prompt-name-input').value = '';
                        textarea.value = 'Add full prompt here...';
                        document.getElementById('prompt-fast-access').checked = false;
                        return;
                    }}
                    window.pywebview.api.get_prompts().then(prompts => {{
                        if (repoSelectedIndex < prompts.length) {{
                            const prompt = prompts[repoSelectedIndex];
                            document.getElementById('prompt-name-input').value = prompt.name;
                            textarea.value = prompt.content;
                            document.getElementById('prompt-fast-access').checked = prompt.fast_access !== false;
                        }}
                    }});
                }}
                function toggleFastAccess() {{
                    if (repoSelectedIndex < 0) return;
                    window.pywebview.api.toggle_prompt_fast_access(repoSelectedIndex).then(newValue => {{ refreshPromptDropdowns(); }});
                }}
                function addNewPrompt() {{
                    const name = document.getElementById('prompt-name-input').value.trim();
                    let content = document.getElementById('prompt-content-input').value.trim();
                    const fastAccess = document.getElementById('prompt-fast-access').checked;
                    if (content === 'Add full prompt here...') content = '';
                    if (!name || !content) {{ alert('Please enter both a name and content for the prompt.'); return; }}
                    window.pywebview.api.add_prompt(name, content, fastAccess).then(success => {{
                        if (success) {{
                            document.getElementById('prompt-name-input').value = '';
                            document.getElementById('prompt-content-input').value = 'Add full prompt here...';
                            document.getElementById('prompt-fast-access').checked = true;
                            document.getElementById('prompt-repo-select').selectedIndex = 0;
                            repoSelectedIndex = -1;
                            refreshPromptDropdowns();
                        }}
                    }});
                }}
                function savePromptChanges() {{
                    if (repoSelectedIndex < 0) {{ alert('Please select a prompt to save changes.'); return; }}
                    const name = document.getElementById('prompt-name-input').value.trim();
                    let content = document.getElementById('prompt-content-input').value.trim();
                    const fastAccess = document.getElementById('prompt-fast-access').checked;
                    if (content === 'Add full prompt here...') content = '';
                    if (!name || !content) {{ alert('Please enter both a name and content for the prompt.'); return; }}
                    window.pywebview.api.update_prompt(repoSelectedIndex, name, content, fastAccess).then(success => {{
                        if (success) refreshPromptDropdowns();
                    }});
                }}
                function deleteSelectedPrompt() {{
                    if (repoSelectedIndex < 0) {{ alert('Please select a prompt to delete.'); return; }}
                    if (confirm('Are you sure you want to delete this prompt?')) {{
                        window.pywebview.api.delete_prompt(repoSelectedIndex).then(success => {{
                            if (success) {{
                                document.getElementById('prompt-name-input').value = '';
                                document.getElementById('prompt-content-input').value = 'Add full prompt here...';
                                document.getElementById('prompt-fast-access').checked = false;
                                document.getElementById('prompt-repo-select').selectedIndex = 0;
                                repoSelectedIndex = -1;
                                refreshPromptDropdowns();
                            }}
                        }});
                    }}
                }}
                function refreshPromptDropdowns() {{
                    // Store current selection before refresh
                    const quickSelect = document.getElementById('quick-prompt-select');
                    const currentQuickValue = quickSelect ? quickSelect.value : '-1';
                    
                    window.pywebview.api.get_prompts().then(prompts => {{
                        let quickOptions = '<option value="-1">Quick Prompts...</option>';
                        prompts.forEach((p, i) => {{ if (p.fast_access !== false) quickOptions += '<option value="' + i + '">' + escapeHtml(p.name) + '</option>'; }});
                        document.getElementById('quick-prompt-select').innerHTML = quickOptions;
                        
                        // Restore selection if it still exists
                        if (currentQuickValue !== '-1') {{
                            const quickSelectNew = document.getElementById('quick-prompt-select');
                            if (quickSelectNew.querySelector('option[value="' + currentQuickValue + '"]')) {{
                                quickSelectNew.value = currentQuickValue;
                            }}
                        }}
                        
                        let repoOptions = '<option value="-1">-- Select Prompt --</option>';
                        prompts.forEach((p, i) => {{ repoOptions += '<option value="' + i + '">' + escapeHtml(p.name) + '</option>'; }});
                        document.getElementById('prompt-repo-select').innerHTML = repoOptions;
                    }});
                }}
                function escapeHtml(text) {{ const div = document.createElement('div'); div.textContent = text; return div.innerHTML; }}
                function autoResizeTextarea(textarea) {{
                    textarea.style.height = 'auto';
                    const newHeight = Math.min(Math.max(textarea.scrollHeight, 80), 120);
                    textarea.style.height = newHeight + 'px';
                }}
                const defaultPromptText = 'Add full prompt here...';
                document.addEventListener('DOMContentLoaded', function() {{
                    const textarea = document.getElementById('prompt-content-input');
                    if (textarea) {{
                        textarea.addEventListener('focus', function() {{ if (this.value === defaultPromptText) this.value = ''; }});
                        textarea.addEventListener('blur', function() {{ if (this.value.trim() === '') this.value = defaultPromptText; }});
                    }}
                }});
            </script>
        </body>
        </html>
        """

        try:
            try:
                sf = user32.GetDpiForSystem() / 96.0
            except:
                sf = 1.0
            logger.info(f"DPI-Skalierungsfaktor: {sf}")
            
            self.nav_window = webview.create_window(
                self.title_nav, html=nav_html,
                width=int(self.win_width_px / sf), height=int(self.NAV_HEIGHT / sf),
                x=int(self.park_x_px / sf), y=0,
                frameless=True, on_top=True, transparent=True, easy_drag=False
            )
            logger.info("Navigation-Fenster erstellt")
            
            browser_height = self.monitor_height - self.NAV_HEIGHT
            initial_url = AVAILABLE_LLMS[self.selected_llms[0]]['url']
            
            self.browser_window = webview.create_window(
                self.title_browser, url=initial_url,
                width=int(self.win_width_px / sf), height=int(browser_height / sf),
                x=int(self.park_x_px / sf), y=int(self.NAV_HEIGHT / sf),
                frameless=True, on_top=True, easy_drag=False
            )
            logger.info(f"Browser-Fenster erstellt (Downloads: {self.download_folder})")
            
            self.nav_window.expose(
                self.load_url, self.set_font_size, self.exit_all, self.change_monitor,
                self.get_monitor_list, self.change_llm, self.get_llm_list, self.set_active_llm,
                self.get_prompts, self.get_fast_access_prompts, self.inject_prompt, self.add_prompt,
                self.update_prompt, self.delete_prompt, self.toggle_prompt_fast_access,
                self.expand_nav, self.bring_nav_to_front, self.toggle_pin, self.switch_to_llm,
                self.set_remain_in_chat, self.get_remain_in_chat,
                self.set_sidebar_side, self.get_sidebar_side,
                self.refresh_monitors
            )
            
            threading.Thread(target=self._mouse_monitor_thread, daemon=True).start()
            
            logger.info("Starte WebView...")
            # Enable downloads - files will be saved to default browser download location
            # or user will be prompted to choose location
            webview.settings['ALLOW_DOWNLOADS'] = True
            webview.start(private_mode=False, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
        except Exception as e:
            logger.critical(f"Kritischer Fehler beim Starten der Anwendung: {e}", exc_info=True)
            sys.exit(1)


def check_single_instance():
    MUTEX_NAME = "Global\\AI_Slidebar_SingleInstance_Mutex"
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    last_error = kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183
    if last_error == ERROR_ALREADY_EXISTS:
        ctypes.windll.user32.MessageBoxW(None, "AI Slidebar is already running.\n\nPlease check your taskbar or system tray.", "AI Slidebar", 0x40 | 0x0)
        sys.exit(0)
    return mutex


if __name__ == "__main__":
    _instance_mutex = check_single_instance()
    try:
        logger.info("=" * 60)
        logger.info("AI Slidebar System wird gestartet...")
        logger.info("=" * 60)
        app = AISidebarSystem()
        app.run()
    except KeyboardInterrupt:
        logger.info("Anwendung durch Benutzer unterbrochen (Strg+C)")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Kritischer Fehler beim Start: {e}", exc_info=True)
        sys.exit(1)
