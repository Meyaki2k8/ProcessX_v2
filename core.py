import atexit
import ctypes
import ctypes.wintypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import winreg
from collections import OrderedDict, defaultdict
from pathlib import Path
import psutil

from config import (
    APP_DIR,
    CRITICAL_SYSTEM_PROCESSES,
    IO_PRIORITY_MAP,
    PRIORITY_MAP,
    PRIORITY_REVERSE,
    get_setting,
    is_critical_process,
    load_rules,
    save_rules,
    set_setting,
    tr,
)

# Win32 Process Access Flags
PROCESS_TERMINATE = 0x0001
PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SET_LIMITED_INFORMATION = 0x2000
PROCESS_ALL_ACCESS = 0x1F0FFF

# Win32 Process Image Name Prototype & Core Libraries
_kernel32 = ctypes.windll.kernel32
_user32 = ctypes.windll.user32
_advapi32 = ctypes.windll.advapi32
_ntdll = ctypes.windll.ntdll
_psapi = getattr(ctypes.windll, "psapi", None)
_powrprof = getattr(ctypes.windll, "powrprof", None)
_dwmapi = getattr(ctypes.windll, "dwmapi", None)

# NT Process Information Classes
ProcessMemoryPriority = 0
ProcessPowerThrottling = 4
ProcessIoPriority = 33

# EcoQoS execution speed throttle mask
PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1

# DWM Blur & Window Attributes
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2

# Power Plan GUID regex
_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# Structures
class MEMORY_PRIORITY_INFORMATION(ctypes.Structure):
    _fields_ = [("MemoryPriority", ctypes.c_ulong)]


class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    _fields_ = [
        ("Version", ctypes.c_ulong),
        ("ControlMask", ctypes.c_ulong),
        ("StateMask", ctypes.c_ulong),
    ]


class DWM_MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


class WIN32_GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.wintypes.DWORD),
        ("Data2", ctypes.wintypes.WORD),
        ("Data3", ctypes.wintypes.WORD),
        ("Data4", ctypes.wintypes.BYTE * 8),
    ]

    def to_str(self) -> str:
        return str(uuid.UUID(bytes_le=bytes(self)))


# ── Full 64-bit ctypes prototypes to eliminate 0xC0000005 and handle leaks ──
_kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
_kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE

_kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
_kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE

_kernel32_err = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32_err.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
_kernel32_err.CreateMutexW.restype = ctypes.wintypes.HANDLE

_kernel32.GetCurrentProcess.argtypes = []
_kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE

_kernel32.GetLastError.argtypes = []
_kernel32.GetLastError.restype = ctypes.wintypes.DWORD

_kernel32.LocalFree.argtypes = [ctypes.c_void_p]
_kernel32.LocalFree.restype = ctypes.c_void_p

_kernel32.TerminateProcess.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.UINT]
_kernel32.TerminateProcess.restype = ctypes.wintypes.BOOL

_QueryFullProcessImageNameW = _kernel32.QueryFullProcessImageNameW
_QueryFullProcessImageNameW.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.wintypes.DWORD,
    ctypes.wintypes.LPWSTR,
    ctypes.POINTER(ctypes.wintypes.DWORD),
]
_QueryFullProcessImageNameW.restype = ctypes.wintypes.BOOL

if hasattr(_kernel32, "SetProcessDefaultCpuSets"):
    _kernel32.SetProcessDefaultCpuSets.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.wintypes.ULONG]
    _kernel32.SetProcessDefaultCpuSets.restype = ctypes.wintypes.BOOL

if hasattr(_kernel32, "GetProcessDefaultCpuSets"):
    _kernel32.GetProcessDefaultCpuSets.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.wintypes.ULONG,
        ctypes.POINTER(ctypes.wintypes.ULONG),
    ]
    _kernel32.GetProcessDefaultCpuSets.restype = ctypes.wintypes.BOOL

if hasattr(_kernel32, "GetSystemCpuSetInformation"):
    _kernel32.GetSystemCpuSetInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.wintypes.ULONG,
        ctypes.POINTER(ctypes.wintypes.ULONG),
        ctypes.wintypes.HANDLE,
        ctypes.wintypes.ULONG,
    ]
    _kernel32.GetSystemCpuSetInformation.restype = ctypes.wintypes.BOOL

if hasattr(_kernel32, "GetProcessInformation"):
    _kernel32.GetProcessInformation.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
    ]
    _kernel32.GetProcessInformation.restype = ctypes.wintypes.BOOL

if hasattr(_kernel32, "SetProcessInformation"):
    _kernel32.SetProcessInformation.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
    ]
    _kernel32.SetProcessInformation.restype = ctypes.wintypes.BOOL

_NtSIP = _ntdll.NtSetInformationProcess
_NtSIP.restype = ctypes.c_long
_NtSIP.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong]

_NtQIP = _ntdll.NtQueryInformationProcess
_NtQIP.restype = ctypes.c_long
_NtQIP.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]

_advapi32.OpenProcessToken.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.wintypes.DWORD,
    ctypes.POINTER(ctypes.wintypes.HANDLE),
]
_advapi32.OpenProcessToken.restype = ctypes.wintypes.BOOL

_advapi32.LookupPrivilegeValueW.argtypes = [
    ctypes.wintypes.LPCWSTR,
    ctypes.wintypes.LPCWSTR,
    ctypes.c_void_p,
]
_advapi32.LookupPrivilegeValueW.restype = ctypes.wintypes.BOOL

_advapi32.AdjustTokenPrivileges.argtypes = [
    ctypes.wintypes.HANDLE,
    ctypes.wintypes.BOOL,
    ctypes.c_void_p,
    ctypes.wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
_advapi32.AdjustTokenPrivileges.restype = ctypes.wintypes.BOOL

if hasattr(_advapi32, "GetTokenInformation"):
    _advapi32.GetTokenInformation.argtypes = [
        ctypes.wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
        ctypes.POINTER(ctypes.wintypes.DWORD),
    ]
    _advapi32.GetTokenInformation.restype = ctypes.wintypes.BOOL

if hasattr(_advapi32, "ConvertSidToStringSidW"):
    _advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    _advapi32.ConvertSidToStringSidW.restype = ctypes.wintypes.BOOL

if _psapi and hasattr(_psapi, "EmptyWorkingSet"):
    _psapi.EmptyWorkingSet.argtypes = [ctypes.wintypes.HANDLE]
    _psapi.EmptyWorkingSet.restype = ctypes.wintypes.BOOL

if hasattr(_user32, "FindWindowW"):
    _user32.FindWindowW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR]
    _user32.FindWindowW.restype = ctypes.wintypes.HWND

if hasattr(_user32, "ShowWindow"):
    _user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = ctypes.wintypes.BOOL

if hasattr(_user32, "SetForegroundWindow"):
    _user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
    _user32.SetForegroundWindow.restype = ctypes.wintypes.BOOL

if hasattr(_user32, "ReleaseCapture"):
    _user32.ReleaseCapture.argtypes = []
    _user32.ReleaseCapture.restype = ctypes.wintypes.BOOL

if hasattr(_user32, "SendMessageW"):
    _user32.SendMessageW.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.wintypes.UINT,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    _user32.SendMessageW.restype = ctypes.c_longlong

if hasattr(_user32, "RegisterWindowMessageW"):
    _user32.RegisterWindowMessageW.argtypes = [ctypes.wintypes.LPCWSTR]
    _user32.RegisterWindowMessageW.restype = ctypes.wintypes.UINT

if hasattr(_user32, "PostMessageW"):
    _user32.PostMessageW.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.wintypes.UINT,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    ]
    _user32.PostMessageW.restype = ctypes.wintypes.BOOL

WM_PROCESSX_SHOW_NAME = "ProcessX_ShowAndActivate_v2"

