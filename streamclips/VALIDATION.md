# StreamClips v0.2.3 — validation

## Passed

- v0.2.3 rendered local practice clips from Clavicular's Kick archive and Caedrel's Twitch archive with platform-specific badges. The excerpts were chosen after transcript review; the automatic hook selector did not produce the final hooks. Both previews were inspected visually, verified as decodable 720×1280 H.264/AAC with non-silent audio, and kept unposted. All 36 automated tests pass. See `PRACTICE_CLIPS.md` for source links and time windows.
- v0.2.2 preserves the normal capitalization of YouTube creator names in the on-video source credit (for example, Nick DiGiovanni and MrBeast). Hooks, dialogue captions, and post metadata remain lowercase. Re-rendered and visually checked two local, unposted practice clips.
- v0.2.1 lowercased added on-video text, moved colour emoji inline with the question, and placed animated captions directly below the full picture and the creator credit beneath them. All 36 automated tests passed, including a real FFmpeg render. Re-rendered the Nick DiGiovanni and MrBeast practice clips, inspected opening and mid-clip frames, and confirmed 720×1280 H.264/AAC output with non-silent audio. Both remained local and unposted.

- v0.2.0 replaces the on-video source title with a sentence-case hook and colour emoji above the footage, plus a creator credit and platform mark below it. The original source name is used in TikTok's prepared caption and YouTube's upload description. The upload title starts with the generated hook for new clips. All 36 automated tests pass, including real H.264/AAC rendering, new-clip metadata wiring, and the three source-platform badge variants.
- Rendered two local v0.2.0 practice videos using previously prepared footage from Nick DiGiovanni and MrBeast. Both decode as 720×1280 H.264/AAC, have non-silent audio, and were inspected at opening and mid-clip frames. These are local previews, not posted or entered into the upload queue.

- v0.1.9 selects a short opening hook from the chosen clip's own transcript, keeps the original source title, and limits each timed caption to three words and a short phone-screen line. Fixed highlight selection so stored transcript segments end with the selected clip rather than a later candidate window. All 30 automated tests pass, including a real FFmpeg render.
- Rendered two local v0.1.9 previews from previously downloaded, user-authorised creator footage: `data/clips/test-reel-v019-spicy-food.mp4` (29.5 seconds) and `data/clips/test-reel-v019-community.mp4` (27.7 seconds). Both decode as 720×1280 H.264/AAC with audible audio levels; inspected opening and mid-clip frames for title, hook, complete picture, and captions. The previews are not posted or added to the upload queue.

