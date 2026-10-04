import json
from pathlib import Path
import sys
import time
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core
import media
import worker
import youtube


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(core, 'DATA', tmp_path)
    core.init()


def seed():
    core.add_source('https://www.youtube.com/@authorised')
    with core.db() as con:
        con.execute("INSERT INTO videos(id,source_id,url,title,duration,score) VALUES ('youtube:a',1,'https://www.youtube.com/watch?v=a','Example',120,5)")


def clip():
    seed()
    path = core.DATA / 'clip.mp4'
    path.write_bytes(b'fixture')
    with core.db() as con:
        con.execute('INSERT INTO clips(id,video_id,title,start,end,score,path,transcript,state,created) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    ('clip', 'youtube:a', 'Example', 0, 30, 80, str(path), 'Example', 'ready', time.time()))


@pytest.mark.parametrize('url,platform', [
    ('https://www.youtube.com/channel/UC123', 'youtube'),
    ('https://www.youtube.com/@creator/videos', 'youtube'),
    ('https://www.twitch.tv/creator', 'twitch'),
    ('https://kick.com/creator', 'kick'),
])
def test_source_profiles(url, platform):
    assert core.source_url(url)[0] == platform


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'https://youtube.com.evil.test/@x',
                                  'http://127.0.0.1', 'https://youtube.com/watch?v=x',
                                  'https://user:secret@youtube.com/@x'])
def test_reject_invalid_sources(url):
    with pytest.raises(ValueError):
        core.source_url(url)


def test_rank_rewards_recent_popular_recordings():
    now = time.time()
    assert core.rank_video(10000, now-3600, now) > core.rank_video(100, now-3600, now)
    assert core.rank_video(10000, now-3600, now) > core.rank_video(10000, now-86400, now)


def test_live_recordings_excluded():
    assert core.normalize_entry({'id': 'a', 'is_live': True}, 'youtube') is None
    assert core.normalize_entry({'id': 'a', 'live_status': 'is_upcoming'}, 'youtube') is None


def test_scan_deduplicates_and_updates_views(monkeypatch):
    core.add_source('https://www.youtube.com/@test')
    entry = core.normalize_entry({'id': 'abc', 'title': 'Example', 'duration': 90, 'view_count': 10}, 'youtube')
    monkeypatch.setattr(core, 'discover', lambda _: [entry])
    core.scan()
    entry['views'] = 20
    core.scan()
    data = core.rows('SELECT * FROM videos')
    assert len(data) == 1 and data[0]['views'] == 20


def test_scan_prefers_newest_listed_video_when_dates_missing(monkeypatch):
    core.add_source('https://www.youtube.com/@test')
    first = core.normalize_entry({'id': 'recent', 'view_count': 100}, 'youtube')
    second = core.normalize_entry({'id': 'older', 'view_count': 1000000}, 'youtube')
    monkeypatch.setattr(core, 'discover', lambda _: [first, second])
    core.scan()
    ranked = core.rows('SELECT id FROM videos ORDER BY score DESC')
    assert [video['id'] for video in ranked] == ['youtube:recent', 'youtube:older']


def test_failure_visible_without_erasing_other_sources(monkeypatch):
    core.add_source('https://kick.com/test')
    def fail(_):
        raise RuntimeError('Access blocked')
    monkeypatch.setattr(core, 'discover', fail)
    core.scan()
    assert core.rows('SELECT error FROM sources')[0]['error'] == 'Access blocked'


def test_highlight_complete_within_limits():
    segments = [{'start': i*5, 'end': i*5+4.8,
                 'text': 'Why does this happen? Here is an interesting explanation.'} for i in range(16)]
    h = core.choose_highlight(segments)
    assert 25 <= h['end']-h['start'] <= 55.1
    assert h['segments'] and h['text']
    assert all(s['start'] < h['end'] for s in h['segments'])


def test_silent_video_held():
    with pytest.raises(ValueError, match='No clear spoken highlight'):
        core.choose_highlight([])


def test_subtitles_relative_and_escaped(tmp_path):
    h = {'start': 60, 'end': 90, 'segments': [{'start': 61, 'end': 64, 'text': '{bad}\\N caption'}]}
    file = tmp_path / 'clip.ass'
    media.write_subtitles(file, h)
    text = file.read_text()
    assert '0:00:01.00,0:00:04.00' in text
    assert '{bad}' not in text and '\\N' not in text


def test_creator_style_and_word_highlighting(tmp_path):
    h = {'start': 10, 'end': 14, 'segments': [{
        'start': 10, 'end': 12, 'text': 'hello world',
        'words': [
            {'start': 10.2, 'end': 10.6, 'text': 'hello'},
            {'start': 10.7, 'end': 11.1, 'text': 'world'},
        ],
    }]}
    file = tmp_path / 'clip.ass'
    media.write_subtitles(file, h)
    text = file.read_text()
    assert 'ORIGINAL VIDEO' not in text
    assert 'SourceTitle' not in text
    assert '0:00:00.20,0:00:00.70,Caption' in text
    assert '0:00:00.70,0:00:01.65,Caption' in text
    assert r'{\c&H0000D7FF&}hello' in text
    assert r'{\c&H0000D7FF&}world' in text
    assert r'\fscx95\fscy95' in text
    assert r'\fad(' in text


