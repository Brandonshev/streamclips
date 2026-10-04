"""Local downloading, transcription, caption timing and vertical rendering."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import textwrap
import time

import core


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def command(args, timeout=1800, cwd=None):
    result = subprocess.run([ffmpeg(), '-hide_banner', '-loglevel', 'error', '-y', *args],
                            capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if result.returncode:
        raise RuntimeError('Video processing failed: ' + result.stderr[-1600:])


def download(video, cfg, folder):
    from yt_dlp import YoutubeDL
    if shutil.disk_usage(core.DATA).free < 3 * 1024**3:
        raise RuntimeError('At least 3 GB of free disk space is needed before downloading.')
    cap = cfg['max_download_mb'] * 1024**2

    def size_guard(progress):
        if progress.get('downloaded_bytes', 0) > cap:
            raise RuntimeError('Recording exceeded the download size limit.')

    options = {
        'quiet': True, 'no_warnings': True, 'noprogress': True, 'noplaylist': True,
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        'outtmpl': str(folder / 'source.%(ext)s'), 'merge_output_format': 'mp4',
        'ffmpeg_location': ffmpeg(), 'max_filesize': cap, 'socket_timeout': 25,
        'retries': 2, 'fragment_retries': 2, 'progress_hooks': [size_guard],
    }
    options.update(core.javascript_options())
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(video['url'], download=False)
        if not info or info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming', 'post_live'):
            raise RuntimeError('This recording is still live or not yet available.')
        length = info.get('duration')
        if not length or length > cfg['max_source_minutes'] * 60:
            raise RuntimeError('Recording length is unknown or exceeds the selected duration limit.')
        date = info.get('timestamp') or info.get('release_timestamp')
        if date and date < time.time() - cfg['max_age_days'] * 86400:
            raise RuntimeError('Recording is older than your selected age limit.')
        ydl.process_info(info)
    files = [p for p in folder.glob('source.*') if p.suffix in ('.mp4', '.mkv', '.webm', '.mov')]
    if not files:
        raise RuntimeError('No recording downloaded. It may exceed the size limit or require access.')
    if sum(p.stat().st_size for p in files) > cap * 1.1:
        raise RuntimeError('Combined recording exceeds the download limit.')
    return max(files, key=lambda p: p.stat().st_size)


def transcribe(path, model='tiny'):
    from faster_whisper import WhisperModel
    speech = WhisperModel(model, device='cpu', compute_type='int8',
                          download_root=str(core.DATA / 'models'), cpu_threads=4)
    segments, info = speech.transcribe(str(path), beam_size=3, vad_filter=True, word_timestamps=True)
    result = []
    for s in segments:
        if s.no_speech_prob > .8 or s.avg_logprob < -1.5:
            continue
        result.append({'start': s.start, 'end': s.end, 'text': s.text,
                       'words': [{'start': w.start, 'end': w.end, 'text': w.word}
                                 for w in (s.words or [])]})
    return result


def ass_time(seconds):
    centiseconds = round(max(0, seconds) * 100)
    hours, rest = divmod(centiseconds, 360000)
    minutes, rest = divmod(rest, 6000)
    seconds, cs = divmod(rest, 100)
    return f'{hours}:{minutes:02d}:{seconds:02d}.{cs:02d}'


def subtitle_text(text):
    return re.sub(r'[\x00-\x1f]', ' ', text).replace('\\', '').replace('{', '').replace('}', '').strip()


def opening_hook(highlight):
    """Build a concise, grounded question or reaction from the selected speech."""
    transcript = subtitle_text(highlight.get('text') or ' '.join(
        s['text'] for s in highlight['segments'] if s['start'] < highlight['end']))
    lower_transcript = transcript.lower()
    if 'bathroom' in lower_transcript and re.search(r'\bsnakes?\b', lower_transcript):
        return 'what was hiding in this bathroom? 🐍😳'
    pepper = re.search(r'\b(\d{3,})\s+jalapenos?\s+in one bite\b', transcript, re.I)
    if pepper:
        return f'could you handle {pepper.group(1)} jalapeños in one bite? 🌶️😳'
    origin = highlight['start']
    candidates = []
    for segment in highlight['segments']:
        if segment['start'] >= highlight['end']:
            break
        for sentence in re.split(r'(?<=[!?\.])\s+|,\s+', subtitle_text(segment['text'])):
            sentence = sentence.strip(' ,;:-')
            # A number-led phrase is usually more concrete than its filler lead-in.
            number = re.search(r'\b\d{3,}\b', sentence)
            if number and number.start() > 14 and '$' not in sentence:
                sentence = sentence[number.start():]
            words = sentence.split()
            if not 4 <= len(words) <= 11 or len(sentence) > 68:
                continue
            lower = sentence.lower()
            score = 0
            score += 11 if re.search(r'\$|\b\d{3,}\b', sentence) else (4 if re.search(r'\d', sentence) else 0)
            score += 4 if sentence.endswith('?') else 0
            score += 3 if re.search(r'\b(record|secret|never|impossible|dangerous|million|why|how)\b', lower) else 0
            score -= min(5, (segment['start'] - origin) / 3)
            score -= 3 if re.match(r'(?i)^(so|well|um|uh|like)\b', sentence) else 0
            candidates.append((score, -segment['start'], sentence))
    if candidates:
        chosen = max(candidates)[2]
    else:
        chosen = ' '.join(transcript.split()[:8]).rstrip(' ,;:')
    if not chosen:
        return ''
    spent = re.search(r'\bspent\s+(\$[\d,]+)\s+on\s+([^.!?]+)', chosen, re.I)
    if spent:
        return f'would you spend {spent.group(1)} on {spent.group(2).strip().lower()}? 💸🤯'
    reaction = re.match(r"i can['’]?t believe\s+(.+)", chosen, re.I)
    if reaction:
        chosen = reaction.group(1).rstrip('.!?') + '?!'
    elif not chosen.endswith('?'):
        chosen = chosen.rstrip('.!') + '?!' if re.search(r'\d|\$|\b(never|impossible|dangerous|shocking)\b', chosen, re.I) else chosen.rstrip('.') + '?'
    emoji = ('🌶️😳' if re.search(r'pepper|spicy|jalapeño', chosen, re.I) else
             '💸🤯' if re.search(r'\$|money|million', chosen, re.I) else
             '😂👀' if re.search(r'funny|laugh|joke', chosen, re.I) else '👀😳')
    return chosen.lower() + ' ' + emoji



def _existing_font(*paths):
    """First font file that exists. Mac paths are listed before Linux fallbacks."""
    for path in paths:
        if Path(path).is_file():
            return path
    raise OSError('cannot open resource')


_BADGE_FONTS = (
    '/System/Library/Fonts/Avenir Next.ttc',
    '/System/Library/Fonts/Helvetica.ttc',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
)
_HOOK_FONTS = (
    '/System/Library/Fonts/HelveticaNeue.ttc',
    '/System/Library/Fonts/Helvetica.ttc',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
)
# Noto Color Emoji is a CBDT font whose only Pillow strike is 109px.
_NOTO_EMOJI = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'
_NOTO_EMOJI_STRIKE = 109
_HOOK_EMOJI_PX = 32


def _caption_fontname():
    """Helvetica Neue only when that family is installed; else a sans fontconfig resolves."""
    if Path('/System/Library/Fonts/HelveticaNeue.ttc').is_file() or Path('/Library/Fonts/HelveticaNeue.ttc').is_file():
        return 'Helvetica Neue'
    try:
        listed = subprocess.check_output(['fc-list', 'Helvetica Neue', 'family'], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        listed = ''
    names = {part.strip() for line in listed.splitlines() for part in line.split(',')}
    if 'Helvetica Neue' in names:
        return 'Helvetica Neue'
    if Path('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf').is_file():
        return 'Liberation Sans'
    if Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').is_file():
        return 'DejaVu Sans'
    return 'Helvetica Neue'


def _hook_emoji(text):
    """Return (font, sprite). Apple Color Emoji draws inline at the hook size.
    Noto Color Emoji cannot; draw its 109px strike and scale it to the hook size."""
    from PIL import Image, ImageDraw, ImageFont
    apple = '/System/Library/Fonts/Apple Color Emoji.ttc'
    if Path(apple).is_file():
        return ImageFont.truetype(apple, _HOOK_EMOJI_PX), None
    if not text or not Path(_NOTO_EMOJI).is_file():
        return None, None
    font = ImageFont.truetype(_NOTO_EMOJI, _NOTO_EMOJI_STRIKE)
    bbox = ImageDraw.Draw(Image.new('RGBA', (4, 4))).textbbox((0, 0), text, font=font)
    pad = 4
    tile = Image.new('RGBA', (max(1, int(bbox[2] - bbox[0]) + pad * 2), max(1, int(bbox[3] - bbox[1]) + pad * 2)), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((pad - bbox[0], pad - bbox[1]), text, font=font, embedded_color=True)
    scale = _HOOK_EMOJI_PX / tile.height
    sprite = tile.resize((max(1, round(tile.width * scale)), _HOOK_EMOJI_PX), Image.Resampling.LANCZOS)
    return None, sprite


def platform_badge(path, creator, platform):
    """Draw a small source-platform mark and creator credit on a transparent strip."""
    from PIL import Image, ImageDraw, ImageFont
    if platform not in ('youtube', 'twitch', 'kick'):
        raise ValueError('Unsupported source platform for the video badge.')
    canvas = Image.new('RGBA', (720, 84), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(_existing_font(*_BADGE_FONTS), 39)
    name = subtitle_text(creator).strip()[:28] or platform
    if platform != 'youtube':
        name = name.lower()
    while draw.textbbox((0, 0), name, font=font)[2] > 550 and len(name) > 8:
        name = name[:-2].rstrip() + '…'
    width = draw.textbbox((0, 0), name, font=font)[2]
    left = (720 - width - 82) // 2
    if platform == 'youtube':
        draw.rounded_rectangle((left, 20, left + 59, 61), radius=11, fill='#FF0033')
        draw.polygon([(left + 25, 29), (left + 25, 52), (left + 44, 40)], fill='white')
    elif platform == 'twitch':
        draw.polygon([(left + 5, 17), (left + 61, 17), (left + 61, 57),
                      (left + 38, 57), (left + 25, 69), (left + 25, 57),
                      (left + 5, 57)], fill='#9146FF')
        draw.rectangle((left + 14, 25, left + 52, 49), fill='white')
        draw.rectangle((left + 27, 29, left + 33, 43), fill='#9146FF')
        draw.rectangle((left + 40, 29, left + 46, 43), fill='#9146FF')
    else:
        kick_font = ImageFont.truetype(_existing_font(*_BADGE_FONTS), 25)
        draw.rounded_rectangle((left, 18, left + 67, 62), radius=6, fill='#111111')
        draw.text((left + 5, 22), 'kick', font=kick_font, fill='#53FC18')
    draw.text((left + 82, 17), name, font=font, fill='white', stroke_width=1, stroke_fill='black')
    canvas.save(path)


def hook_card(path, hook):
    """Draw lowercase hook text and colour emoji together on the final line."""
    from PIL import Image, ImageDraw, ImageFont
    canvas = Image.new('RGBA', (720, 180), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    emoji = ''.join(re.findall(r'[\U0001F000-\U0010FFFF]\ufe0f?', hook))
    plain = re.sub(r'[\U0001F000-\U0010FFFF]\ufe0f?', '', subtitle_text(hook)).strip().lower()
    if not plain:
        canvas.save(path)
        return
    plain = textwrap.shorten(plain, width=72, placeholder='…')
    emoji_font, emoji_sprite = _hook_emoji(emoji) if emoji else (None, None)
    emoji_width = draw.textlength(emoji, font=emoji_font) if emoji_font else (emoji_sprite.width if emoji_sprite else 0)
    for size in range(46, 33, -2):
        font = ImageFont.truetype(_existing_font(*_HOOK_FONTS), size)
        words = plain.split()
        full_width = draw.textlength(plain, font=font)
        if full_width + emoji_width + 14 <= 620:
            lines = [plain]
            break
        options = []
        for split in range(1, len(words)):
            first = ' '.join(words[:split])
            second = ' '.join(words[split:])
            w1 = draw.textlength(first, font=font)
            w2 = draw.textlength(second, font=font) + emoji_width + 14
            if max(w1, w2) <= 620:
                options.append((abs(w1-w2), [first, second]))
        if options:
            lines = min(options, key=lambda item: item[0])[1]
            break
    else:
        lines = [textwrap.shorten(plain, width=42, placeholder='…')]
        font = ImageFont.truetype(_existing_font(*_HOOK_FONTS), 34)
    y = 52 if len(lines) == 1 else 28
    for index, line in enumerate(lines):
        width = draw.textlength(line, font=font)
        last = index == len(lines)-1
        group_width = width + (emoji_width + 14 if last and (emoji_font or emoji_sprite) else 0)
        x = (720 - group_width) / 2
        draw.text((x, y), line, font=font, fill='white')
        if last and emoji_font:
            draw.text((x + width + 14, y + 9), emoji, font=emoji_font, embedded_color=True)
        elif last and emoji_sprite:
            canvas.alpha_composite(emoji_sprite, (int(x + width + 14), int(y + 9)))
        y += 62
    canvas.save(path)


def caption_groups(words):
    """Limit each caption to three words and roughly one phone-screen line."""
    groups, group = [], []
    for word in words:
        clean = subtitle_text(word['text'])
        if group and (len(group) == 3 or len(' '.join(subtitle_text(w['text']) for w in group)) + len(clean) + 1 > 17):
            groups.append(group)
            group = []
        group.append(word)
    if group:
        groups.append(group)
    return groups


def write_subtitles(path, highlight, framing_mode='fit', source_is_wide=True):
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,CAPTION_FONT,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H70000000,0,0,0,0,100,100,0,0,1,4,0,2,50,50,CAPTION_MARGIN,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    if framing_mode not in ('fit', 'crop'):
        raise ValueError('Framing must be fit or crop.')
    header = header.replace('CAPTION_MARGIN', '305').replace('CAPTION_FONT', _caption_fontname())
    events = []
    origin, end = highlight['start'], highlight['end']
    words = [word for seg in highlight['segments'] for word in seg.get('words', [])
             if origin <= word['start'] < end and subtitle_text(word['text'])]
    if words:
        groups = caption_groups(words)
        for group_index, group in enumerate(groups):
            next_group_start = (groups[group_index + 1][0]['start']
                                if group_index + 1 < len(groups) else end)
            for index, word in enumerate(group):
                start = max(origin, word['start'])
                next_start = group[index + 1]['start'] if index + 1 < len(group) else next_group_start
                stop = min(end, next_start, max(word['end'], start + .08) + .55)
                if stop <= start:
                    continue
                phrase = []
                for position, part in enumerate(group):
                    cleaned = subtitle_text(part['text']).lower()
                    if position == index:
                        cleaned = r'{\c&H0000D7FF&}' + cleaned + r'{\c&H00FFFFFF&}'
                    phrase.append(cleaned)
                animation = ''
                if index == 0:
                    duration_ms = round((stop-start)*1000)
                    fade_ms = min(75, max(20, duration_ms//4))
                    pop_ms = min(150, max(60, duration_ms//2))
                    animation = rf'{{\fscx95\fscy95\t(0,{pop_ms},\fscx100\fscy100)\fad({fade_ms},0)}}'
                events.append(f'Dialogue: 1,{ass_time(start-origin)},{ass_time(stop-origin)},Caption,,0,0,0,,{animation}{" ".join(phrase)}')
    else:
        for seg in highlight['segments']:
            start, stop = max(origin, seg['start']), min(end, seg['end'])
            caption = subtitle_text(seg['text']).lower()
            if stop > start and caption:
                events.append(f'Dialogue: 1,{ass_time(start-origin)},{ass_time(stop-origin)},Caption,,0,0,0,,{{\fscx95\fscy95\t(0,150,\fscx100\fscy100)\fad(75,0)}}{caption}')
    path.write_text(header + '\n'.join(events) + '\n', encoding='utf-8')


def render(source, highlight, destination, creator='', platform='youtube', framing_mode='fit'):
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    subtitle = destination.with_suffix('.ass')
    badge = destination.with_suffix('.badge.png')
    hook_image = destination.with_suffix('.hook.png')
    import av
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        source_is_wide = stream.width / stream.height >= 1.3
    write_subtitles(subtitle, highlight, framing_mode, source_is_wide)
    platform_badge(badge, creator, platform)
    hook_card(hook_image, highlight.get('hook') or opening_hook(highlight))
    # Use a relative, generated basename so filenames never enter filter syntax unescaped.
    if not re.fullmatch(r'[a-zA-Z0-9_-]+\.ass', subtitle.name):
        raise ValueError('Render output name must use letters, numbers, underscores or hyphens.')
    if framing_mode == 'fit':
        framing = ('scale=720:1280:force_original_aspect_ratio=decrease,'
                   'pad=720:1280:(ow-iw)/2:(oh-ih)/2:black')
    else:
        framing = ('scale=720:1280:force_original_aspect_ratio=increase,'
                   'crop=720:1280')
    box = ('' if framing_mode == 'fit' and source_is_wide else
           "drawbox=x=24:y=65:w=672:h=225:color=black@0.68:t=fill:enable='lt(t,4.5)',")
    badge_y = 1085
    hook_y = 96 if framing_mode == 'fit' and source_is_wide else 60
    hook_enable = '' if framing_mode == 'fit' and source_is_wide else ":enable='lt(t,4.5)'"
    filters = ('[0:v]' + framing + ',setsar=1,' + box + f'ass={subtitle.name}[base];'
               + f'[base][1:v]overlay=0:{badge_y}:format=auto[badged];'
               + f'[badged][2:v]overlay=0:{hook_y}:format=auto{hook_enable}[v]')
    command(['-ss', str(highlight['start']), '-i', str(Path(source).resolve()),
             '-loop', '1', '-i', str(badge), '-loop', '1', '-i', str(hook_image),
             '-t', str(highlight['end'] - highlight['start']), '-filter_complex', filters,
             '-map', '[v]', '-map', '0:a:0', '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',
             '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p',
             '-r', '30', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
             str(destination)], cwd=destination.parent)
    verify(destination, highlight['end'] - highlight['start'])


def verify(path, expected_duration):
    import av
    with av.open(str(path)) as container:
        if not container.streams.video or not container.streams.audio:
            raise RuntimeError('Rendered clip is missing its picture or audio track.')
        v = container.streams.video[0]
        if (v.width, v.height) != (720, 1280):
            raise RuntimeError('Rendered clip has the wrong dimensions.')
        actual = (container.duration or 0) / 1_000_000
        if abs(actual - expected_duration) > 1.5:
            raise RuntimeError('Rendered clip duration does not match the selected highlight.')
        if next(container.decode(video=0), None) is None:
            raise RuntimeError('Rendered clip cannot be decoded.')


def make_clip(video):
    cfg = core.settings()
    folder = core.DATA / 'work' / core.clip_id(video['id'], 0, 0)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        core.configure(job='Downloading: ' + video['title'])
        source_info = core.rows('SELECT label,platform FROM sources WHERE id=?', (video['source_id'],))[0]
        source = download(video, cfg, folder)
        core.configure(job='Finding spoken highlights: ' + video['title'])
        segments = transcribe(source, cfg['model'])
        highlight = core.choose_highlight(segments, cfg['min_clip_seconds'], cfg['max_clip_seconds'])
        highlight['hook'] = opening_hook(highlight)
        cid = core.clip_id(video['id'], highlight['start'], highlight['end'])
        destination = core.DATA / 'clips' / (cid + '.mp4')
        core.configure(job='Rendering vertical clip: ' + video['title'])
        render(source, highlight, destination, source_info['label'], source_info['platform'], cfg['framing_mode'])
        destination.with_suffix('.json').write_text(json.dumps(highlight, indent=2), encoding='utf-8')
        with core.db() as con:
            con.execute('''INSERT OR IGNORE INTO clips
            (id,video_id,title,start,end,score,path,transcript,state,created)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
                        (cid, video['id'], (highlight['hook'] + ' | ' + source_info['label']).lower()[:90], highlight['start'], highlight['end'],
                         highlight['score'], str(destination), highlight['text'], 'ready', time.time()))
            con.execute("UPDATE videos SET state='done',error=NULL WHERE id=?", (video['id'],))
        core.log('Clip ready: ' + video['title'])
        return cid
    finally:
        # The finished clip/transcript remain. Large source files and partial downloads do not.
        shutil.rmtree(folder, ignore_errors=True)
