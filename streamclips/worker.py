"""One durable local scheduler; shared job lock prevents overlapping work."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
from pathlib import Path
import signal
import threading
import time

import core


@contextlib.contextmanager
def lock(name='job'):
    path = core.DATA / (name + '.lock')
    with path.open('a+') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def recover():
    with core.db() as con:
        con.execute("UPDATE videos SET state='failed',error='Previous processing was interrupted; retry from Recordings.' WHERE state='processing'")
        con.execute("UPDATE clips SET state='check_upload',error='Upload was interrupted. Check YouTube Studio before retrying.' WHERE state='uploading'")


def process(video):
    import media
    with core.db() as con:
        changed = con.execute("UPDATE videos SET state='processing',error=NULL WHERE id=? AND state IN ('new','failed')", (video['id'],)).rowcount
    if not changed:
        return
    try:
        media.make_clip(video)
    except Exception as exc:
        with core.db() as con:
            con.execute("UPDATE videos SET state='failed',error=? WHERE id=?", (str(exc)[:2000], video['id']))
        core.log('Could not make clip: ' + str(exc))


def cycle():
    cfg = core.settings()
    if time.time() - cfg['last_scan'] >= cfg['interval_minutes'] * 60:
        core.scan()
        cfg = core.settings()
        made = core.rows('SELECT COUNT(*) AS n FROM clips WHERE created>?', (time.time() - 86400,))[0]['n']
        # Produce at most one per cycle and cap the total over a rolling 24-hour window.
        if cfg['enabled'] and made < cfg['daily_clip_limit']:
            candidates = core.rows('''SELECT v.* FROM videos v JOIN sources s ON s.id=v.source_id
                WHERE v.state='new' AND s.enabled=1
                AND (v.duration IS NULL OR v.duration<=?)
                AND (v.published IS NULL OR v.published>=?)
                ORDER BY v.score DESC LIMIT 5''',
                (cfg['max_source_minutes'] * 60, time.time() - cfg['max_age_days'] * 86400))
            for candidate in candidates:
                process(candidate)
                if core.rows('SELECT state FROM videos WHERE id=?', (candidate['id'],))[0]['state'] == 'done':
                    break
    cfg = core.settings()
    if not cfg['enabled'] or time.time() - cfg['last_upload'] < cfg['min_upload_hours'] * 3600:
        return
    if not (core.DATA / 'youtube-token.json').exists():
        return
    states = ('ready', 'approved') if cfg['auto_upload'] else ('approved',)
    placeholders = ','.join('?' for _ in states)
    queued = core.rows(f'''SELECT c.id FROM clips c JOIN videos v ON c.video_id=v.id
        JOIN sources s ON v.source_id=s.id WHERE c.state IN ({placeholders}) AND s.enabled=1
        ORDER BY c.created LIMIT 1''', states)
    if queued:
        import youtube
        core.configure(job='Uploading a clip to YouTube')
        youtube.upload(queued[0]['id'])


def run(action, item=None):
    with lock() as acquired:
        if not acquired:
            core.log('Another job is already running. Try again when it finishes.')
            return
        recover()
        try:
            if action == 'scan':
                core.scan()
            elif action == 'make':
                videos = core.rows('''SELECT v.* FROM videos v JOIN sources s ON s.id=v.source_id
                    WHERE v.id=? AND s.enabled=1''', (item,))
                if not videos:
                    raise RuntimeError('Recording not found or creator paused.')
                process(videos[0])
            elif action == 'connect':
                import youtube
                core.configure(job='Waiting for your YouTube sign-in')
                youtube.connect()
            elif action == 'upload':
                import youtube
                core.configure(job='Uploading selected clip')
                youtube.upload(item)
            elif action == 'cycle':
                cycle()
        except Exception as exc:
            core.log('Action stopped: ' + str(exc))
        finally:
            core.configure(job='Idle')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['scan', 'make', 'connect', 'upload', 'cycle', 'loop'])
    parser.add_argument('item', nargs='?')
    args = parser.parse_args()
    core.init()
    if args.action != 'loop':
        run(args.action, args.item)
        return
    with lock('scheduler') as acquired:
        if not acquired:
            return
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())

        def heartbeat():
            while not stop.is_set():
                core.configure(heartbeat=time.time())
                stop.wait(5)
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            while not stop.is_set():
                if core.settings()['enabled']:
                    run('cycle')
                stop.wait(30)
        finally:
            stop.set()
            thread.join(timeout=6)
            core.configure(heartbeat=0)


if __name__ == '__main__':
    main()