if _powrprof and hasattr(_powrprof, "PowerGetActiveScheme"):
    _powrprof.PowerGetActiveScheme.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(WIN32_GUID))]
    _powrprof.PowerGetActiveScheme.restype = ctypes.wintypes.DWORD

if _powrprof and hasattr(_powrprof, "PowerSetActiveScheme"):
    _powrprof.PowerSetActiveScheme.argtypes = [ctypes.c_void_p, ctypes.POINTER(WIN32_GUID)]
    _powrprof.PowerSetActiveScheme.restype = ctypes.wintypes.DWORD

if _powrprof and hasattr(_powrprof, "PowerEnumerate"):
    _powrprof.PowerEnumerate.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.wintypes.DWORD),
    ]
    _powrprof.PowerEnumerate.restype = ctypes.wintypes.DWORD

if _powrprof and hasattr(_powrprof, "PowerReadFriendlyName"):
    _powrprof.PowerReadFriendlyName.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(WIN32_GUID),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.wintypes.DWORD),
    ]
    _powrprof.PowerReadFriendlyName.restype = ctypes.wintypes.DWORD

if _dwmapi and hasattr(_dwmapi, "DwmSetWindowAttribute"):
    _dwmapi.DwmSetWindowAttribute.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
    ]
    _dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

if _dwmapi and hasattr(_dwmapi, "DwmExtendFrameIntoClientArea"):
    _dwmapi.DwmExtendFrameIntoClientArea.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.c_void_p,
    ]
    _dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long


# Global Static Caches
_cache_lock = threading.Lock()
_applied_cache: dict[tuple[int, float], dict] = {}
_pid_exe_cache: dict[int, str] = {}
_exe_path_cache: OrderedDict[str, str] = OrderedDict()
_io_pri_cache: dict[int, tuple[float, str]] = {}
_aff_cache: dict[int, tuple[float, list]] = {}
_services_cache: dict[int, list[str]] = {}
_services_cache_time = 0.0

_shared_proc_map: dict[str, set[int]] = {}
_shared_proc_time = 0.0
_last_running_pids: dict[str, int] = {}


def acquire_single_instance_mutex() -> object:
    name = "Local\\ProcessX_SingleInstance_v2"
    handle = _kernel32_err.CreateMutexW(None, True, name)
    last_error = ctypes.get_last_error()
    if not handle or last_error == 183:  # ERROR_ALREADY_EXISTS
        hwnd = _user32.FindWindowW(None, "ProcessX v2.0")
        if hwnd:
            msg_id = _user32.RegisterWindowMessageW(WM_PROCESSX_SHOW_NAME)
            if msg_id:
                _user32.PostMessageW(hwnd, msg_id, 0, 0)
            _user32.SetForegroundWindow(hwnd)
        sys.exit(0)
    return handle