- 24 automated tests, including a real FFmpeg portrait render with captions and audio.
- Source URL validation; live/upcoming recording exclusion; popularity/recency ordering; repeated scans update rather than duplicate videos.
- Job locking; recovery from interrupted processing; uncertain uploads held instead of automatically retried; upload completion deduplication using mocked Google responses.
- Rolling daily production cap and pause during a source scan.
- Streamlit app rendering and settings submission through its application test harness.
- Live discovery against the user-provided YouTube channel: eight recent recordings returned.
- One full real source job: downloaded a roughly 19-minute recording, ran the local tiny speech model, selected a 27.66-second highlight, rendered a 720×1280 MP4 with audio and timed captions, and queued it as ready.
- Inspected extracted output frames, including a frame with readable rendered captions. Temporary recording downloads were cleaned up.
- Re-ran all 24 tests after updating the launcher to skip Streamlit's first-run email prompt; all passed.
- Opened the control panel in Chrome and verified version 0.1.1, one watched creator, one ready clip, paused automation, and private upload default.
- Added a dated, sourced creator catalog containing 20 YouTube, 20 Twitch, and 20 Kick primary channels plus six verified cross-platform matches. The local watchlist now has 66 unique sources. Re-ran all 24 tests and checked that the restarted panel displays the updated count.
- Installed and checked the per-user macOS login service; `launchctl` reports it running while automation remains paused. Restarted the panel and confirmed v0.1.3, 66 watched sources, one ready clip, and zero uploads. All 24 automated tests pass on v0.1.3.
- Verified and added Adin Ross's and IShowSpeed's Twitch accounts, bringing the catalog to 60 primary platform channels and eight additional cross-platform links. Deployed v0.1.4 with 68 unique watched sources.
- Live read-only checks returned two archived videos each from IShowSpeed on Twitch and Adin Ross on Kick. The login scheduler and local panel were restarted and verified running on v0.1.4.
- Added a per-clip TikTok handoff with MP4 download, an editable-by-copying caption, and a link to TikTok's upload page. No TikTok account is connected or background TikTok posting attempted.
- Opened TikTok Studio in Chrome and found an existing sign-in for @brandonshev; no file was uploaded. Verified the v0.1.5 Clips panel displays the download, caption and TikTok link for the sample clip. Corrected the sample source label to MrBeast.
- Refreshed all 68 sources and found 482 recordings. Produced a second captioned clip from a recent Stokes Twins recording; checked both clips contain sound and portrait video. The attempt to download an IShowSpeed recording returned HTTP 403 and was marked failed without making a clip.
- Fixed scheduled selection to favour each source's recent-first order when YouTube omits dates; a scheduled run can now try up to five candidates if earlier ones fail. All 26 automated tests pass, and the v0.1.6 scheduler was restarted with production enabled.
- Uploaded the MrBeast and Stokes Twins clips to their matching YouTube fan channels as private drafts. Both finished processing and YouTube reported no copyright-check issues. Public visibility is pending the required upload disclosures.
- Published both prepared Shorts on 1 October 2026 after completing the YouTube disclosures: Stokes Twins https://youtube.com/shorts/-P6QnlkZFIM and MrBeast https://youtube.com/shorts/voSkCsqCdqk. YouTube Studio confirmed publication for each.
- Updated the renderer for future clips: full-frame vertical crop, a four-second source-title banner, bold three-word captions with word-by-word highlighting, and normalised source audio. The two published Shorts were not modified.
- All 27 automated tests pass, including caption timing and original-title text. Rendered a new 29.5-second test reel from Nick DiGiovanni's “Cooking Every Level Of Spicy Food”; verified a decodable 720×1280 video with audio and inspected frames at 1, 7 and 15 seconds. The new reel remains local and ready for review, not uploaded.
- Added a default full-frame layout for wide recordings: the whole landscape picture remains visible between black top/bottom areas, which carry the source title and captions. The earlier crop layout remains selectable. Research examples and evidence limits are recorded in `STYLE_RESEARCH.md`.
- All 28 automated tests pass, including a real wide-source render that checks for black space above and below the visible picture and a second render showing the crop setting still fills the canvas. Rendered a new 29.5-second local full-frame preview from the same source, verified audio, dimensions, duration and decoding, and inspected its title, picture and captions at seven seconds. No public video was changed or posted.

## Not verified / known limits

- No API-based YouTube upload: a destination account has not been selected or connected in StreamClips. The YouTube Data API and Desktop OAuth client are enabled in Google Cloud project `deft-bazaar-509714-e2`; the user's Google account is a test user. Public API publishing can require a Google audit. The two manual YouTube Studio posts above are separate from that API workflow.
- Twitch and Kick were checked against one live source each; the remaining sources have not each been checked. Kick's undocumented recording-list endpoint may be blocked or change.
- Highlight quality is heuristic; it is not equivalent to OpusClip's semantic scene analysis. Tiny-model captions can contain mistakes, as seen in proper-name/word transcription in the sample.
- No monetisation, copyright-clearance, moderation or revenue validation is performed by the program.

## Handoff state

Sixty-eight sources configured, 482 recordings discovered, and two clips publicly posted to their matching fan channels. Scheduled clip production enabled at up to two clips per rolling 24 hours; auto-upload remains disabled because no YouTube access token or creator-specific channel routing is configured. New clips default to full-frame framing with black space. Default API visibility private. No paid services configured.
