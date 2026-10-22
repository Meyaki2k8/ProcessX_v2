import datetime
import faulthandler
import sys
import threading
import traceback
from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
from config import APP_DIR, load_rules
from core import acquire_single_instance_mutex, apply_all_rules, recover_power_plan_on_startup
from ui import run_app

_LOG_FILE = None


def _setup_crash_logging():
    global _LOG_FILE
    log_path = APP_DIR / "processx.log"
    try:
        if log_path.exists() and log_path.stat().st_size > 1_000_000:
            old_log = APP_DIR / "processx.log.old"
            if old_log.exists():
                old_log.unlink()
            log_path.rename(old_log)
    except Exception:
        pass

    try:
        _LOG_FILE = open(log_path, "a", encoding="utf-8", buffering=1)
    except Exception:
        return

    try:
        faulthandler.enable(file=_LOG_FILE, all_threads=True)
    except Exception:
        pass

    def _sys_excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            _LOG_FILE.write(f"\n[{now}] [FATAL UNCAUGHT EXCEPTION]\n")
            traceback.print_exception(exc_type, exc_value, exc_tb, file=_LOG_FILE)
            _LOG_FILE.flush()
        except Exception:
            pass

    sys.excepthook = _sys_excepthook

    def _threading_excepthook(args):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            _LOG_FILE.write(f"\n[{now}] [FATAL THREAD EXCEPTION in {args.thread.name}]\n")
            traceback.print_exception(args.exc_type, args.exc_value, args.exc_tb, file=_LOG_FILE)
            _LOG_FILE.flush()
        except Exception:
            pass

    threading.excepthook = _threading_excepthook

    def _unraisablehook(unraisable):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            _LOG_FILE.write(f"\n[{now}] [UNRAISABLE EXCEPTION: {unraisable.err_msg}]\n")
            traceback.print_exception(unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback, file=_LOG_FILE)
            _LOG_FILE.flush()
        except Exception:
            pass

    sys.unraisablehook = _unraisablehook

    def _qt_message_handler(mode: QtMsgType, context, message: str):
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            level = "WARNING" if mode == QtMsgType.QtWarningMsg else ("CRITICAL" if mode == QtMsgType.QtCriticalMsg else "FATAL")
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ctx_str = f" ({context.file}:{context.line})" if context and context.file else ""
            try:
                _LOG_FILE.write(f"[{now}] [QT {level}]{ctx_str} {message}\n")
                _LOG_FILE.flush()
            except Exception:
                pass

    qInstallMessageHandler(_qt_message_handler)


def main():
    _setup_crash_logging()
    if "--apply-rules" in sys.argv:
        apply_all_rules(load_rules())
        sys.exit(0)

    _mutex = acquire_single_instance_mutex()
    recover_power_plan_on_startup()
    sys.exit(run_app())


if __name__ == "__main__":
    main()