def enable_token_privilege(privilege_name: str) -> bool:
    h_token = None
    try:
        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", ctypes.c_ulong), ("HighPart", ctypes.c_long)]

        class LUID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Luid", LUID), ("Attributes", ctypes.c_ulong)]

        class TOKEN_PRIVILEGES(ctypes.Structure):
            _fields_ = [("PrivilegeCount", ctypes.c_ulong), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

        token = ctypes.wintypes.HANDLE()
        if not _advapi32.OpenProcessToken(_kernel32.GetCurrentProcess(), 0x0028, ctypes.byref(token)):  # TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY
            return False
        h_token = token

        try:
            luid = LUID()
            if not _advapi32.LookupPrivilegeValueW(None, privilege_name, ctypes.byref(luid)):
                return False

            tp = TOKEN_PRIVILEGES()
            tp.PrivilegeCount = 1
            tp.Privileges[0].Luid = luid
            tp.Privileges[0].Attributes = 0x00000002  # SE_PRIVILEGE_ENABLED

            _advapi32.AdjustTokenPrivileges(h_token, False, ctypes.byref(tp), ctypes.sizeof(tp), None, None)
            return _kernel32.GetLastError() == 0
        finally:
            if h_token:
                _kernel32.CloseHandle(h_token)
    except (OSError, PermissionError, Exception):
        return False


_privilege_initialized = False


def ensure_increase_base_priority():
    global _privilege_initialized
    if not _privilege_initialized:
        _privilege_initialized = True
        enable_token_privilege("SeIncreaseBasePriorityPrivilege")


# CPU Sets Topology Detection
def _query_system_cpu_set_information() -> bytes:
    try:
        kernel32 = ctypes.windll.kernel32
        fn = getattr(kernel32, "GetSystemCpuSetInformation", None)
        if not fn:
            return b""
        needed = ctypes.c_ulong(0)
        fn(None, 0, ctypes.byref(needed), None, 0)
        if needed.value == 0:
            return b""
        for _ in range(3):
            buf_size = needed.value
            buf = (ctypes.c_byte * buf_size)()
            if fn(buf, buf_size, ctypes.byref(needed), None, 0):
                return bytes(buf)[:needed.value]
            if kernel32.GetLastError() != 122 or needed.value <= buf_size:
                break
    except OSError:
        pass
    return b""


def _detect_cpu_topology() -> dict:
    raw_sets = _query_system_cpu_set_information()
    cpu_sets_by_gl = {}
    if raw_sets:
        offset = 0
        while offset + 16 <= len(raw_sets):
            size = int.from_bytes(raw_sets[offset : offset + 4], "little")
            cputype = int.from_bytes(raw_sets[offset + 4 : offset + 8], "little")
            if size < 16 or offset + size > len(raw_sets):
                break
            if cputype == 0:  # CpuSetInformation
                cs_id = int.from_bytes(raw_sets[offset + 8 : offset + 12], "little")
                group = int.from_bytes(raw_sets[offset + 12 : offset + 14], "little")
                logical_idx = raw_sets[offset + 14]
                cpu_sets_by_gl[(group, logical_idx)] = cs_id
            offset += size

    if cpu_sets_by_gl:
        sorted_gl = sorted(cpu_sets_by_gl.keys(), key=lambda x: (x[0], x[1]))
    else:
        n_log = psutil.cpu_count(logical=True) or 1
        sorted_gl = [(0, i) for i in range(n_log)]

    logical_processors = []
    global_to_cpu_set_id = {}
    cpu_set_id_to_global = {}

    for g_idx, (grp, l_idx) in enumerate(sorted_gl):
        cs_id = cpu_sets_by_gl.get((grp, l_idx))
        logical_processors.append({
            "global_index": g_idx,
            "group": grp,
            "logical_index": l_idx,
            "cpu_set_id": cs_id,
            "display_label": f"CPU {g_idx}",
        })
        if cs_id is not None:
            global_to_cpu_set_id[g_idx] = cs_id
            cpu_set_id_to_global[cs_id] = g_idx

    return {
        "logical_processor_count": len(logical_processors),
        "processor_group_count": len(set(x[0] for x in sorted_gl)),
        "logical_processors": logical_processors,
        "global_to_cpu_set_id": global_to_cpu_set_id,
        "cpu_set_id_to_global": cpu_set_id_to_global,
    }


CPU_TOPOLOGY = _detect_cpu_topology()
CPU_COUNT = CPU_TOPOLOGY["logical_processor_count"]


def set_cpu_sets(pid: int, cpu_indices: list | None) -> bool:
    h_proc = None
    try:
        for access in (
            PROCESS_SET_LIMITED_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION,
            PROCESS_SET_INFORMATION | PROCESS_QUERY_INFORMATION,
            PROCESS_ALL_ACCESS,
        ):
            h_proc = _kernel32.OpenProcess(access, False, pid)
            if h_proc:
                break
        if not h_proc:
            return False

        if not cpu_indices:
            return bool(_kernel32.SetProcessDefaultCpuSets(h_proc, None, 0))

        mapping = CPU_TOPOLOGY.get("global_to_cpu_set_id", {})
        if not mapping:
            return False

        set_ids = [mapping[i] for i in cpu_indices if i in mapping]
        if len(set_ids) != len(cpu_indices):
            return False

        arr = (ctypes.c_uint32 * len(set_ids))(*set_ids)
        return bool(_kernel32.SetProcessDefaultCpuSets(h_proc, arr, len(set_ids)))
    except (OSError, PermissionError, Exception):
        return False
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


def get_effective_cpu_sets(pid: int) -> list[int]:
    mapping = CPU_TOPOLOGY.get("cpu_set_id_to_global", {})
    if not mapping:
        return []
    h_proc = None
    try:
        h_proc = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_proc:
            return []
        count = ctypes.wintypes.ULONG(0)
        _kernel32.GetProcessDefaultCpuSets(h_proc, None, 0, ctypes.byref(count))
        if count.value == 0:
            return []
        arr = (ctypes.c_uint32 * count.value)()
        _kernel32.GetProcessDefaultCpuSets(h_proc, arr, count.value, ctypes.byref(count))
        return sorted(set(mapping[s] for s in arr if s in mapping))
    except (OSError, PermissionError, Exception):
        return []
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


def get_io_priority(pid: int) -> int:
    h_proc = None
    try:
        h_proc = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_proc:
            h_proc = _kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if not h_proc:
            return -1
        io_val = ctypes.c_ulong(0)
        if _NtQIP(h_proc, ProcessIoPriority, ctypes.byref(io_val), ctypes.sizeof(io_val), None) == 0:
            return int(io_val.value)
        return -1
    except (OSError, PermissionError, Exception):
        return -1
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


def set_io_priority(pid: int, level: int) -> tuple[bool, str]:
    if not 0 <= level <= 3:
        return False, f"Invalid level {level}"
    h_proc = None
    try:
        if level == 3:
            ensure_increase_base_priority()

        h_proc = _kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
        if not h_proc:
            h_proc = _kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not h_proc:
            return False, f"OpenProcess error {_kernel32.GetLastError()}"

        io_val = ctypes.c_ulong(level)
        status = _NtSIP(h_proc, ProcessIoPriority, ctypes.byref(io_val), ctypes.sizeof(io_val))
        if status == 0:
            return True, "OK"
        if status == -1073741727:  # STATUS_PRIVILEGE_NOT_HELD
            return False, "Requires Administrator privileges"
        return False, f"NtStatus 0x{status & 0xFFFFFFFF:08X}"
    except (OSError, PermissionError, Exception) as e:
        return False, str(e)
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


def get_memory_priority(pid: int) -> int:
    h_proc = None
    try:
        h_proc = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_proc:
            h_proc = _kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if not h_proc:
            return -1
        mem = MEMORY_PRIORITY_INFORMATION()
        if _kernel32.GetProcessInformation(h_proc, ProcessMemoryPriority, ctypes.byref(mem), ctypes.sizeof(mem)):
            return int(mem.MemoryPriority)
        return -1
    except (OSError, PermissionError, Exception):
        return -1
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


def set_memory_priority(pid: int, level: int) -> tuple[bool, str]:
    if level not in (1, 2, 3, 4, 5):
        return False, f"Invalid level {level}"
    h_proc = None
    try:
        h_proc = _kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
        if not h_proc:
            h_proc = _kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not h_proc:
            return False, f"OpenProcess error {_kernel32.GetLastError()}"
        mem = MEMORY_PRIORITY_INFORMATION(level)
        if _kernel32.SetProcessInformation(h_proc, ProcessMemoryPriority, ctypes.byref(mem), ctypes.sizeof(mem)):
            return True, "OK"
        return False, f"SetProcessInformation error {_kernel32.GetLastError()}"
    except (OSError, PermissionError, Exception) as e:
        return False, str(e)
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


def get_ecoqos(pid: int) -> bool:
    h_proc = None
    try:
        h_proc = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_proc:
            h_proc = _kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if not h_proc:
            return False
        state = PROCESS_POWER_THROTTLING_STATE(Version=PROCESS_POWER_THROTTLING_CURRENT_VERSION)
        if _kernel32.GetProcessInformation(h_proc, ProcessPowerThrottling, ctypes.byref(state), ctypes.sizeof(state)):
            return bool(state.StateMask & PROCESS_POWER_THROTTLING_EXECUTION_SPEED)
        return False
    except (OSError, PermissionError, Exception):
        return False
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


def set_ecoqos(pid: int, enabled: bool) -> tuple[bool, str]:
    h_proc = None
    try:
        h_proc = _kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
        if not h_proc:
            h_proc = _kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not h_proc:
            return False, f"OpenProcess error {_kernel32.GetLastError()}"
        state = PROCESS_POWER_THROTTLING_STATE()
        state.Version = PROCESS_POWER_THROTTLING_CURRENT_VERSION
        state.ControlMask = PROCESS_POWER_THROTTLING_EXECUTION_SPEED
        state.StateMask = PROCESS_POWER_THROTTLING_EXECUTION_SPEED if enabled else 0
        if _kernel32.SetProcessInformation(h_proc, ProcessPowerThrottling, ctypes.byref(state), ctypes.sizeof(state)):
            return True, "OK"
        return False, f"SetProcessInformation error {_kernel32.GetLastError()}"
    except (OSError, PermissionError, Exception) as e:
        return False, str(e)
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


def trim_process_memory(pid: int) -> bool:
    """Flush working set to standby list via EmptyWorkingSet."""
    h_proc = None
    try:
        h_proc = _kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION, False, pid)
        if not h_proc:
            return False
        if _psapi and hasattr(_psapi, "EmptyWorkingSet"):
            return bool(_psapi.EmptyWorkingSet(h_proc))
        return False
    except (OSError, PermissionError, Exception):
        return False
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


def kill_process(pid: int) -> bool:
    try:
        p = psutil.Process(pid)
        p.kill()
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
        pass
    h_proc = None
    try:
        h_proc = _kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if h_proc:
            return bool(_kernel32.TerminateProcess(h_proc, 1))
        return False
    except (OSError, PermissionError, Exception):
        return False
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


# Power Plan Management via powrprof.dll (Zero subprocess calls)
def _guid_from_str(guid_str: str) -> WIN32_GUID:
    u = uuid.UUID(guid_str)
    return WIN32_GUID.from_buffer_copy(u.bytes_le)


def get_active_power_plan_guid() -> str | None:
    if not _powrprof:
        return None
    try:
        p_guid = ctypes.POINTER(WIN32_GUID)()
        if _powrprof.PowerGetActiveScheme(None, ctypes.byref(p_guid)) == 0 and p_guid:
            try:
                return p_guid.contents.to_str()
            finally:
                _kernel32.LocalFree(p_guid)
    except OSError:
        pass
    return None


def set_active_power_plan(guid_str: str) -> tuple[bool, str]:
    if not _GUID_RE.match(guid_str.strip()):
        return False, f"Invalid GUID format: {guid_str}"
    if not _powrprof:
        return False, "powrprof library not available"
    try:
        g = _guid_from_str(guid_str)
        res = _powrprof.PowerSetActiveScheme(None, ctypes.byref(g))
        if res == 0:
            return True, "OK"
        return False, f"PowerSetActiveScheme error {res}"
    except OSError as e:
        return False, str(e)