def test_hook_comes_from_clip_and_is_not_invented(tmp_path):
    h = {'start': 10, 'end': 21, 'text': 'So we started talking. He spent $500 on breakfast.',
         'segments': [
             {'start': 10, 'end': 13, 'text': 'So we started talking.'},
             {'start': 14, 'end': 18, 'text': 'He spent $500 on breakfast.'},
         ]}
    assert media.opening_hook(h) == 'would you spend $500 on breakfast? 💸🤯'
    file = tmp_path / 'hook.ass'
    media.write_subtitles(file, h)
    text = file.read_text()
    assert 'Would you spend $500' not in text
    assert 'Hook' not in text
    assert 'Original source title' not in text
    image = tmp_path / 'hook.png'
    media.hook_card(image, media.opening_hook(h))
    assert image.exists()


def test_broader_hook_grounded_in_selected_story():
    h = {'start': 0, 'end': 20, 'text': 'The community uses this bathroom. Sometimes you see snakes here.',
         'segments': [{'start': 0, 'end': 5, 'text': 'The community uses this bathroom.'},
                      {'start': 6, 'end': 10, 'text': 'Sometimes you see snakes here.'}]}
    assert media.opening_hook(h) == 'what was hiding in this bathroom? 🐍😳'


def test_emoji_drawn_inline_with_lowercase_question(tmp_path):
    from PIL import Image
    h = {'start': 0, 'end': 8, 'hook': 'what happened? 🐍😳', 'segments': []}
    ass = tmp_path / 'hook.ass'
    emoji = tmp_path / 'hook.png'
    media.write_subtitles(ass, h)
    media.hook_card(emoji, h['hook'])
    assert 'what happened?' not in ass.read_text()
    assert '🐍' not in ass.read_text()
    with Image.open(emoji) as picture:
        assert picture.getbbox() is not None
        assert picture.size == (720, 180)


@pytest.mark.parametrize('platform', ['youtube', 'twitch', 'kick'])
def test_platform_badge_is_transparent_with_source_icon(tmp_path, platform):
    from PIL import Image
    path = tmp_path / (platform + '.png')
    media.platform_badge(path, 'Example Creator', platform)
    with Image.open(path) as badge:
        assert badge.size == (720, 84)
        assert badge.getpixel((0, 0))[3] == 0
        assert any(badge.getpixel((x, 40))[3] for x in range(200, 520))


def test_caption_groups_stay_readable():
    words = [{'text': w} for w in ['extraordinary', 'breakfast', 'today', 'is', 'here']]
    groups = media.caption_groups(words)
    assert [[w['text'] for w in group] for group in groups] == [
        ['extraordinary'], ['breakfast', 'today'], ['is', 'here']]


def test_new_clip_uses_creator_badge_and_hook_upload_title(monkeypatch):
    seed()
    with core.db() as con:
        con.execute("UPDATE sources SET label='Example Creator' WHERE id=1")
    recording = core.rows('SELECT * FROM videos')[0]
    h = {'start': 0, 'end': 30, 'score': 50, 'text': 'He spent $500 on breakfast.',
         'segments': [{'start': 0, 'end': 4, 'text': 'He spent $500 on breakfast.'}]}
    monkeypatch.setattr(media, 'download', lambda _v, _cfg, folder: folder / 'source.mp4')
    monkeypatch.setattr(media, 'transcribe', lambda *_: [])
    monkeypatch.setattr(core, 'choose_highlight', lambda *_: h)
    calls = []
    def fake_render(source, highlight, destination, creator, platform, framing):
        calls.append((creator, platform, framing))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b'preview')
    monkeypatch.setattr(media, 'render', fake_render)
    media.make_clip(recording)
    clip = core.rows('SELECT * FROM clips')[0]
    assert calls == [('Example Creator', 'youtube', 'fit')]
    assert clip['title'].startswith('would you spend $500 on breakfast?')
    assert clip['title'].endswith('example creator')
    assert core.rows('SELECT title FROM videos')[0]['title'] == 'Example'


def test_video_subtitles_leave_hook_for_inline_graphic(tmp_path):
    h = {'start': 0, 'end': 12, 'hook': 'could this really happen? 👀', 'segments': []}
    fit = tmp_path / 'fit.ass'
    crop = tmp_path / 'crop.ass'
    media.write_subtitles(fit, h, 'fit', True)
    media.write_subtitles(crop, h, 'crop', True)
    assert 'Hook' not in fit.read_text()
    assert 'Hook' not in crop.read_text()
    assert 'SourceTitle' not in fit.read_text()


def test_recover_never_retries_uncertain_upload():
    clip()
    with core.db() as con:
        con.execute("UPDATE clips SET state='uploading'")
        con.execute("UPDATE videos SET state='processing'")
    worker.recover()
    assert core.rows('SELECT state FROM clips')[0]['state'] == 'check_upload'
    assert core.rows('SELECT state FROM videos')[0]['state'] == 'failed'


