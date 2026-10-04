"""Double-click launcher; opens an existing panel or starts a new one."""
import importlib.util
import json
import subprocess
import sys
from urllib.request import urlopen
import webbrowser

from core import ROOT, DATA, init, settings, rows, add_source

required = ['streamlit', 'yt_dlp', 'faster_whisper', 'imageio_ffmpeg', 'googleapiclient', 'google_auth_oauthlib']
if any(importlib.util.find_spec(name) is None for name in required):
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
init()
if not rows('SELECT id FROM sources') and (ROOT / 'starter-watchlist.json').exists():
    for source in json.loads((ROOT / 'starter-watchlist.json').read_text()):
        add_source(source['url'], source['label'], source['permission_note'])
if settings()['enabled']:
    with (DATA / 'worker.log').open('a') as output:
        subprocess.Popen([sys.executable, str(ROOT / 'worker.py'), 'loop'], cwd=ROOT,
                         stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
try:
    with urlopen('http://127.0.0.1:8765/_stcore/health', timeout=2) as response:
        running = response.status == 200
except Exception:
    running = False
if running:
    webbrowser.open('http://127.0.0.1:8765')
else:
    subprocess.run([sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
                    '--server.address', '127.0.0.1', '--server.port', '8765',
                    '--server.showEmailPrompt', 'false',
                    '--browser.gatherUsageStats', 'false'], cwd=ROOT)
