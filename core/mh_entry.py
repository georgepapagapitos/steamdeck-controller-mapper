"""Entry point for the installed shims (docs/14 §6): `/usr/bin/python3 -I mh_entry.py mh-run ...` or `... <map-helper
command>`. -I leaves the script's own directory off sys.path, so it's put back here.

The mh-run path must never stop a launch: if even importing map-helper fails (a broken install), it still execs the
command after `--` unless the shim said it will (--no-exec) or there's none (--hook).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))


def _mh_run(argv):
    try:
        from maphelper.mhrun import main
    except BaseException:
        if "--hook" in argv or "--es-de" in argv or "--no-exec" in argv or "--" not in argv:
            return 0
        command = argv[argv.index("--") + 1:]
        if command:
            os.execvp(command[0], command)
        return 0
    return main(argv)


if __name__ == "__main__":
    if sys.argv[1:2] == ["mh-run"]:
        sys.exit(_mh_run(sys.argv[2:]))
    from maphelper.cli import main
    sys.exit(main(sys.argv[1:]))
