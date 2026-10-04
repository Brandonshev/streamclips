"""StreamClips v0.2.3: local state, source discovery, and highlight selection."""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('STREAMCLIPS_DATA', ROOT / 'data')).resolve()
VERSION = '0.2.3'
DEFAULTS = {
    'interval_minutes': 360, 'max_source_minutes': 120,
    'daily_clip_limit': 2, 'max_download_mb': 1000,
    'max_age_days': 30, 'min_clip_seconds': 25, 'max_clip_seconds': 55,
    'model': 'tiny', 'framing_mode': 'fit', 'enabled': False, 'auto_upload': False,
    'privacy': 'private', 'min_upload_hours': 12, 'last_upload': 0,
    'last_scan': 0, 'heartbeat': 0, 'job': 'Idle',
}


@contextlib.contextmanager
def db():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATA / 'streamclips.sqlite', timeout=20)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def init():
    with db() as con:
        con.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY, url TEXT UNIQUE NOT NULL, platform TEXT NOT NULL,
            label TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            permission_note TEXT NOT NULL, error TEXT, checked REAL);
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY, source_id INTEGER NOT NULL, url TEXT NOT NULL,
            title TEXT NOT NULL, duration REAL, views INTEGER, published REAL,
            score REAL NOT NULL, state TEXT NOT NULL DEFAULT 'new', error TEXT);
        CREATE TABLE IF NOT EXISTS clips (
            id TEXT PRIMARY KEY, video_id TEXT NOT NULL, title TEXT NOT NULL,
            start REAL NOT NULL, end REAL NOT NULL, score REAL NOT NULL,
            path TEXT NOT NULL, transcript TEXT NOT NULL, state TEXT NOT NULL,
            created REAL NOT NULL, youtube_id TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, created REAL NOT NULL, message TEXT NOT NULL);
        ''')
        for key, value in DEFAULTS.items():
            con.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', (key, json.dumps(value)))


def settings():
    with db() as con:
        return {r['key']: json.loads(r['value']) for r in con.execute('SELECT * FROM settings')}


def configure(**values):
    with db() as con:
        con.executemany('INSERT OR REPLACE INTO settings VALUES (?,?)',
                        [(k, json.dumps(v)) for k, v in values.items()])


def rows(sql, args=()):
    with db() as con:
        return [dict(r) for r in con.execute(sql, args)]


def log(message):
    with db() as con:
        con.execute('INSERT INTO events(created,message) VALUES (?,?)', (time.time(), str(message)[:2000]))


def source_url(value):
    """Restrict the watchlist to known public platform origins."""
    p = urlparse(value.strip())
    host = (p.hostname or '').lower().removeprefix('www.')
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Use a normal https:// YouTube, Twitch or Kick link.')
    path = p.path.rstrip('/')
    if host == 'youtube.com':
        if not re.fullmatch(r'/(?:channel/[\w-]+|@[\w.\-]+|c/[\w.\-]+|user/[\w.\-]+)(?:/videos)?', path):
            raise ValueError('Paste a YouTube channel link, not an individual video.')
        return 'youtube', 'https://www.youtube.com' + path.removesuffix('/videos') + '/videos'
    if host == 'twitch.tv' and re.fullmatch(r'/[\w]+(?:/videos)?', path):
        return 'twitch', 'https://www.twitch.tv/' + path.split('/')[1] + '/videos?filter=archives&sort=time'
    if host == 'kick.com' and re.fullmatch(r'/[\w-]+(?:/videos)?', path):
        return 'kick', 'https://kick.com/' + path.split('/')[1]
    raise ValueError('Use a YouTube channel, Twitch profile or Kick profile link.')


def add_source(url, label='', note='Creator authorises clipping and reposting (confirmed by user).'):
    platform, url = source_url(url)
    with db() as con:
        con.execute('INSERT INTO sources(url,platform,label,permission_note) VALUES (?,?,?,?)',
                    (url, platform, label.strip() or url, note))


def rank_video(views, published, now=None):
    """Popularity/recency proxy, deliberately not a virality prediction."""
    now = now or time.time()
    age_hours = max(1, (now - (published or now - 7 * 86400)) / 3600)
    return round(math.log1p(max(0, views or 0)) / (1 + age_hours / 48), 4)


def normalize_entry(entry, platform, now=None):
    now = now or time.time()
    if entry.get('is_live') or entry.get('live_status') in ('is_live', 'is_upcoming', 'post_live'):
        return None
    eid = str(entry.get('id') or '')
    url = entry.get('webpage_url') or entry.get('url') or ''
    if platform == 'youtube' and eid:
        url = 'https://www.youtube.com/watch?v=' + eid
    if not eid or not url.startswith('https://'):
        return None
    published = entry.get('timestamp') or entry.get('release_timestamp')
    if not published and entry.get('upload_date'):
        import datetime
        try:
            published = datetime.datetime.strptime(entry['upload_date'], '%Y%m%d').replace(
                tzinfo=datetime.timezone.utc).timestamp()
        except ValueError:
            pass
    views = entry.get('view_count') or 0
    return {'id': platform + ':' + eid, 'url': url,
            'title': str(entry.get('title') or 'Untitled recording'),
            'duration': entry.get('duration'), 'views': views, 'published': published,
            'score': rank_video(views, published, now)}


def discover(source, limit=8):
    from yt_dlp import YoutubeDL
    opts = {'quiet': True, 'no_warnings': True, 'skip_download': True,
            'extract_flat': 'in_playlist', 'playlistend': limit, 'socket_timeout': 20,
            'retries': 1, 'extractor_retries': 1}
    opts.update(javascript_options())
    if source['platform'] == 'kick':
        # Kick has no stable documented public VOD-list API. Surface failure; never bypass blocks.
        slug = urlparse(source['url']).path.strip('/').split('/')[0]
        req = Request(f'https://kick.com/api/v2/channels/{slug}/videos',
                      headers={'User-Agent': f'StreamClips/{VERSION}', 'Accept': 'application/json'})
        with urlopen(req, timeout=20) as response:
            payload = json.load(response)
        items = payload if isinstance(payload, list) else payload.get('data', [])
        if not isinstance(items, list):
            raise RuntimeError('Kick returned an unsupported recordings list. Try again later.')
        entries = []
        for item in items[:limit]:
            video = item.get('video') or {}
            uuid = video.get('uuid') or item.get('uuid')
            if not uuid:
                continue
            entries.append({'id': uuid, 'url': f'https://kick.com/{slug}/videos/{uuid}',
                            'title': item.get('session_title'), 'duration': (item.get('duration') or 0) / 1000,
                            'view_count': item.get('views') or video.get('views')})
        if items and not entries:
            raise RuntimeError('Kick recordings format changed; discovery needs an update.')
    else:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source['url'], download=False)
        entries = (info or {}).get('entries') or []
    found = []
    for entry in entries:
        if entry:
            normalized = normalize_entry(entry, source['platform'])
            if normalized:
                found.append(normalized)
    return found


def javascript_options():
    """Use an existing Node runtime when available for YouTube's player challenges."""
    bundled = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
    node = shutil.which('node') or (str(bundled) if bundled.is_file() else None)
    return {'js_runtimes': {'node': {'path': node}}} if node else {}


def scan():
    for source in rows('SELECT * FROM sources WHERE enabled=1'):
        configure(job='Checking ' + source['label'])
        try:
            found = discover(source)
            with db() as con:
                for position, v in enumerate(found):
                    # Flat playlist entries often omit dates. Their order still reflects
                    # the source's recent-first listing, so favour newer entries.
                    priority = v['score'] + 10 * max(0, 8 - position)
                    con.execute('''INSERT INTO videos(id,source_id,url,title,duration,views,published,score)
                    VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    views=excluded.views, score=excluded.score, title=excluded.title,
                    duration=excluded.duration,published=excluded.published''',
                                (v['id'], source['id'], v['url'], v['title'], v['duration'],
                                 v['views'], v['published'], priority))
                con.execute('UPDATE sources SET error=NULL,checked=? WHERE id=?', (time.time(), source['id']))
            log(f"Found {len(found)} recent recordings: {source['label']}")
        except Exception as exc:
            with db() as con:
                con.execute('UPDATE sources SET error=?,checked=? WHERE id=?', (str(exc)[:1500], time.time(), source['id']))
            log(f"Could not check {source['label']}: {exc}")
    configure(last_scan=time.time())


def choose_highlight(segments, minimum=25, maximum=55):
    """Sentence-aligned speech-density + opening-hook heuristic, no paid LLM."""
    candidates = []
    hooks = {'why', 'how', 'never', 'imagine', 'actually', 'secret', 'wait', 'watch', 'what', 'but'}
    for i, segment in enumerate(segments):
        chunk = []
        for following in segments[i:]:
            if following['end'] - segment['start'] > maximum:
                break
            chunk.append(following)
            length = following['end'] - segment['start']
            if length < minimum:
                continue
            text = ' '.join(s['text'].strip() for s in chunk)
            words = re.findall(r"[\w']+", text.lower())
            if len(words) < 20:
                continue
            spoken = sum(max(0, s['end'] - s['start']) for s in chunk)
            density = min(1, spoken / length)
            pace = len(words) / length
            diversity = len(set(words)) / len(words)
            hook = len(set(words[:15]) & hooks)
            ending = text.rstrip().endswith(('.', '!', '?'))
            score = 40 * density + 20 * diversity + 5 * min(hook, 3) + 10 * ending - 10 * abs(pace - 2.3)
            candidates.append({'start': max(0, segment['start'] - .1), 'end': following['end'],
                               'score': round(score, 1), 'text': text, 'segments': list(chunk)})
    if not candidates:
        raise ValueError('No clear spoken highlight of the selected length was found. Recording held for review.')
    return max(candidates, key=lambda c: c['score'])


def clip_id(video_id, start, end):
    return hashlib.sha256(f'{video_id}:{start:.2f}:{end:.2f}'.encode()).hexdigest()[:20]