def list_power_plans() -> list[tuple[str, str, bool]]:
    plans = []
    if not _powrprof:
        return plans
    try:
        active_guid = (get_active_power_plan_guid() or "").lower()
        ACCESS_SCHEME = 16
        index = 0
        buf = (ctypes.c_byte * 16)()
        buf_size = ctypes.wintypes.DWORD(16)

        while True:
            buf_size.value = 16
            res = _powrprof.PowerEnumerate(None, None, None, ACCESS_SCHEME, index, buf, ctypes.byref(buf_size))
            if res != 0:
                break
            g = WIN32_GUID.from_buffer_copy(buf)
            g_str = g.to_str()

            name_buf_size = ctypes.wintypes.DWORD(512)
            name_buf = (ctypes.c_byte * 512)()
            n_res = _powrprof.PowerReadFriendlyName(None, ctypes.byref(g), None, None, name_buf, ctypes.byref(name_buf_size))
            name = ctypes.wstring_at(name_buf) if n_res == 0 else g_str

            plans.append((name, g_str, g_str.lower() == active_guid))
            index += 1
    except OSError:
        pass
    return plans

def _log_power_plan_error(message: str):
    try:
        log_path = APP_DIR / "processx.log"
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{now}] [POWER PLAN ERROR] {message}\n")
    except Exception:
        pass


class PowerPlanManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._original_guid = None
        self._controllers = []

    def on_process_seen(self, exe: str, guid: str):
        guid = guid.strip()
        if not _GUID_RE.match(guid):
            return
        with self._lock:
            if self._original_guid is None:
                active = get_active_power_plan_guid()
                if active:
                    self._original_guid = active
                    set_setting("power_plan_original_guid", active)
            self._controllers = [c for c in self._controllers if c[0] != exe]
            self._controllers.append((exe, guid))
            self._activate(guid)

    def on_process_gone(self, exe: str):
        with self._lock:
            before = len(self._controllers)
            self._controllers = [c for c in self._controllers if c[0] != exe]
            if len(self._controllers) == before:
                return
            if self._controllers:
                self._activate(self._controllers[-1][1])
            else:
                self._restore()

    def shutdown_restore(self):
        with self._lock:
            if self._original_guid:
                self._restore()
            self._controllers = []

    def _activate(self, guid: str):
        current = get_active_power_plan_guid()
        if current and current.lower() == guid.lower():
            return
        ok, msg = set_active_power_plan(guid)
        if not ok:
            _log_power_plan_error(f"Failed to activate power plan {guid}: {msg}")

    def _restore(self):
        if not self._original_guid:
            return
        current = get_active_power_plan_guid()
        if current and current.lower() == self._original_guid.lower():
            self._original_guid = None
            set_setting("power_plan_original_guid", None)
            return
        ok, msg = set_active_power_plan(self._original_guid)
        if ok:
            self._original_guid = None
            set_setting("power_plan_original_guid", None)
        else:
            _log_power_plan_error(f"Failed to restore power plan {self._original_guid}: {msg}")

    def recover_on_startup(self):
        with self._lock:
            if self._controllers:
                return
            saved = get_setting("power_plan_original_guid")
            if not saved or not isinstance(saved, str):
                return
            saved = saved.strip()
            if not _GUID_RE.match(saved):
                set_setting("power_plan_original_guid", None)
                return
            existing_guids = {p[1].lower() for p in list_power_plans()}
            if saved.lower() not in existing_guids:
                set_setting("power_plan_original_guid", None)
                return
            current = get_active_power_plan_guid()
            if current and current.lower() == saved.lower():
                set_setting("power_plan_original_guid", None)
                return
            ok, msg = set_active_power_plan(saved)
            if not ok:
                _log_power_plan_error(f"Failed to restore power plan on startup ({saved}): {msg}")
            set_setting("power_plan_original_guid", None)


_power_plan_manager = PowerPlanManager()
atexit.register(_power_plan_manager.shutdown_restore)


def recover_power_plan_on_startup():
    _power_plan_manager.recover_on_startup()


# Windows Startup Registration (Task Scheduler)
_STARTUP_TASK_NAME = "ProcessX v2.0"


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _remove_legacy_run_key() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            try:
                winreg.DeleteValue(key, "ProcessX")
            except (FileNotFoundError, OSError):
                pass
    except (FileNotFoundError, OSError):
        pass


def _get_current_user_id() -> str:
    token = ctypes.wintypes.HANDLE()
    try:
        if _advapi32.OpenProcessToken(_kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            try:
                size = ctypes.wintypes.DWORD(0)
                _advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
                if size.value > 0:
                    buf = (ctypes.c_byte * size.value)()
                    if _advapi32.GetTokenInformation(token, 1, buf, size.value, ctypes.byref(size)):
                        sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p)).contents
                        pstr = ctypes.c_wchar_p()
                        if _advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(pstr)):
                            try:
                                sid_str = pstr.value or ""
                                return sid_str
                            finally:
                                _kernel32.LocalFree(pstr)
            finally:
                _kernel32.CloseHandle(token)
    except Exception:
        pass

    domain = os.environ.get("USERDOMAIN")
    user = os.environ.get("USERNAME")
    if domain and user:
        return f"{domain}\\{user}"
    return user or ""


