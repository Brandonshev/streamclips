# StreamClips v0.2.3

A local program for watching authorised creators, selecting spoken highlights, creating captioned vertical clips, and queuing uploads to your YouTube channel. No paid API keys, Zapier subscription or cloud rendering service is used.

The v0.2.3 practice set adds one local Kick sample from Clavicular and one local Twitch sample from Caedrel. Their source links, selected time windows, and review notes are in [PRACTICE_CLIPS.md](PRACTICE_CLIPS.md). The rendering code is unchanged from v0.2.2.

Finished clips can also be downloaded with a ready-to-copy caption from **Clips → Post this clip to TikTok**. This opens TikTok's upload page for you to review and post from your own account. StreamClips is not connected to a TikTok account and does not automatically post there.

## Open it

On this Mac, double-click **Start StreamClips.command**. The control panel opens at **http://127.0.0.1:8765**. The free dependencies are already installed in this copy. Keep the terminal window open while using the panel.

Your requested creators and the researched platform lists are in the watchlist. The dated selection and ranking sources are in [creator-catalog.json](creator-catalog.json). Scheduled clip production is enabled on this Mac; automatic uploading is disabled. Two earlier clips were posted manually to their matching YouTube fan channels.

1. Open **Recordings**, expand a recording, and choose **Make a clip**. The first transcription may download a free speech model. Processing a long recording can take several minutes or longer.
2. Open **Clips** after refreshing. Preview the result and edit its upload title.
3. Connect your destination in **Settings**, following the one-time Google instructions below.
4. Set your upload visibility and schedule. Use **Start automation** to run recurring discovery and clipping.
5. To publish without reviewing each clip, enable **Automatically queue every finished clip for upload**. Otherwise select **Save title and queue upload** for each clip you want uploaded.

The scheduler runs in the background while your Mac is awake. A per-user login service restarts it when you sign in to the Mac. Closing the page does not pause it. Use **Pause automation** before closing if you want processing to stop. A clip already processing may finish, but the worker rechecks pause before starting another scheduled upload. An upload already in flight may complete. The Mac must be awake and signed in for scheduled work to run.

## What it does

- Watches the eight most recent recordings returned by each enabled source. YouTube channels and Twitch archived-video profiles use yt-dlp. Kick's recording-list adapter is experimental and reports errors when unavailable.
- Prioritises recordings using a transparent view-count/recency score and the source's recent-first listing order when timestamps are missing. Download checks enforce the recording age and duration metadata; a scheduled run can try up to five candidates when earlier ones are ineligible.
- Downloads a recording at up to 720p with size/duration limits. It does not record live streams, remove access controls, or scrape browser cookies.
- Transcribes speech locally using faster-whisper. Selects one 25–55 second spoken passage per recording based on speech density, pace, vocabulary and opening words. This is a heuristic, not an AI judgement of the funniest or most viral moment.
- Produces a 720×1280 H.264/AAC MP4 with normalised source audio and lowercase, word-highlighted captions in a softer font. Each caption phrase gently fades and grows into place. The default **Show the full frame with black space** layout preserves a wide recording in the middle, puts a concise lowercase question or reaction with colour emoji on the same line above it, places captions directly below the footage, and credits the creator name beside a YouTube, Twitch, or Kick mark beneath the captions. YouTube creator names keep their usual capitalization; other source credits, hooks, and dialogue captions remain lowercase. The original recording title is kept in the TikTok caption and YouTube description, not burned into the video. **Fill the screen by cropping** remains available in Settings; it shows the hook briefly over the picture. Hook writing is a free transcript-based heuristic and can inherit speech-recognition mistakes; review before posting. It does not track faces, remove all internal silences, generate commentary, or add editorial context.
- Stores completed clip/transcript files, removes temporary source downloads, checks output dimensions/audio/duration, and retains an activity log.
- Defaults to one production opportunity every six hours, at most two new clips per rolling 24 hours, and at least 12 hours between uploads. Manual clip requests bypass the daily production cap. Intervals are relative to successful scans/uploads, not fixed wall-clock posting times.
- Keeps deduplication records and uses exclusive job locks. An interrupted upload goes into **check_upload**, which requires checking YouTube Studio before retrying. This avoids automatically creating duplicates when the upload result is uncertain.

