"""StreamClips local control panel. No paid services or analytics."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

import streamlit as st

import core

core.init()
st.set_page_config(page_title='StreamClips', page_icon='🎬', layout='wide')


def start(action, item=None):
    with (core.DATA / 'worker.log').open('a') as output:
        subprocess.Popen([sys.executable, str(core.ROOT / 'worker.py'), action, *([item] if item else [])],
                         cwd=core.ROOT, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)


def timestamp(value):
    return datetime.datetime.fromtimestamp(value).strftime('%d %b, %H:%M') if value else 'Not yet'


st.title('StreamClips')
st.caption(f'Your creator watchlist → captioned vertical clips → YouTube or TikTok · v{core.VERSION}')
cfg = core.settings()
sources = core.rows('SELECT * FROM sources ORDER BY id')
clips = core.rows('''SELECT c.*,v.url AS source_url,v.title AS original_title,s.label AS creator,s.platform AS source_platform
    FROM clips c JOIN videos v ON v.id=c.video_id JOIN sources s ON s.id=v.source_id
    ORDER BY c.created DESC''')

with st.sidebar:
    st.subheader('Automation')
    alive = time.time() - cfg['heartbeat'] < 45
    st.write('Running' if cfg['enabled'] and alive else 'Paused' if not cfg['enabled'] else 'Scheduler offline')
    st.caption('Your computer must stay awake. Closing this page does not stop the scheduler.')
    if st.button('Start automation', type='primary', disabled=not any(s['enabled'] for s in sources)):
        core.configure(enabled=True, last_scan=0)
        start('loop')
        st.rerun()
    if st.button('Pause automation'):
        core.configure(enabled=False)
        st.info('Paused. An in-progress clip may finish; no further scheduled uploads will start.')
    if st.button('Check creators now', disabled=not sources):
        start('scan')
        st.toast('Checking for recordings. Refresh shortly.')
    if st.button('Refresh status'):
        st.rerun()
    st.divider()
    st.write('Destination')
    st.write(cfg.get('channel_name', 'YouTube not connected'))
    st.caption('Uploads: ' + cfg['privacy'])

@st.fragment(run_every=5)
def status():
    current = core.settings()
    a, b, c = st.columns(3)
    a.metric('Creators watched', len(core.rows('SELECT id FROM sources WHERE enabled=1')))
    b.metric('Clips ready', len(core.rows("SELECT id FROM clips WHERE state IN ('ready','approved')")))
    c.metric('Uploaded', len(core.rows("SELECT id FROM clips WHERE state='uploaded'")))
    st.info('Current job: ' + current['job'])
status()

watchlist, recordings, queue, settings_tab, activity = st.tabs(
    ['Creators', 'Recordings', 'Clips', 'Settings', 'Activity'])

with watchlist:
    st.subheader('Creators you have permission to clip')
    st.write('Paste their profile or channel links. YouTube and Twitch use recorded videos; live capture is not included.')
    with st.form('add_source', clear_on_submit=True):
        url = st.text_input('Creator link', placeholder='https://www.youtube.com/@creator')
        label = st.text_input('Name to show', placeholder='Optional')
        note = st.text_input('Permission notes', value='Creator authorises clipping and reposting.')
        submit = st.form_submit_button('Add creator')
        if submit:
            try:
                core.add_source(url, label, note)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    if not sources:
        st.info('Add your first creator above.')
    for s in sources:
        with st.container(border=True):
            st.markdown(f"**{s['label']}**")
            st.caption(f"{s['platform'].title()} · Last checked: {timestamp(s['checked'])}")
            st.link_button('Open creator', s['url'])
            if s['platform'] == 'kick':
                st.caption('Experimental: Kick may block automated recording discovery.')
            if s['error']:
                st.error(s['error'])
            enabled = st.toggle('Watch this creator', value=bool(s['enabled']), key=f"source-{s['id']}")
            if enabled != bool(s['enabled']):
                with core.db() as con:
                    con.execute('UPDATE sources SET enabled=? WHERE id=?', (int(enabled), s['id']))
                st.rerun()

with recordings:
    st.subheader('Recent recordings')
    st.caption('Ranked by views and recency where available. This is a rough priority score, not a prediction of virality.')
    videos = core.rows('''SELECT v.*,s.label AS creator FROM videos v JOIN sources s ON s.id=v.source_id
                          ORDER BY score DESC LIMIT 100''')
    if not videos:
        st.info('Use “Check creators now” to find recordings.')
    for v in videos:
        with st.expander(v['title'] + ' · ' + v['state']):
            st.write(v['creator'])
            st.write(f"Views: {v['views'] or 0:,} · Priority: {v['score']} · Length: {round((v['duration'] or 0)/60)} min")
            st.link_button('Original recording', v['url'])
            if v['error']:
                st.error(v['error'])
            if v['state'] in ('new', 'failed') and st.button('Make a clip', key='make-' + v['id']):
                start('make', v['id'])
                st.toast('Clip job started. Refresh to see progress.')

with queue:
    st.subheader('Your clips')
    st.caption('Refresh after a job finishes to see new clips. Uploads are private by default.')
    if not clips:
        st.info('Clips will appear here after processing a recording.')
    for c in clips:
        with st.expander(c['title'] + ' · ' + c['state']):
            path = Path(c['path'])
            if path.exists():
                st.video(str(path))
                st.markdown('**Post this clip to TikTok**')
                st.caption('Download the clip, then upload it using your TikTok account. Review it and choose the post settings in TikTok.')
                with path.open('rb') as clip_file:
                    st.download_button('Download video for TikTok', clip_file,
                                       file_name=f'streamclips-{c["id"]}.mp4', mime='video/mp4',
                                       key='tiktok-download-' + c['id'])
                st.code(f'{c["title"].lower()}\n\nclip from {c["creator"].lower()} ({c["source_platform"]}).\noriginal video: {c["original_title"].lower()}\n{c["source_url"]}', language=None)
                st.link_button('Open TikTok upload', 'https://www.tiktok.com/upload')
            st.caption(f"Source moment: {c['start']:.1f}–{c['end']:.1f}s · Speech highlight score: {c['score']}")
            st.write(c['transcript'])
            if c['error']:
                st.error(c['error'])
            if c['youtube_id']:
                st.link_button('Open uploaded clip', 'https://www.youtube.com/watch?v=' + c['youtube_id'])
            if c['state'] in ('ready', 'approved'):
                title = st.text_input('Upload title', value=c['title'], max_chars=100, key='title-' + c['id'])
                left, right = st.columns(2)
                if left.button('Save title and queue upload', key='approve-' + c['id'], disabled=not title.strip()):
                    with core.db() as con:
                        con.execute("UPDATE clips SET title=?,state='approved' WHERE id=? AND state IN ('ready','approved')", (title.strip(), c['id']))
                    st.success('Queued. Connect YouTube and start automation to upload on your schedule.')
                if right.button('Discard clip', key='discard-' + c['id']):
                    with core.db() as con:
                        con.execute("UPDATE clips SET state='discarded' WHERE id=? AND state IN ('ready','approved')", (c['id'],))
                    st.rerun()
            if c['state'] == 'check_upload':
                st.warning('Check YouTube Studio before retrying so the same clip is not uploaded twice.')
                existing = st.text_input('If already uploaded, paste its YouTube video ID', key='existing-' + c['id'])
                if st.button('Record existing upload', key='record-' + c['id'], disabled=len(existing.strip()) != 11):
                    with core.db() as con:
                        con.execute("UPDATE clips SET state='uploaded',youtube_id=?,error=NULL WHERE id=? AND state='check_upload'", (existing.strip(), c['id']))
                    core.configure(last_upload=time.time())
                    st.rerun()
                if st.button('I checked: no upload exists. Return to queue', key='retry-' + c['id']):
                    with core.db() as con:
                        con.execute("UPDATE clips SET state='ready',error=NULL WHERE id=? AND state='check_upload'", (c['id'],))
                    st.rerun()

with settings_tab:
    st.subheader('Production and schedule')
    with st.form('configuration'):
        interval = st.selectbox('Check for new recordings every', [60, 180, 360, 720, 1440],
                                index=[60, 180, 360, 720, 1440].index(cfg['interval_minutes']),
                                format_func=lambda n: f'{n//60} hours')
        daily = st.number_input('Maximum new clips per 24 hours', 1, 10, cfg['daily_clip_limit'])
        length = st.number_input('Longest source recording to process (minutes)', 1, 360, cfg['max_source_minutes'])
        age = st.number_input('Only process recordings from the past (days)', 1, 365, cfg['max_age_days'])
        size = st.number_input('Download limit per recording (MB)', 100, 5000, cfg['max_download_mb'], step=100)
        model = st.selectbox('Speech recognition', ['tiny', 'base', 'small'],
                             index=['tiny', 'base', 'small'].index(cfg['model']),
                             help='Tiny is fastest. Small is more accurate but slower. First use downloads the free model.')
        framing = st.selectbox('Video framing', ['fit', 'crop'],
                               index=['fit', 'crop'].index(cfg.get('framing_mode', 'fit')),
                               format_func=lambda value: 'Show the full frame with black space' if value == 'fit' else 'Fill the screen by cropping',
                               help='Full frame preserves the entire picture; a wide source leaves black space for the hook, creator credit and captions.')
        auto = st.toggle('Automatically queue every finished clip for upload', value=cfg['auto_upload'])
        gap = st.number_input('Minimum hours between uploads', 1, 168, cfg['min_upload_hours'])
        privacy = st.selectbox('YouTube visibility', ['private', 'unlisted', 'public'],
                              index=['private', 'unlisted', 'public'].index(cfg['privacy']))
        st.caption('New, unaudited YouTube API projects can only upload privately. This version is for general-audience content, not made-for-kids channels.')
        if st.form_submit_button('Save settings'):
            core.configure(interval_minutes=interval, daily_clip_limit=daily, max_source_minutes=length,
                           max_age_days=age, max_download_mb=size, model=model, framing_mode=framing, auto_upload=auto,
                           min_upload_hours=gap, privacy=privacy)
            st.success('Settings saved.')
    st.subheader('Connect your destination YouTube channel')
    st.write('There is a one-time Google setup. Your sign-in is handled by Google; the program does not ask for your password.')
    with st.expander('One-time connection instructions'):
        st.markdown('''1. Open [Google Cloud Console](https://console.cloud.google.com/), create a project and enable **YouTube Data API v3**.
2. Configure Google Auth Platform / OAuth consent and add your Google account as a test user if the app is in testing.
3. Create an **OAuth client ID → Desktop app**, then download its JSON file.
4. Add that file below and choose **Connect YouTube**. Select your destination channel in Google's browser window.

Testing-mode consent can expire after seven days. A durable unattended connection may require changing your OAuth publishing status. Public API uploads require Google's separate compliance audit. See the included guide for official links.''')
    client = st.file_uploader('Google desktop-app connection file', type=['json'])
    if client and st.button('Save connection file'):
        try:
            value = json.loads(client.getvalue())
            if not all(value.get('installed', {}).get(k) for k in ('client_id', 'client_secret', 'auth_uri', 'token_uri')):
                raise ValueError('Choose the Desktop app OAuth JSON from Google, not a service-account key.')
            if value['installed']['auth_uri'] != 'https://accounts.google.com/o/oauth2/auth' or value['installed']['token_uri'] != 'https://oauth2.googleapis.com/token':
                raise ValueError('Connection file must use Google OAuth endpoints.')
            from youtube import save_private
            save_private(core.DATA / 'youtube-client.json', json.dumps(value))
            st.success('Connection file saved locally.')
        except Exception as exc:
            st.error(str(exc))
    if st.button('Connect YouTube', disabled=not (core.DATA / 'youtube-client.json').exists()):
        start('connect')
        st.info('A Google sign-in window will open. Return here and refresh after connecting.')
    st.caption('No paid APIs are configured. Processing uses your computer, internet and electricity.')
    st.subheader('TikTok posting')
    st.write('Finished clips have a download and ready-to-copy caption in the Clips tab. Open TikTok there to review and post from your own account.')
    st.caption('TikTok does not provide an approved hands-free publishing connection for this personal reposting utility. Its Direct Post API requires per-post review and consent, and unaudited clients are restricted to private posts.')

with activity:
    st.subheader('Activity and errors')
    for event in core.rows('SELECT * FROM events ORDER BY id DESC LIMIT 50'):
        st.write(f"{timestamp(event['created'])} — {event['message']}")