def test_lock_excludes_overlapping_jobs():
    with worker.lock() as first:
        with worker.lock() as second:
            assert first and not second


def test_daily_cap_prevents_processing(monkeypatch):
    clip()
    core.configure(enabled=True, daily_clip_limit=1)
    monkeypatch.setattr(core, 'scan', lambda: core.configure(last_scan=time.time()))
    process = MagicMock()
    monkeypatch.setattr(worker, 'process', process)
    worker.cycle()
    process.assert_not_called()


def test_pause_during_scan_prevents_processing(monkeypatch):
    seed()
    core.configure(enabled=True)
    monkeypatch.setattr(core, 'scan', lambda: core.configure(enabled=False, last_scan=time.time()))
    process = MagicMock()
    monkeypatch.setattr(worker, 'process', process)
    worker.cycle()
    process.assert_not_called()


def test_cycle_tries_next_candidate_after_ineligible_video(monkeypatch):
    seed()
    with core.db() as con:
        con.execute("INSERT INTO videos(id,source_id,url,title,duration,score) VALUES ('youtube:b',1,'https://www.youtube.com/watch?v=b','Recent',120,4)")
    core.configure(enabled=True, last_scan=0)
    monkeypatch.setattr(core, 'scan', lambda: core.configure(last_scan=time.time()))
    attempted = []
    def fake_process(video):
        attempted.append(video['id'])
        with core.db() as con:
            con.execute('UPDATE videos SET state=? WHERE id=?', ('failed' if video['id'] == 'youtube:a' else 'done', video['id']))
    monkeypatch.setattr(worker, 'process', fake_process)
    worker.cycle()
    assert attempted == ['youtube:a', 'youtube:b']


def test_upload_success_not_sent_twice(monkeypatch):
    clip()
    core.configure(channel_id='destination')
    api = MagicMock()
    api.channels.return_value.list.return_value.execute.return_value = {'items': [{'id': 'destination'}]}
    api.videos.return_value.insert.return_value.next_chunk.return_value = (None, {'id': 'uploaded123'})
    monkeypatch.setattr(youtube, 'credentials', lambda: object())
    monkeypatch.setattr('googleapiclient.discovery.build', lambda *a, **kw: api)
    youtube.upload('clip')
    body = api.videos.return_value.insert.call_args.kwargs['body']
    assert 'original video: example' in body['snippet']['description']
    assert core.rows('SELECT state FROM clips')[0]['state'] == 'uploaded'
    with pytest.raises(RuntimeError, match='already been uploaded'):
        youtube.upload('clip')
    assert api.videos.return_value.insert.call_count == 1


def test_upload_failure_requires_manual_reconciliation(monkeypatch):
    clip()
    core.configure(channel_id='destination')
    api = MagicMock()
    api.channels.return_value.list.return_value.execute.return_value = {'items': [{'id': 'destination'}]}
    api.videos.return_value.insert.return_value.next_chunk.side_effect = TimeoutError('Lost response')
    monkeypatch.setattr(youtube, 'credentials', lambda: object())
    monkeypatch.setattr('googleapiclient.discovery.build', lambda *a, **kw: api)
    with pytest.raises(TimeoutError):
        youtube.upload('clip')
    assert core.rows('SELECT state FROM clips')[0]['state'] == 'check_upload'


def test_render_actual_portrait_video(tmp_path):
    source = tmp_path / 'source.mp4'
    media.command(['-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30',
                   '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
                   '-t', '4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)])
    h = {'start': .5, 'end': 3.5, 'segments': [{'start': .5, 'end': 3.5, 'text': 'Captions are working.'}]}
    output = tmp_path / 'render.mp4'
    media.render(source, h, output, 'Example Creator', 'youtube', 'fit')
    media.verify(output, 3)
    assert output.stat().st_size > 10000
    import av
    with av.open(str(output)) as container:
        frame = next(container.decode(video=0)).to_ndarray(format='rgb24')
    assert frame[320, 360].max() < 20  # black above the complete wide picture
    assert frame[600, 360].max() > 100  # source footage remains visible in the middle
    assert frame[950, 10].max() < 20   # black below it

    cropped = tmp_path / 'cropped.mp4'
    media.render(source, h, cropped, 'Example Creator', 'youtube', 'crop')
    media.verify(cropped, 3)
    with av.open(str(cropped)) as container:
        frame = next(container.decode(video=0)).to_ndarray(format='rgb24')
    assert frame[320, 360].max() > 100  # crop mode fills the same position


def test_control_panel_loads_and_saves():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(core.ROOT / 'app.py')).run(timeout=20)
    assert not app.exception
    assert [t.label for t in app.tabs] == ['Creators', 'Recordings', 'Clips', 'Settings', 'Activity']
    for button in app.button:
        if button.label == 'Save settings':
            button.click().run()
            break
    assert not app.exception
