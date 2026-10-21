#!/usr/bin/env python3
"""Preserve CMake's manifest-update notification through Wine's exit-code truncation."""

from pathlib import Path
import subprocess
import sys


def manifest(args):
    command = [str(Path(__file__).with_name('mt-wine')), *args]
    result = subprocess.run(command).returncode
    if result == 1 and '/notify_update' in args:
        # Verify the merge succeeded before reporting CMake's POSIX update status.
        result = subprocess.run([arg for arg in command if arg != '/notify_update']).returncode
        return 187 if result == 0 else result
    return result


if __name__ == '__main__':
    sys.exit(manifest(sys.argv[1:]))
