"""Install or remove the per-user macOS scheduler login service."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys

import core


LABEL = 'com.streamclips.scheduler'
AGENT = Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist'
DOMAIN = f'gui/{os.getuid()}'


def service_definition():
    return {
        'Label': LABEL,
        'ProgramArguments': [sys.executable, str(core.ROOT / 'worker.py'), 'loop'],
        'WorkingDirectory': str(core.ROOT),
        'RunAtLoad': True,
        'KeepAlive': True,
        'ProcessType': 'Background',
        'StandardOutPath': str(core.DATA / 'scheduler.log'),
        'StandardErrorPath': str(core.DATA / 'scheduler.log'),
    }


def install():
    core.init()
    AGENT.parent.mkdir(parents=True, exist_ok=True)
    target = f'{DOMAIN}/{LABEL}'
    subprocess.run(['launchctl', 'bootout', target], capture_output=True, check=False)
    AGENT.write_bytes(plistlib.dumps(service_definition()))
    os.chmod(AGENT, 0o600)
    subprocess.run(['launchctl', 'bootstrap', DOMAIN, str(AGENT)], check=True)
    print(f'Installed {LABEL}; it starts when you sign in and follows the app pause switch.')


def uninstall():
    subprocess.run(['launchctl', 'bootout', f'{DOMAIN}/{LABEL}'], capture_output=True, check=False)
    AGENT.unlink(missing_ok=True)
    print(f'Removed {LABEL}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'uninstall'])
    args = parser.parse_args()
    (install if args.action == 'install' else uninstall)()
