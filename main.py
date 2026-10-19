import sys
from config import load_rules
from core import acquire_single_instance_mutex, apply_all_rules
from ui import run_app


def main():
    if "--apply-rules" in sys.argv:
        apply_all_rules(load_rules())
        sys.exit(0)

    _mutex = acquire_single_instance_mutex()
    sys.exit(run_app())


if __name__ == "__main__":
    main()