## One-time YouTube connection

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable **YouTube Data API v3**.
2. Configure OAuth consent in Google Auth Platform. If the app is in testing, add the account that owns the destination YouTube channel as a test user.
3. Create an OAuth client of type **Desktop app**, then download its JSON configuration.
4. In StreamClips **Settings**, upload the JSON and choose **Save connection file**, then **Connect YouTube**.
5. Complete Google's browser sign-in and choose the correct channel. Refresh StreamClips and verify the channel name in the sidebar.

Tokens and the connection file are stored locally with owner-only file permissions. Do not share the `data` folder. The program uses upload and channel-read scopes; it never asks for a Google password. In testing mode, Google can expire refresh tokens after seven days. Longer-lived use may require moving OAuth consent out of testing and meeting Google's applicable requirements.

**Public publishing has a separate Google requirement:** uploads from new unaudited API projects are restricted to private visibility. Selecting public in this program cannot override that. See [YouTube upload requirements](https://developers.google.com/youtube/v3/docs/videos/insert) and [OAuth token expiration](https://developers.google.com/identity/protocols/oauth2#expiration). Two clips were posted manually through YouTube Studio; API publishing remains untested because no destination account is connected.

This release sets uploads to general-audience / not made for kids. Do not use it for a made-for-kids channel without changing that setting in the implementation. Clips are credited and linked to their original recordings, based on your confirmation that the selected creators authorise reposting.

Permission does not itself guarantee monetisation; captioned excerpts may still fall under YouTube's [reused-content policy](https://support.google.com/youtube/answer/1311392?hl=en). There is no revenue or virality guarantee.

## TikTok posting limit

TikTok's [Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines) say its Direct Post API is intended for authentic creators sharing original content, and specifically disallow a personal utility for uploading to accounts you manage or copying arbitrary material from other platforms. The same guidelines require creator information, a video preview, manually selected privacy and interaction settings, and express consent before each upload. Unaudited API clients are limited to private posts. For this use case, StreamClips therefore prepares the video and caption for a post you complete in TikTok; it does not offer a background TikTok uploader or claim to be linked to your account.

## Free does not mean unlimited

The program has no subscription or paid model/API dependency. It still uses your bandwidth, disk space, electricity and computer. Tiny speech recognition is relatively quick but can mishear names and accents. Select base or small for improved accuracy at the cost of speed. Automatic content moderation, copyright checks, sponsorship filtering, and advanced editorial selection are not included.

YouTube/Twitch/Kick can change their formats or limit access. Source access failures are shown in the app rather than treated as successful scans. Kick has no stable documented VOD-list interface used here. Twitch and Kick have not been verified against a user-provided account yet.

Finished clips are retained until you remove them from disk. Discard hides a clip from the upload queue but keeps its file. Processing stops when free disk space drops below 3 GB. Do not expose this local control panel to the internet.

## Installation on another Mac

Use Python 3.12 or 3.13 and a supported Node.js runtime (Node 22+ recommended for YouTube extraction). The launcher can use the bundled Codex Python when present. Otherwise install Python first, then double-click the launcher. FFmpeg is supplied by imageio-ffmpeg. First setup requires an internet connection to download free packages and speech models.

To install the same sign-in scheduler on another Mac, run `.venv/bin/python autostart.py install` after installing dependencies. Run `.venv/bin/python autostart.py uninstall` to remove it.

For a terminal setup:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python launch.py
```

## Maintenance and testing

```sh
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

The tests cover source validation, ranking, duplicate discovery, silent-recording rejection, timed captions, platform marks, emoji rendering, original-title credit in the upload description, interrupted jobs, upload state transitions with mocked Google responses, daily limits, pause behaviour, a real FFmpeg render, and the Streamlit control panel. Automated API uploads require your connected account and have not been performed.

Version is recorded in `VERSION` and `core.VERSION`. Increment both for each new deployment. Keep `.venv`, `data`, tokens and working files out of shared archives and source control.