def is_in_startup() -> bool:
    try:
        res = subprocess.run(
            ["schtasks", "/Query", "/TN", _STARTUP_TASK_NAME],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return res.returncode == 0
    except Exception:
        return False


def add_to_startup() -> tuple[bool, str]:
    try:
        _remove_legacy_run_key()

        frozen = getattr(sys, "frozen", False)
        if frozen:
            cmd = f'"{Path(sys.executable).resolve()}"'
            args = "--startup"
        else:
            script_path = str(Path(__file__).resolve().parent / "main.py")
            py_exe = sys.executable.replace("python.exe", "pythonw.exe")
            if not Path(py_exe).exists():
                py_exe = sys.executable
            cmd = f'"{py_exe}"'
            args = f'"{script_path}" --startup'

        user_id = _get_current_user_id()
        user_id_tag = f"\n      <UserId>{_xml_escape(user_id)}</UserId>" if user_id else ""

        xml_content = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <URI>\\{_STARTUP_TASK_NAME}</URI>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
  </Settings>
  <Triggers>
    <LogonTrigger>{user_id_tag}
    </LogonTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>{_xml_escape(cmd)}</Command>
      <Arguments>{_xml_escape(args)}</Arguments>
    </Exec>
  </Actions>
</Task>"""

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-16", suffix=".xml", delete=False) as f:
                f.write(xml_content)
                tmp_path = f.name

            res = subprocess.run(
                ["schtasks", "/Create", "/TN", _STARTUP_TASK_NAME, "/XML", tmp_path, "/F"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if res.returncode == 0:
                return True, tr("status_startup_added_task")
            err = (res.stderr or res.stdout or "").strip()
            return False, tr("status_startup_failed", err=err)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
    except Exception as e:
        return False, tr("status_startup_failed", err=e)


def remove_from_startup() -> tuple[bool, str]:
    try:
        _remove_legacy_run_key()

        if not is_in_startup():
            return True, ""

        res = subprocess.run(
            ["schtasks", "/Delete", "/TN", _STARTUP_TASK_NAME, "/F"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if res.returncode == 0 or not is_in_startup():
            return True, ""
        err = (res.stderr or res.stdout or "").strip()
        return False, tr("status_startup_failed", err=err)
    except Exception as e:
        return False, tr("status_startup_failed", err=e)


# DWM Window Blur & Styling
def set_dwm_corner_preference(hwnd: int, rounded: bool = True) -> bool:
    if not hwnd or sys.platform != "win32" or not _dwmapi:
        return False
    try:
        val = ctypes.c_int(DWMWCP_ROUND if rounded else DWMWCP_DONOTROUND)
        return _dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(val), ctypes.sizeof(val)) == 0
    except OSError:
        return False


def apply_dwm_glass(hwnd: int, backdrop_type: int = 3, dark: bool = True, rounded: bool = True) -> bool:
    if not hwnd or sys.platform != "win32" or not _dwmapi:
        return False
    try:
        if dark:
            val_dark = ctypes.c_int(1)
            _dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val_dark), ctypes.sizeof(val_dark))

        set_dwm_corner_preference(hwnd, rounded=rounded)

        val_backdrop = ctypes.c_int(backdrop_type)
        _dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(val_backdrop), ctypes.sizeof(val_backdrop))

        margins = DWM_MARGINS(-1, -1, -1, -1)
        _dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        return True
    except OSError:
        return False


# Process Cache & Dynamic Path Resolution
def query_process_image_path(pid: int) -> str:
    """
    Retrieves the full native executable path using Win32 API directly:
    OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid) + QueryFullProcessImageNameW.
    Works reliably for elevated, system, and anti-cheat protected processes
    where standard psutil proc.exe() fails with AccessDenied.
    """
    if not pid or pid <= 4:
        return ""
    h_proc = None
    try:
        h_proc = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_proc:
            return ""
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.wintypes.DWORD(len(buf))
        # dwFlags = 0 returns standard Win32 format (e.g. C:\Windows\...)
        if _QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
            val = buf.value
            if val and os.path.isfile(val):
                return val
        return ""
    except Exception:
        return ""
    finally:
        if h_proc:
            _kernel32.CloseHandle(h_proc)


def resolve_exe_path_dynamically(name: str) -> str:
    """
    Dynamically discovers an executable path by process name without hardcoding:
    1. PATH resolution via shutil.which(name)
    2. Dynamic system search in System32, SysWOW64, and SystemRoot based on environment
    """
    if not name:
        return ""
    name_clean = name.strip()
    cand_name = name_clean if name_clean.lower().endswith(".exe") else f"{name_clean}.exe"

    # Step 3a: Check PATH / current environment
    found = shutil.which(cand_name) or shutil.which(name_clean)
    if found and os.path.isfile(found):
        try:
            return os.path.abspath(found)
        except OSError:
            return found

    # Step 3b: Dynamic lookup in Windows SystemRoot directories
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or "C:\\Windows"
    search_dirs = [
        os.path.join(system_root, "System32"),
        os.path.join(system_root, "SysWOW64"),
        system_root,
    ]
    for d in search_dirs:
        cand = os.path.join(d, cand_name)
        if os.path.isfile(cand):
            return cand

    return ""


def get_proc_exe(proc_or_pid, name: str = None) -> str:
    """
    100% dynamic 3-step executable path resolution for any Windows process:
    Step 1: psutil proc.exe()
    Step 2: Win32 QueryFullProcessImageNameW via OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)
    Step 3: Dynamic lookup via shutil.which and SystemRoot (System32/SysWOW64)
    """
    pid = proc_or_pid if isinstance(proc_or_pid, int) else getattr(proc_or_pid, "pid", None)
    if pid:
        with _cache_lock:
            cached = _pid_exe_cache.get(pid)
        if cached and os.path.isfile(cached):
            return cached

    path = ""
    # Step 1: psutil proc.exe()
    try:
        if hasattr(proc_or_pid, "exe"):
            path = proc_or_pid.exe()
        elif pid and pid > 4:
            path = psutil.Process(pid).exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError):
        path = ""

    # Step 2: Win32 API via QueryFullProcessImageNameW
    if (not path or not os.path.isfile(path)) and pid and pid > 4:
        path = query_process_image_path(pid)

    # Step 3: Dynamic lookup by process name if still missing
    if not path or not os.path.isfile(path):
        proc_name = name
        if not proc_name and hasattr(proc_or_pid, "name"):
            try:
                proc_name = proc_or_pid.name()
            except Exception:
                pass
        if not proc_name and pid:
            try:
                proc_name = psutil.Process(pid).name()
            except Exception:
                pass
        if proc_name and proc_name.lower() not in ("system idle process", "system", "registry", "memcompression", "memory compression", "secure system"):
            path = resolve_exe_path_dynamically(proc_name)

    if path and os.path.isfile(path):
        if pid:
            with _cache_lock:
                _pid_exe_cache[pid] = path
        return path

    return ""


def find_exe_path(name: str, pid: int = None, path_hint: str = None) -> str | None:
    if path_hint and os.path.isfile(path_hint):
        return path_hint

    name_lower = (name or "").strip().lower()
    if pid is not None:
        with _cache_lock:
            cached = _pid_exe_cache.get(pid)
        if cached and os.path.isfile(cached):
            return cached
        exe = get_proc_exe(pid, name=name)
        if exe and os.path.isfile(exe):
            with _cache_lock:
                _pid_exe_cache[pid] = exe
                if name_lower:
                    _exe_path_cache[name_lower] = exe
            return exe

    if name_lower:
        with _cache_lock:
            cached = _exe_path_cache.get(name_lower)
        if cached and os.path.isfile(cached):
            return cached

    # Scan running processes to find matching executable
    for p in psutil.process_iter(["name", "exe", "pid"]):
        try:
            p_name = (p.info["name"] or "").strip().lower()
            p_pid = p.info.get("pid")
            p_exe = p.info.get("exe")
            if not p_exe and p_pid and p_pid > 4:
                p_exe = query_process_image_path(p_pid)
            if p_name and p_exe and os.path.isfile(p_exe):
                with _cache_lock:
                    if p_pid:
                        _pid_exe_cache[p_pid] = p_exe
                    _exe_path_cache[p_name] = p_exe
                if p_name == name_lower:
                    return p_exe
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Step 3: Dynamic discovery
    if name_lower and name_lower not in ("system idle process", "system", "registry", "memcompression", "memory compression", "secure system"):
        resolved = resolve_exe_path_dynamically(name)
        if resolved and os.path.isfile(resolved):
            with _cache_lock:
                _exe_path_cache[name_lower] = resolved
            return resolved

    return None



def find_rule_for_process(proc_or_pid, rules: dict, name: str = None, exe_path: str = None) -> tuple:
    if not rules:
        return None, None

    raw_path = exe_path or get_proc_exe(proc_or_pid)
    pid = proc_or_pid if isinstance(proc_or_pid, int) else getattr(proc_or_pid, "pid", None)

    if name:
        proc_name = name.lower().strip()
    elif raw_path:
        proc_name = os.path.basename(raw_path).lower().strip()
    elif hasattr(proc_or_pid, "name"):
        try:
            proc_name = (proc_or_pid.name() or "").lower().strip()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            proc_name = ""
    else:
        proc_name = ""

    if is_critical_process(proc_name, pid, raw_path):
        return None, None

    if proc_name:
        if proc_name in rules:
            return proc_name, rules[proc_name]
        for k, r in rules.items():
            k_lower = k.lower().strip()
            r_name = (r.get("name") or k).lower().strip()
            if k_lower == proc_name or r_name == proc_name:
                return k, r

    return None, None


def _get_rule_signature(rule: dict) -> dict:
    aff = rule.get("affinity")
    if isinstance(aff, (list, tuple, set)):
        aff_tuple = tuple(sorted(aff))
    else:
        aff_tuple = aff
    return {
        "priority": rule.get("priority"),
        "affinity": aff_tuple,
        "io_priority": rule.get("io_priority"),
        "memory_priority": rule.get("memory_priority"),
        "ecoqos": rule.get("ecoqos"),
    }


def _get_proc_cache_key(proc: psutil.Process) -> tuple[int, float]:
    try:
        return (proc.pid, proc.create_time())
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return (proc.pid, 0.0)


def apply_rule(proc: psutil.Process, rule: dict, force: bool = False) -> list[str]:
    if proc is None:
        return ["CPU Sets: Saved", "CPU Priority: Saved", "I/O Priority: Saved"]
    pid = proc.pid
    try:
        p_name = proc.name()
        p_exe = get_proc_exe(proc)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        p_name, p_exe = "", ""

    if is_critical_process(p_name, pid, p_exe):
        return ["Protected: Critical system process skipped"]

    cache_key = _get_proc_cache_key(proc)
    rule_sig = _get_rule_signature(rule)

    if not force:
        with _cache_lock:
            if _applied_cache.get(cache_key) == rule_sig:
                return ["Cached: Rule already applied"]

    results = []
    now = time.monotonic()

    # 1. CPU Sets
    aff = rule.get("affinity")
    if aff not in (None, "None", []):
        try:
            ok = set_cpu_sets(pid, aff)
            results.append("CPU Sets: OK" if ok else "CPU Sets: FAILED")
            if ok:
                with _cache_lock:
                    _aff_cache[pid] = (now, list(aff))
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError):
            results.append("CPU Sets: FAILED")

    # 2. CPU Priority
    pri = rule.get("priority")
    if pri and pri not in (None, "None"):
        try:
            pri_class = PRIORITY_MAP.get(pri)
            if pri_class is not None:
                proc.nice(pri_class)
                results.append("CPU Priority: OK")
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError):
            results.append("CPU Priority: FAILED")

    # 3. I/O Priority
    io_pri = rule.get("io_priority")
    if io_pri not in (None, "None", -1):
        try:
            lvl = int(io_pri)
            ok, _ = set_io_priority(pid, lvl)
            results.append("I/O Priority: OK" if ok else "I/O Priority: FAILED")
            if ok:
                with _cache_lock:
                    _io_pri_cache[pid] = (now, IO_PRIORITY_MAP.get(lvl, "Normal"))
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError):
            results.append("I/O Priority: FAILED")

    # 4. Memory Priority
    mem_pri = rule.get("memory_priority")
    if mem_pri not in (None, "None", -1):
        try:
            ok, _ = set_memory_priority(pid, int(mem_pri))
            results.append("Memory Priority: OK" if ok else "Memory Priority: FAILED")
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError):
            results.append("Memory Priority: FAILED")

    # 5. EcoQoS
    if rule.get("ecoqos") is not None:
        try:
            ok, _ = set_ecoqos(pid, bool(rule["ecoqos"]))
            results.append("EcoQoS: OK" if ok else "EcoQoS: FAILED")
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError):
            results.append("EcoQoS: FAILED")

    with _cache_lock:
        _applied_cache[cache_key] = rule_sig

    return results


def apply_all_rules(rules: dict):
    if not rules:
        return
    live_pids = set()
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            p_name = (proc.info.get("name") or "").lower()
            p_pid = proc.info.get("pid")
            if not p_pid or p_pid <= 4:
                continue
            live_pids.add(p_pid)
            if is_critical_process(p_name, p_pid):
                continue
            _, rule = find_rule_for_process(proc, rules, name=p_name)
            if rule:
                apply_rule(proc, rule)
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError):
            pass

    with _cache_lock:
        dead_keys = [k for k in _applied_cache if k[0] not in live_pids]
        for k in dead_keys:
            _applied_cache.pop(k, None)


def apply_all_rules_async(rules: dict) -> threading.Thread:
    rules_copy = dict(rules)
    t = threading.Thread(target=apply_all_rules, args=(rules_copy,), daemon=True, name="ApplyAllRulesThread")
    t.start()
    return t


def revert_running_instances(target_key: str, rule_hint: dict = None, all_rules: dict = None):
    default_rule = {
        "priority": "Normal",
        "io_priority": 2,
        "affinity": None,
        "memory_priority": 5,
        "ecoqos": False,
    }
    target_name = (rule_hint.get("name") if rule_hint else "") or os.path.basename(target_key)
    target_name = target_name.lower().strip()

    if is_critical_process(target_name):
        return

    for p in psutil.process_iter(["name", "pid"]):
        try:
            p_name = (p.info["name"] or "").lower().strip()
            p_pid = p.info.get("pid")
            if is_critical_process(p_name, p_pid) or p_name != target_name:
                continue
            apply_rule(p, default_rule, force=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError):
            pass


def save_and_apply_rule(rules: dict, target_key: str, rule: dict, pid: int = None, path_hint: str = None, auto_apply: bool = True) -> tuple:
    target_name = os.path.basename(rule.get("name") or target_key).lower().strip()
    rule_key = target_name
    rule["name"] = rule.get("name") or target_name
    rule.pop("exe_path", None)

    if auto_apply:
        rules[rule_key] = rule
        save_rules(rules)

    instance_ct = 0
    all_msgs = []
    any_failed = False
    pp_guid = rule.get("power_plan")

    runtime_exe = path_hint or (get_proc_exe(pid, name=target_name) if pid else None) or find_exe_path(target_name, pid=pid)
    if is_critical_process(target_name, pid, runtime_exe):
        return 0, False, ["Protected: Critical system process skipped"]

    applied_pids = set()
    for p in psutil.process_iter(["name", "pid"]):
        try:
            p_pid = p.info["pid"]
            p_name = (p.info["name"] or "").lower().strip()
            if is_critical_process(p_name, p_pid):
                continue

            matched = False
            if auto_apply:
                matched_key, _ = find_rule_for_process(p, rules, name=p_name)
                matched = (matched_key == rule_key)
            else:
                matched = (p_name == target_name or p_pid == pid)

            if matched:
                instance_ct += 1
                applied_pids.add(p_pid)
                msgs = apply_rule(p, rule, force=True)
                if any("FAILED" in m for m in msgs):
                    any_failed = True
                all_msgs.extend(msgs)
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError):
            pass

    if pid and pid not in applied_pids:
        try:
            p = psutil.Process(pid)
            if not is_critical_process(p.name(), pid):
                instance_ct += 1
                msgs = apply_rule(p, rule, force=True)
                if any("FAILED" in m for m in msgs):
                    any_failed = True
                all_msgs.extend(msgs)
        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError, OSError):
            pass

    if instance_ct > 0 and auto_apply:
        if pp_guid:
            _power_plan_manager.on_process_seen(rule_key, pp_guid)
        else:
            _power_plan_manager.on_process_gone(rule_key)

    return instance_ct, any_failed, all_msgs


def delete_rule(rules: dict, rule_key: str):
    actual_key = None
    target_rule = None
    rule_key_lower = os.path.basename(rule_key).lower().strip()
    if rule_key_lower in rules:
        actual_key = rule_key_lower
        target_rule = rules[rule_key_lower]
    elif rule_key in rules:
        actual_key = rule_key
        target_rule = rules[rule_key]
    else:
        for k, r in list(rules.items()):
            if k.lower().strip() == rule_key_lower or (r.get("name") and r["name"].lower().strip() == rule_key_lower):
                actual_key = k
                target_rule = r
                break

    if actual_key and actual_key in rules:
        rule_to_del = rules.pop(actual_key)
        save_rules(rules)
        revert_running_instances(actual_key, rule_to_del, rules)
        _power_plan_manager.on_process_gone(actual_key)


def get_running_pids(rules: dict) -> dict[str, int]:
    """
    Returns a dict mapping {rule_key: pid} for each unique rule in rules
    that currently matches at least one active running process on the system.
    Guarantees:
    - Only valid rule keys from rules are present in the returned dict.
    - Multiple running instances under the same profile only count once.
    - len(result) <= len(rules) is always true.
    """
    if not rules:
        return {}
    result = {}
    try:
        for p in psutil.process_iter(["name", "pid"]):
            try:
                p_name = p.info.get("name")
                p_id = p.info.get("pid")
                if not p_id or not psutil.pid_exists(p_id):
                    continue
                rk, _ = find_rule_for_process(p, rules, name=p_name)
                if rk and rk in rules and rk not in result:
                    result[rk] = p_id
                    if len(result) == len(rules):
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                pass
    except (OSError, PermissionError, Exception):
        pass
    return result


def get_live_active_profile_pids(rules: dict, watcher=None) -> dict[str, int]:
    """
    Returns a validated mapping {rule_key: pid} for currently active profiles,
    consulting RuleWatcher's tracked PIDs and cross-checking process existence.
    Falls back to get_running_pids(rules).
    """
    result = {}
    if watcher:
        try:
            active_map = watcher.get_active_rule_pids()
            for rk, pids in active_map.items():
                for pid in pids:
                    if psutil.pid_exists(pid):
                        try:
                            p = psutil.Process(pid)
                            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                                result[rk] = pid
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                            pass
        except Exception:
            pass
    if not result and rules:
        result = get_running_pids(rules)
    return result


def get_services_by_pid() -> dict[int, list[str]]:
    global _services_cache, _services_cache_time
    now = time.monotonic()
    if now - _services_cache_time < 5.0 and _services_cache:
        return _services_cache

    s_map = defaultdict(list)
    try:
        for s in psutil.win_service_iter():
            try:
                p_id = s.pid()
                s_name = s.name()
                if p_id and s_name:
                    s_map[p_id].append(s_name)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                pass
    except (OSError, PermissionError):
        pass

    _services_cache = dict(s_map)
    _services_cache_time = now
    return _services_cache


def priority_name(nice: int | None) -> str:
    return PRIORITY_REVERSE.get(nice, "Normal")


def io_priority_name_cached(pid: int) -> str:
    now = time.monotonic()
    with _cache_lock:
        cached = _io_pri_cache.get(pid)
        if cached and (now - cached[0]) < 6.0:
            return cached[1]
    val = get_io_priority(pid)
    val_str = IO_PRIORITY_MAP.get(val, "None")
    with _cache_lock:
        _io_pri_cache[pid] = (now, val_str)
    return val_str


def effective_cpu_sets_cached(pid: int) -> list[int]:
    now = time.monotonic()
    with _cache_lock:
        cached = _aff_cache.get(pid)
        if cached and (now - cached[0]) < 6.0:
            return cached[1]
    live = get_effective_cpu_sets(pid)
    with _cache_lock:
        _aff_cache[pid] = (now, live)
    return live


def format_ram(b: int) -> str:
    if b >= 1073741824:
        return f"{b / 1073741824:.1f} GB"
    if b >= 1048576:
        return f"{b / 1048576:.0f} MB"
    if b >= 1024:
        return f"{b / 1024:.0f} KB"
    return f"{b} B"


def format_cpu(pct: float) -> str:
    return f"{pct:.1f}%"


def format_affinity_str(aff: list | None) -> str:
    if aff is None or aff == "None":
        return "None"
    if not aff or len(set(aff)) >= CPU_COUNT:
        return "all"
    return ",".join(str(c) for c in sorted(aff))


SYSTEM_ROOT_PRIORITY = {
    "system idle process": 0,
    "system": 1,
    "registry": 2,
    "smss.exe": 3,
    "csrss.exe": 4,
    "wininit.exe": 5,
    "services.exe": 6,
    "lsass.exe": 7,
    "fontdrvhost.exe": 8,
    "winlogon.exe": 9,
    "dwm.exe": 10,
}


def collect_proc_snapshot(rules: dict) -> list[dict]:
    global _shared_proc_map, _shared_proc_time, _last_running_pids
    live_pids = set()
    current_running_pids = {}
    name_to_pids = defaultdict(set)
    pid_exe_map = {}
    exe_name_map = {}
    raw_nodes = {}

    attrs = ["pid", "name", "ppid", "cpu_percent", "memory_info", "nice"]
    for p in psutil.process_iter(attrs):
        try:
            info = p.info
            pid = info["pid"]
            live_pids.add(pid)
            name = (info.get("name") or "").strip()
            if not name:
                continue

            name_lower = name.lower()
            name_to_pids[name_lower].add(pid)
            if name_lower not in current_running_pids:
                current_running_pids[name_lower] = pid

            ppid = info.get("ppid") or 0
            mem = info.get("memory_info")
            ram = mem.rss if mem else 0
            nice = info.get("nice")
            if name_lower != "system idle process":
                cpu = (info.get("cpu_percent") or 0.0) / CPU_COUNT
            else:
                cpu = 0.0

            with _cache_lock:
                cached_exe = _pid_exe_cache.get(pid)
            if cached_exe:
                p_exe = cached_exe
                pid_exe_map[pid] = cached_exe
            else:
                try:
                    p_exe = p.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError, PermissionError, Exception):
                    p_exe = ""

                # Step 2: Fallback to Win32 QueryFullProcessImageNameW via OpenProcess(0x1000)
                if not p_exe and pid > 4:
                    p_exe = query_process_image_path(pid)

                if p_exe and os.path.isfile(p_exe):
                    pid_exe_map[pid] = p_exe
                    if name_lower not in exe_name_map:
                        exe_name_map[name_lower] = p_exe

            raw_nodes[pid] = {
                "name": name,
                "name_lower": name_lower,
                "pid": pid,
                "ppid": ppid,
                "ram": ram,
                "nice": nice,
                "cpu": cpu,
                "exe_path": p_exe,
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError, PermissionError, Exception):
            pass

    with _cache_lock:
        _shared_proc_map = dict(name_to_pids)
        _shared_proc_time = time.monotonic()
        _last_running_pids = current_running_pids
        for p_id, p_path in pid_exe_map.items():
            _pid_exe_cache[p_id] = p_path
        for k, v in exe_name_map.items():
            if k not in _exe_path_cache:
                _exe_path_cache[k] = v
                if len(_exe_path_cache) > 512:
                    _exe_path_cache.popitem(last=False)

        # Evict terminated PIDs
        for dead in set(_io_pri_cache.keys()) - live_pids:
            _io_pri_cache.pop(dead, None)
        for dead in set(_aff_cache.keys()) - live_pids:
            _aff_cache.pop(dead, None)
        for dead in set(_pid_exe_cache.keys()) - live_pids:
            _pid_exe_cache.pop(dead, None)
        dead_applied = [k for k in _applied_cache if k[0] not in live_pids]
        for k in dead_applied:
            _applied_cache.pop(k, None)

    services_map = get_services_by_pid()
    resolved = {}

    for pid, node in raw_nodes.items():
        name_lower = node["name_lower"]
        proc_exe = node["exe_path"] or pid_exe_map.get(pid) or ""

        _, rule = find_rule_for_process(pid, rules, name=name_lower, exe_path=proc_exe)
        pri_str = rule["priority"] if rule and "priority" in rule and rule["priority"] not in (None, "None") else priority_name(node["nice"])
        io_str = IO_PRIORITY_MAP.get(rule.get("io_priority"), io_priority_name_cached(pid)) if rule and rule.get("io_priority") not in (None, "None", -1) else io_priority_name_cached(pid)
        aff_str = format_affinity_str(rule["affinity"]) if rule and rule.get("affinity") not in (None, "None") else (format_affinity_str(effective_cpu_sets_cached(pid)) or "all")

        is_sys = pid <= 4 or name_lower in SYSTEM_ROOT_PRIORITY or is_critical_process(name_lower, pid, proc_exe)

        resolved[pid] = {
            "name": node["name"],
            "name_lower": name_lower,
            "pid": pid,
            "ppid": node["ppid"],
            "ram": node["ram"],
            "cpu": node["cpu"],
            "exe_path": proc_exe,
            "pri_str": pri_str,
            "io_str": io_str,
            "aff_str": aff_str,
            "has_rule": bool(rule),
            "services": services_map.get(pid, []),
            "is_system": is_sys,
        }

    children_by_parent = defaultdict(list)
    roots = []

    for pid, node in resolved.items():
        ppid = node["ppid"]
        if ppid in resolved and ppid != pid:
            curr = ppid
            cycle = False
            for _ in range(25):
                if curr == pid:
                    cycle = True
                    break
                if curr not in resolved:
                    break
                curr = resolved[curr]["ppid"]
            if not cycle:
                children_by_parent[ppid].append(pid)
            else:
                roots.append(pid)
        else:
            roots.append(pid)

    visited = set()

    def build_tree_node(pid) -> dict | None:
        if pid in visited:
            return None
        visited.add(pid)
        base = dict(resolved[pid])
        child_pids = children_by_parent.get(pid, [])
        built_children = []
        tot_ram = base["ram"]
        tot_cpu = base["cpu"]

        for c_pid in child_pids:
            c_node = build_tree_node(c_pid)
            if c_node:
                built_children.append(c_node)
                tot_ram += c_node["total_ram"]
                tot_cpu += c_node["total_cpu"]

        built_children.sort(key=lambda x: (x["total_ram"], x["total_cpu"]), reverse=True)
        base["children"] = built_children
        base["has_children"] = bool(built_children)
        base["total_ram"] = tot_ram
        base["total_cpu"] = tot_cpu
        base["ram_str"] = format_ram(tot_ram if built_children else base["ram"])
        base["cpu_str"] = format_cpu(tot_cpu if built_children else base["cpu"])
        return base

    built_roots = []
    for r_pid in roots:
        node = build_tree_node(r_pid)
        if node:
            built_roots.append(node)

    for u_pid in resolved:
        if u_pid not in visited:
            node = build_tree_node(u_pid)
            if node:
                built_roots.append(node)

    system_roots = []
    user_roots = []

    for r_node in built_roots:
        nm = r_node["name_lower"]
        if nm == "explorer.exe":
            user_roots.append(r_node)
        elif r_node["is_system"] or nm in SYSTEM_ROOT_PRIORITY or r_node["pid"] <= 4:
            system_roots.append(r_node)
        else:
            user_roots.append(r_node)

    system_roots.sort(key=lambda x: (SYSTEM_ROOT_PRIORITY.get(x["name_lower"], 999), -x["total_ram"]))
    user_roots.sort(key=lambda x: (0 if x["name_lower"] == "explorer.exe" else 1, -x["total_ram"]))
    return system_roots + user_roots


# Background Watcher
class RuleWatcher:
    def __init__(self, rules_supplier, status_cb=None, refresh_cb=None, profile_status_cb=None):
        self.rules_supplier = rules_supplier
        self.status_cb = status_cb
        self.refresh_cb = refresh_cb
        self.profile_status_cb = profile_status_cb
        self._stop_event = threading.Event()
        self._interval = 2.5
        self._thread = None
        self._lock = threading.Lock()
        self._active_rule_pids = {}

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        with self._lock:
            self._active_rule_pids.clear()

    def set_active_mode(self, active: bool):
        # 2.5s when UI is visible, 5.0s+ when minimized to tray
        self._interval = 2.5 if active else 5.5

    def get_active_rule_pids(self) -> dict[str, set[int]]:
        with self._lock:
            return {k: set(v) for k, v in self._active_rule_pids.items()}

    def _run(self):
        last_rule_pids = {}
        while not self._stop_event.is_set():
            try:
                rules = self.rules_supplier()
                if not rules:
                    if last_rule_pids:
                        for rk in list(last_rule_pids):
                            _power_plan_manager.on_process_gone(rk)
                            if self.profile_status_cb:
                                try:
                                    self.profile_status_cb(rk, False)
                                except Exception:
                                    pass
                        last_rule_pids.clear()
                    with self._lock:
                        self._active_rule_pids.clear()
                    if self.status_cb:
                        try:
                            self.status_cb("")
                        except Exception:
                            pass
                    if self._stop_event.wait(timeout=self._interval):
                        break
                    continue

                want_names = set()
                for rk, r in rules.items():
                    nm = (r.get("name") or os.path.basename(rk)).lower().strip()
                    if nm and not is_critical_process(nm):
                        want_names.add(nm)

                candidate_pids = []
                now = time.monotonic()
                with _cache_lock:
                    if (now - _shared_proc_time) < (self._interval + 1.0) and _shared_proc_map:
                        for name_lower in want_names:
                            if name_lower in _shared_proc_map:
                                for p_id in _shared_proc_map[name_lower]:
                                    if not is_critical_process(name_lower, p_id):
                                        candidate_pids.append((p_id, name_lower))

                if not candidate_pids:
                    for p in psutil.process_iter(["name", "pid"]):
                        try:
                            n = (p.info.get("name") or "").lower().strip()
                            p_id = p.info.get("pid")
                            if n in want_names and not is_critical_process(n, p_id):
                                candidate_pids.append((p_id, n))
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                            pass

                current_rule_pids = {}
                for pid, n in candidate_pids:
                    try:
                        if not psutil.pid_exists(pid):
                            with _cache_lock:
                                if n in _shared_proc_map and pid in _shared_proc_map[n]:
                                    _shared_proc_map[n].discard(pid)
                            continue
                        proc = psutil.Process(pid)
                        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
                            with _cache_lock:
                                if n in _shared_proc_map and pid in _shared_proc_map[n]:
                                    _shared_proc_map[n].discard(pid)
                            continue

                        rk, rule = find_rule_for_process(pid, rules, name=n)
                        if rk and rule:
                            current_rule_pids.setdefault(rk, set()).add(pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                        with _cache_lock:
                            if n in _shared_proc_map and pid in _shared_proc_map[n]:
                                _shared_proc_map[n].discard(pid)

                # Cross-check existing tracked rules for any processes that exited
                for rk, pids in list(last_rule_pids.items()):
                    if rk not in current_rule_pids:
                        continue
                    live_pids = set()
                    for pid in current_rule_pids[rk]:
                        if psutil.pid_exists(pid):
                            try:
                                p = psutil.Process(pid)
                                if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                                    live_pids.add(pid)
                            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                                pass
                    if live_pids:
                        current_rule_pids[rk] = live_pids
                    else:
                        del current_rule_pids[rk]

                newly_applied = []
                newly_started_rules = []
                for rk, cur_pids in current_rule_pids.items():
                    rule = rules[rk]
                    seen_pids = last_rule_pids.get(rk, set())
                    new_pids = cur_pids - seen_pids
                    disp_name = rule.get("name") or os.path.basename(rk)
                    for pid in new_pids:
                        try:
                            proc = psutil.Process(pid)
                            apply_rule(proc, rule)
                            newly_applied.append(disp_name)
                            pp = rule.get("power_plan")
                            if pp:
                                _power_plan_manager.on_process_seen(rk, pp)
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
                            pass
                    if not seen_pids and cur_pids:
                        newly_started_rules.append(rk)
                    last_rule_pids[rk] = cur_pids

                exited_rules = [rk for rk in list(last_rule_pids) if rk not in current_rule_pids]
                for rk in exited_rules:
                    _power_plan_manager.on_process_gone(rk)
                    del last_rule_pids[rk]

                with self._lock:
                    self._active_rule_pids = {k: set(v) for k, v in current_rule_pids.items()}

                if self.profile_status_cb:
                    for rk in newly_started_rules:
                        try:
                            self.profile_status_cb(rk, True)
                        except Exception:
                            pass
                    for rk in exited_rules:
                        try:
                            self.profile_status_cb(rk, False)
                        except Exception:
                            pass

                if (newly_applied or exited_rules) and self.refresh_cb:
                    try:
                        self.refresh_cb()
                    except Exception:
                        pass

                if (newly_applied or exited_rules) and self.status_cb:
                    try:
                        if current_rule_pids:
                            active_names = [rules[rk].get("name") or os.path.basename(rk) for rk in current_rule_pids if rk in rules]
                            if active_names:
                                self.status_cb(f"Auto-applied: {', '.join(sorted(set(active_names)))}")
                            else:
                                self.status_cb("")
                        else:
                            self.status_cb("")
                    except Exception:
                        pass
            except (OSError, PermissionError, Exception):
                pass

            if self._stop_event.wait(timeout=self._interval):
                break
