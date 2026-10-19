import json
import os
import threading
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal

APP_DIR = Path(os.environ.get("APPDATA", ".")) / "ProcessX"
APP_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = APP_DIR / "settings.json"
RULES_FILE = APP_DIR / "rules.json"

DEFAULT_SETTINGS = {
    "language": "vi",
    "run_on_startup": False,
    "minimize_to_tray": True,
    "refresh_interval_ms": 2500,
}

_PRIORITY_CLASSES = {
    "Idle": 0x00000040,          # IDLE_PRIORITY_CLASS
    "Below Normal": 0x00004000,  # BELOW_NORMAL_PRIORITY_CLASS
    "Normal": 0x00000020,        # NORMAL_PRIORITY_CLASS
    "Above Normal": 0x00008000,  # ABOVE_NORMAL_PRIORITY_CLASS
    "High": 0x00000080,          # HIGH_PRIORITY_CLASS
    "Realtime": 0x00000100,      # REALTIME_PRIORITY_CLASS
}

PRIORITY_MAP = dict(_PRIORITY_CLASSES)
PRIORITY_REVERSE = {v: k for k, v in PRIORITY_MAP.items()}

IO_PRIORITY_NAMES = ["Very Low", "Low", "Normal", "High"]
IO_PRIORITY_MAP = {0: "Very Low", 1: "Low", 2: "Normal", 3: "High"}

CRITICAL_SYSTEM_PROCESSES = {
    "explorer.exe",
    "csrss.exe",
    "smss.exe",
    "winlogon.exe",
    "dwm.exe",
    "services.exe",
    "lsass.exe",
    "wininit.exe",
    "system",
    "system idle process",
    "registry",
    "fontdrvhost.exe",
    "svchost.exe",
    "sihost.exe",
    "taskhostw.exe",
    "ctfmon.exe",
    "securityhealthservice.exe",
    "searchindexer.exe",
    "runtimebroker.exe",
    "shellexperiencehost.exe",
    "conhost.exe",
    "audiodg.exe",
    "spoolsv.exe",
}

