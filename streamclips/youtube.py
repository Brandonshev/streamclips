"""Explicit OAuth connection and conservative upload state transitions."""
from __future__ import annotations

import json
import os
import time

import core

SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly']


def save_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path) + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(text)
    os.replace(str(path) + '.tmp', path)
    os.chmod(path, 0o600)


def credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    path = core.DATA / 'youtube-token.json'
    if not path.exists():
        raise RuntimeError('Connect your destination YouTube channel first.')
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_private(path, creds.to_json())
    if not creds.valid:
        raise RuntimeError('Your YouTube connection expired. Reconnect in Settings.')
    return creds


def connect():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    client = core.DATA / 'youtube-client.json'
    if not client.exists():
        raise RuntimeError('Add your Google desktop-app connection file in Settings first.')
    flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
    creds = flow.run_local_server(port=0, timeout_seconds=180,
                                 authorization_prompt_message='Finish connecting in your browser.')
    api = build('youtube', 'v3', credentials=creds)
    channels = api.channels().list(part='snippet', mine=True).execute().get('items', [])
    if len(channels) != 1:
        raise RuntimeError('Choose an account with one destination YouTube channel and reconnect.')
    save_private(core.DATA / 'youtube-token.json', creds.to_json())
    core.configure(channel_name=channels[0]['snippet']['title'], channel_id=channels[0]['id'])
    core.log('YouTube connected: ' + channels[0]['snippet']['title'])


def upload(cid):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from pathlib import Path
    cfg = core.settings()
    if cfg['privacy'] not in ('private', 'unlisted', 'public'):
        raise ValueError('Choose a valid upload visibility.')
    clips = core.rows('''SELECT c.*, v.url AS source_url, v.title AS original_title, s.label AS creator, s.enabled AS source_enabled
        FROM clips c JOIN videos v ON v.id=c.video_id JOIN sources s ON s.id=v.source_id WHERE c.id=?''', (cid,))
    if not clips or clips[0]['state'] not in ('ready', 'approved'):
        raise RuntimeError('This clip is not awaiting upload, or has already been uploaded.')
    clip = clips[0]
    if not clip['source_enabled']:
        raise RuntimeError('This creator is paused. Upload is disabled for their clips.')
    if not Path(clip['path']).exists():
        raise RuntimeError('The clip file is missing.')
    creds = credentials()
    api = build('youtube', 'v3', credentials=creds)
    current = api.channels().list(part='id', mine=True).execute().get('items', [])
    if not current or current[0]['id'] != cfg.get('channel_id'):
        raise RuntimeError('Destination channel changed. Reconnect before uploading.')
    body = {
        'snippet': {'title': clip['title'].lower()[:100],
                    'description': f"clip from {clip['creator'].lower()}.\noriginal video: {clip['original_title'].lower()}\noriginal recording: {clip['source_url']}\n\nshared with creator permission.\n#shorts",
                    'categoryId': '24'},
        'status': {'privacyStatus': cfg['privacy'], 'selfDeclaredMadeForKids': False},
    }
    # Mark before any bytes leave. Never automatically retry uncertain uploads after a crash.
    with core.db() as con:
        changed = con.execute("UPDATE clips SET state='uploading',error=NULL WHERE id=? AND state IN ('ready','approved')", (cid,)).rowcount
        if changed != 1:
            raise RuntimeError('Another upload already claimed this clip.')
    try:
        request = api.videos().insert(part='snippet,status', body=body,
                                     media_body=MediaFileUpload(clip['path'], chunksize=8 * 1024**2,
                                                               mimetype='video/mp4', resumable=True),
                                     notifySubscribers=False)
        response = None
        while response is None:
            _, response = request.next_chunk(num_retries=2)
        with core.db() as con:
            con.execute("UPDATE clips SET state='uploaded',youtube_id=?,error=NULL WHERE id=?", (response['id'], cid))
        core.configure(last_upload=time.time())
        core.log('Uploaded: ' + clip['title'])
        return response['id']
    except Exception as exc:
        with core.db() as con:
            con.execute("UPDATE clips SET state='check_upload',error=? WHERE id=?", (str(exc)[:1500], cid))
        core.log('Upload needs checking in YouTube Studio before retry: ' + clip['title'])
        raise