TRANSLATIONS = {
    "vi": {
        "app_title": "ProcessX",
        "search_placeholder": "Tìm kiếm tiến trình (tên hoặc PID)...",
        "tooltip_minimize": "Thu nhỏ",
        "tooltip_maximize": "Phóng to / Khôi phục",
        "tooltip_close": "Đóng",
        "lang_toggle_en": "EN",
        "lang_toggle_vi": "VI",
        "btn_profiles": "Profiles",
        "btn_add_profile": "+ Thêm Profile",
        "btn_settings": "Cài đặt",
        "btn_refresh": "Làm mới",
        "btn_startup": "Khởi động cùng Windows",
        "btn_startup_enabled": "Đã bật khởi động",
        "tooltip_profiles": "Quản lý danh sách cấu hình rules",
        "tooltip_add_profile": "Thêm quy tắc mới cho ứng dụng / game",
        "tooltip_settings": "Cấu hình tùy chọn hệ thống & giao diện",
        "tooltip_refresh": "Cập nhật lại danh sách tiến trình",
        "tooltip_startup": "Tự động chạy ProcessX khi đăng nhập Windows",
        "metric_profiles": "Profiles:",
        "metric_procs": "Tiến trình:",
        "watcher_active": "Watcher Active",
        "watcher_idle": "Watcher Idle",
        "settings_title": "Cài đặt hệ thống - ProcessX v2.0",
        "settings_sec_general": "CÀI ĐẶT CHUNG",
        "settings_startup_label": "Khởi động cùng Windows",
        "settings_startup_desc": "Tự động khởi chạy ProcessX khi đăng nhập vào Windows.",
        "settings_tray_label": "Thu xuống khay hệ thống khi đóng",
        "settings_tray_desc": "Đóng cửa sổ sẽ ẩn ứng dụng xuống khay hệ thống để tiếp tục áp dụng quy tắc.",
        "settings_lang_label": "Ngôn ngữ hiển thị",
        "settings_lang_desc": "Chọn ngôn ngữ giao diện (Tiếng Việt / English).",
        "settings_btn_close": "Đóng",
        "settings_status_saved": "Đã lưu cài đặt",
        "col_proc_name": "TÊN TIẾN TRÌNH",
        "col_pid": "PID",
        "col_cpu": "CPU",
        "col_ram": "RAM",
        "col_cpu_pri": "ƯU TIÊN CPU",
        "col_io_pri": "ƯU TIÊN I/O",
        "col_cpu_sets": "CPU SETS",
        "col_profile": "PROFILE",
        "rule_active": "Active",
        "rule_none": "-",
        "menu_edit_profile": "Sửa / Tạo Profile: {name}",
        "menu_open_explorer": "Mở vị trí file trong Explorer",
        "menu_copy_path": "Sao chép đường dẫn EXE",
        "menu_trim_mem": "Dọn dẹp bộ nhớ (Trim Working Set)",
        "menu_kill_proc": "Kết thúc tiến trình",
        "menu_refresh": "Làm mới danh sách",
        "confirm_kill_title": "Xác nhận kết thúc tiến trình",
        "confirm_kill_msg": "Bạn có chắc muốn kết thúc {target}?",
        "error_title": "Lỗi",
        "error_open_folder": "Không thể mở thư mục:\n{err}",
        "error_kill_proc": "Không thể kết thúc tiến trình:\n{err}",
        "status_watcher_running": "Watcher đang chạy: tự động áp dụng quy tắc khi tiến trình khởi chạy.",
        "status_startup_added_task": "Đã thêm ProcessX vào khởi động cùng Windows (Task Scheduler).",
        "status_startup_added_reg": "Đã thêm ProcessX vào khởi động cùng Windows (Registry Run).",
        "status_startup_failed": "Không thể thiết lập khởi động cùng Windows: {err}",
        "tray_open": "Mở ProcessX v2.0",
        "tray_profiles": "Profiles...",
        "tray_refresh": "Làm mới",
        "tray_quit": "Thoát",
        "add_dlg_title": "Thêm Profile Mới",
        "add_dlg_label": "Tên EXE (hoặc chọn tệp thực thi):",
        "add_dlg_placeholder": "VD: game.exe",
        "add_dlg_browse": "Chọn tệp...",
        "add_dlg_path_prefix": "Đường dẫn: {path}",
        "add_dlg_cancel": "Hủy",
        "add_dlg_continue": "Tiếp tục",
        "add_dlg_file_filter": "Tệp thực thi (*.exe);;Tất cả tệp (*.*)",
        "add_dlg_file_dialog_title": "Chọn tệp thực thi",
        "add_dlg_err_empty": "Vui lòng nhập tên file EXE.",
        "pm_title": "Quản lý Profiles - ProcessX v2.0",
        "pm_search_placeholder": "Lọc profile theo tên...",
        "pm_col_exe": "TÊN EXE",
        "pm_col_cpu_pri": "ƯU TIÊN CPU",
        "pm_col_io_pri": "ƯU TIÊN I/O",
        "pm_col_cpu_sets": "CPU SETS",
        "pm_col_power_plan": "POWER PLAN",
        "pm_col_status": "TRẠNG THÁI",
        "pm_status_running": "Đang chạy",
        "pm_status_stopped": "Chưa chạy",
        "pm_btn_import": "Nhập cấu hình",
        "pm_btn_export": "Xuất cấu hình",
        "pm_btn_delete": "Xóa Profile",
        "pm_btn_edit": "Chỉnh sửa...",
        "pm_btn_close": "Đóng",
        "pm_confirm_delete_title": "Xác nhận xóa",
        "pm_confirm_delete_msg": "Bạn có chắc muốn xóa Profile cho '{exe}'?",
        "pm_import_success_title": "Thành công",
        "pm_import_success_msg": "Đã nhập thành công {count} quy tắc.",
        "pm_export_success_title": "Thành công",
        "pm_export_success_msg": "Đã xuất {count} cấu hình rules ra file:\n{path}",
        "pm_empty_no_profiles": "Chưa có profile nào. Nhấn '+ Thêm Profile' để tạo cấu hình mới.",
        "pm_empty_not_found": "Không tìm thấy profile phù hợp.",
        "ed_title": "Cấu hình Profile: {name}",
        "ed_path_label": "Đường dẫn:",
        "ed_pid_label": "PID:",
        "ed_sec_cpu_pri": "1. ƯU TIÊN CPU",
        "ed_sec_io_pri": "2. ƯU TIÊN I/O",
        "ed_sec_mem_pri": "3. ƯU TIÊN BỘ NHỚ",
        "ed_sec_cpu_sets": "4. CPU SETS / CPU AFFINITY ({core_count} Luồng)",
        "ed_btn_all_cores": "Tất cả",
        "ed_btn_physical_cores": "Cores thực",
        "ed_btn_p_cores": "P-Cores",
        "ed_btn_e_cores": "E-Cores",
        "val_none": "Không",
        "ed_btn_clear": "Không",
        "ed_sec_power_plan": "5. GÓI ĐIỆN NĂNG",
        "ed_power_plan_default": "Mặc định hệ thống (Không đổi)",
        "ed_btn_reset_defaults": "Đặt lại mặc định",
        "ed_btn_delete": "Xóa Profile",
        "ed_btn_cancel": "Hủy",
        "ed_btn_save": "Lưu Profile",
        "ed_confirm_delete_title": "Xác nhận xóa",
        "ed_confirm_delete_msg": "Bạn có chắc muốn xóa Profile của '{name}'?",
        "ed_err_no_cores": "Vui lòng chọn ít nhất 1 CPU Core.",
        "ed_status_saved_rule": "Đã lưu Profile: tự động áp dụng khi tiến trình khởi chạy.",
        "ed_status_saved_and_applied": "Đã lưu Profile & áp dụng cho {count} tiến trình đang chạy.",
        "ed_status_applied_temp": "Đã áp dụng cho {count} tiến trình đang chạy (Điều chỉnh tạm thời).",
        "ed_status_no_instances": "Không tìm thấy tiến trình đang chạy để áp dụng tạm thời.",
        "ed_status_reset": "Đã đặt lại các cấu hình về giá trị mặc định.",
        "pri_none": "Không",
        "pri_idle": "Nghỉ",
        "pri_below_normal": "Dưới chuẩn",
        "pri_normal": "Bình thường",
        "pri_above_normal": "Trên chuẩn",
        "pri_high": "Cao",
        "pri_realtime": "Thời gian thực",
        "io_none": "Không",
        "io_very_low": "Rất thấp",
        "io_low": "Thấp",
        "io_normal": "Bình thường",
        "io_high": "Cao",
        "mem_none": "Không",
        "mem_very_low": "Rất thấp (1)",
        "mem_low": "Thấp (2)",
        "mem_medium": "Trung bình (3)",
        "mem_normal": "Bình thường (5)",
        "aff_none": "Không",
    },
    "en": {
        "app_title": "ProcessX",
        "search_placeholder": "Search processes (name or PID)...",
        "tooltip_minimize": "Minimize",
        "tooltip_maximize": "Maximize / Restore",
        "tooltip_close": "Close",
        "lang_toggle_en": "EN",
        "lang_toggle_vi": "VI",
        "btn_profiles": "Profiles",
        "btn_add_profile": "+ Add Profile",
        "btn_settings": "Settings",
        "btn_refresh": "Refresh",
        "btn_startup": "Run on Startup",
        "btn_startup_enabled": "Startup Enabled",
        "tooltip_profiles": "Manage rule configurations and profiles",
        "tooltip_add_profile": "Add new rule for an app or game",
        "tooltip_settings": "Configure system settings & preferences",
        "tooltip_refresh": "Refresh system process list",
        "tooltip_startup": "Launch ProcessX automatically on Windows login",
        "metric_profiles": "Profiles:",
        "metric_procs": "Processes:",
        "watcher_active": "Watcher Active",
        "watcher_idle": "Watcher Idle",
        "settings_title": "System Settings - ProcessX v2.0",
        "settings_sec_general": "GENERAL SETTINGS",
        "settings_startup_label": "Run on Windows Startup",
        "settings_startup_desc": "Launch ProcessX automatically when logging into Windows.",
        "settings_tray_label": "Minimize to System Tray on Close",
        "settings_tray_desc": "Closing window minimizes to tray to keep rules and watcher active.",
        "settings_lang_label": "Display Language",
        "settings_lang_desc": "Select user interface language (Tiếng Việt / English).",
        "settings_btn_close": "Close",
        "settings_status_saved": "Settings saved",
        "col_proc_name": "PROCESS NAME",
        "col_pid": "PID",
        "col_cpu": "CPU",
        "col_ram": "RAM",
        "col_cpu_pri": "CPU PRIORITY",
        "col_io_pri": "I/O PRIORITY",
        "col_cpu_sets": "CPU SETS",
        "col_profile": "PROFILE",
        "rule_active": "Active",
        "rule_none": "-",
        "menu_edit_profile": "Edit / Create Profile: {name}",
        "menu_open_explorer": "Open File Location in Explorer",
        "menu_copy_path": "Copy EXE Path",
        "menu_trim_mem": "Trim Working Set (Clean RAM)",
        "menu_kill_proc": "End Process",
        "menu_refresh": "Refresh List",
        "confirm_kill_title": "Confirm End Process",
        "confirm_kill_msg": "Are you sure you want to terminate {target}?",
        "error_title": "Error",
        "error_open_folder": "Failed to open directory:\n{err}",
        "error_kill_proc": "Failed to terminate process:\n{err}",
        "status_watcher_running": "Watcher running: rules auto-applied when process starts.",
        "status_startup_added_task": "Added ProcessX to Windows Startup (Task Scheduler).",
        "status_startup_added_reg": "Added ProcessX to Windows Startup (Registry Run).",
        "status_startup_failed": "Failed to configure Windows startup: {err}",
        "tray_open": "Open ProcessX v2.0",
        "tray_profiles": "Profiles...",
        "tray_refresh": "Refresh",
        "tray_quit": "Quit",
        "add_dlg_title": "Add New Profile",
        "add_dlg_label": "EXE Name (or browse executable):",
        "add_dlg_placeholder": "e.g., game.exe",
        "add_dlg_browse": "Browse...",
        "add_dlg_path_prefix": "Path: {path}",
        "add_dlg_cancel": "Cancel",
        "add_dlg_continue": "Continue",
        "add_dlg_file_filter": "Executable Files (*.exe);;All Files (*.*)",
        "add_dlg_file_dialog_title": "Select Executable File",
        "add_dlg_err_empty": "Please enter an EXE file name.",
        "pm_title": "Manage Profiles - ProcessX v2.0",
        "pm_search_placeholder": "Filter profiles by name...",
        "pm_col_exe": "EXE NAME",
        "pm_col_cpu_pri": "CPU PRIORITY",
        "pm_col_io_pri": "I/O PRIORITY",
        "pm_col_cpu_sets": "CPU SETS",
        "pm_col_power_plan": "POWER PLAN",
        "pm_col_status": "STATUS",
        "pm_status_running": "Running",
        "pm_status_stopped": "Stopped",
        "pm_btn_import": "Import Profiles",
        "pm_btn_export": "Export Profiles",
        "pm_btn_delete": "Delete Profile",
        "pm_btn_edit": "Edit Profile...",
        "pm_btn_close": "Close",
        "pm_confirm_delete_title": "Confirm Delete",
        "pm_confirm_delete_msg": "Are you sure you want to delete profile for '{exe}'?",
        "pm_import_success_title": "Success",
        "pm_import_success_msg": "Successfully imported {count} rules.",
        "pm_export_success_title": "Success",
        "pm_export_success_msg": "Exported {count} rules to file:\n{path}",
        "pm_empty_no_profiles": "No profiles added yet. Click '+ Add Profile' to create one.",
        "pm_empty_not_found": "No matching profiles found.",
        "ed_title": "Profile Configuration: {name}",
        "ed_path_label": "Path:",
        "ed_pid_label": "PID:",
        "ed_sec_cpu_pri": "1. CPU PRIORITY",
        "ed_sec_io_pri": "2. I/O PRIORITY",
        "ed_sec_mem_pri": "3. MEMORY PRIORITY",
        "ed_sec_cpu_sets": "4. CPU SETS / CPU AFFINITY ({core_count} Cores)",
        "ed_btn_all_cores": "All",
        "ed_btn_physical_cores": "Physical Only",
        "ed_btn_p_cores": "P-Cores",
        "ed_btn_e_cores": "E-Cores",
        "val_none": "None",
        "ed_btn_clear": "None",
        "ed_sec_power_plan": "5. POWER PLAN",
        "ed_power_plan_default": "System Default (Do Not Change)",
        "ed_btn_reset_defaults": "Reset to Defaults",
        "ed_btn_delete": "Delete Profile",
        "ed_btn_cancel": "Cancel",
        "ed_btn_save": "Save Profile",
        "ed_confirm_delete_title": "Confirm Delete",
        "ed_confirm_delete_msg": "Are you sure you want to delete the profile for '{name}'?",
        "ed_err_no_cores": "Please select at least 1 CPU Core.",
        "ed_status_saved_rule": "Saved Profile: will auto-apply when process starts.",
        "ed_status_saved_and_applied": "Saved Profile & applied to {count} running instance(s).",
        "ed_status_applied_temp": "Applied to {count} running instance(s) (Temporary adjustment).",
        "ed_status_no_instances": "No running instances found to apply temporary adjustment.",
        "ed_status_reset": "Reset configuration to system default values.",
        "pri_none": "None",
        "pri_idle": "Idle",
        "pri_below_normal": "Below Normal",
        "pri_normal": "Normal",
        "pri_above_normal": "Above Normal",
        "pri_high": "High",
        "pri_realtime": "Realtime",
        "io_none": "None",
        "io_very_low": "Very Low",
        "io_low": "Low",
        "io_normal": "Normal",
        "io_high": "High",
        "mem_none": "None",
        "mem_very_low": "Very Low (1)",
        "mem_low": "Low (2)",
        "mem_medium": "Medium (3)",
        "mem_normal": "Normal (5)",
        "aff_none": "None",
    }
}

_VALUE_TRANSLATION_MAP = {
    "Idle": "pri_idle",
    "Below Normal": "pri_below_normal",
    "Normal": "pri_normal",
    "Above Normal": "pri_above_normal",
    "High": "pri_high",
    "Realtime": "pri_realtime",
    "Very Low": "io_very_low",
    "Low": "io_low",
    "all": "ed_btn_all_cores",
}

_cfg_lock = threading.Lock()
_settings_cache = None


def load_settings() -> dict:
    global _settings_cache
    with _cfg_lock:
        if _settings_cache is not None:
            return dict(_settings_cache)
        settings = dict(DEFAULT_SETTINGS)
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    settings.update(data)
            except (json.JSONDecodeError, OSError):
                pass
        _settings_cache = settings
        return dict(_settings_cache)


def save_settings(settings: dict):
    global _settings_cache
    with _cfg_lock:
        _settings_cache = dict(settings)
        try:
            SETTINGS_FILE.write_text(json.dumps(_settings_cache, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def get_setting(key: str, default=None):
    return load_settings().get(key, DEFAULT_SETTINGS.get(key, default))


def set_setting(key: str, value):
    settings = load_settings()
    settings[key] = value
    save_settings(settings)


def load_rules() -> dict:
    if RULES_FILE.exists():
        try:
            data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            corrupt = RULES_FILE.with_suffix(".json.corrupt")
            try:
                os.replace(RULES_FILE, corrupt)
            except OSError:
                pass
    return {}


def save_rules(rules: dict):
    tmp_path = RULES_FILE.with_name(f"rules_{os.getpid()}_{threading.get_ident()}.tmp")
    try:
        tmp_path.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, RULES_FILE)
    except OSError:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def validate_rules(data) -> tuple[dict, list[str]]:
    if not isinstance(data, dict):
        raise ValueError("Rules data must be a dictionary")
    cleaned = {}
    warnings = []
    for exe, rule in data.items():
        if not isinstance(exe, str) or not exe.strip():
            warnings.append(f"Skipped invalid process target: {exe!r}")
            continue
        if not isinstance(rule, dict):
            warnings.append(f"Skipped non-dictionary rule for {exe}")
            continue

        clean = {}
        if "priority" in rule and rule["priority"] in PRIORITY_MAP:
            clean["priority"] = rule["priority"]
        if "io_priority" in rule:
            try:
                val = int(rule["io_priority"])
                if val in (0, 1, 2, 3):
                    clean["io_priority"] = val
            except (TypeError, ValueError):
                pass
        if "affinity" in rule:
            aff = rule["affinity"]
            if isinstance(aff, list) and all(isinstance(x, int) for x in aff):
                clean["affinity"] = aff
            elif aff is None or aff == "None":
                clean["affinity"] = None
        if "memory_priority" in rule:
            try:
                val = int(rule["memory_priority"])
                if val in (1, 2, 3, 5):
                    clean["memory_priority"] = val
            except (TypeError, ValueError):
                pass
        if "power_plan" in rule and isinstance(rule["power_plan"], str):
            clean["power_plan"] = rule["power_plan"].strip()
        if "ecoqos" in rule:
            clean["ecoqos"] = bool(rule["ecoqos"])
        if "exe_path" in rule and isinstance(rule["exe_path"], str):
            clean["exe_path"] = rule["exe_path"]

        clean["name"] = rule.get("name") or os.path.basename(clean.get("exe_path") or exe)
        if clean:
            cleaned[exe.lower()] = clean

    return cleaned, warnings


def import_rules_from_file(path: str | Path, current_rules: dict | None = None) -> tuple[dict, list[str]]:
    """Reads a JSON file from path, validates the rules, and merges them with current_rules."""
    p = Path(path)
    content = p.read_text(encoding="utf-8")
    data = json.loads(content)
    cleaned, warnings = validate_rules(data)
    merged = dict(current_rules) if current_rules is not None else {}
    merged.update(cleaned)
    return merged, warnings


def export_rules_to_file(path: str | Path, rules: dict) -> None:
    """Exports rules to a JSON file at path with 2-space indentation."""
    p = Path(path)
    p.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")



def is_critical_process(name: str = "", pid: int = None, exe_path: str = "") -> bool:
    if pid is not None and pid <= 4:
        return True
    target = (name or "").lower().strip()
    if target in CRITICAL_SYSTEM_PROCESSES:
        return True
    if exe_path:
        base = os.path.basename(exe_path).lower().strip()
        if base in CRITICAL_SYSTEM_PROCESSES:
            return True
        norm = exe_path.lower()
        system_root = (os.environ.get("SystemRoot") or os.environ.get("WINDIR") or "C:\\Windows").lower()
        sys32 = os.path.join(system_root, "system32")
        sysapps = os.path.join(system_root, "systemapps")
        if norm.startswith(sys32) or norm.startswith(sysapps) or r"\system32" in norm:
            for crit in CRITICAL_SYSTEM_PROCESSES:
                if norm.endswith(crit):
                    return True
    return False


class _I18n(QObject):
    language_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._lang = str(get_setting("language", "vi")).lower()
        if self._lang not in TRANSLATIONS:
            self._lang = "vi"

    @property
    def current_language(self) -> str:
        return self._lang

    def set_language(self, lang: str):
        target = lang.lower()
        if target in TRANSLATIONS and self._lang != target:
            self._lang = target
            set_setting("language", target)
            self.language_changed.emit(target)

    def tr(self, key: str, **kwargs) -> str:
        dict_lang = TRANSLATIONS.get(self._lang, TRANSLATIONS["vi"])
        text = dict_lang.get(key, TRANSLATIONS["vi"].get(key, key))
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text


I18N = _I18n()


def tr(key: str, **kwargs) -> str:
    return I18N.tr(key, **kwargs)


def translate_val(val: str, category: str = "") -> str:
    if not isinstance(val, str):
        return str(val) if val is not None else ""
    if category == "io":
        if val == "Normal":
            return tr("io_normal")
        if val == "High":
            return tr("io_high")
    key = _VALUE_TRANSLATION_MAP.get(val)
    return tr(key) if key else val
