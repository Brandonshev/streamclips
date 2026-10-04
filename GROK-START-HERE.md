# Grok handoff v1.0.2 — StreamClips v0.2.3

Grok Bot is now the primary operational contact; Codex remains the development contact. Read PRIMARY-CONTACT-AND-UPDATES.md for the shared repository and automatic release deployment requirements.

Read streamclips/README.md, VALIDATION.md and STYLE_RESEARCH.md first. This archive contains source, the 68-source watchlist/catalog and four approved-style practice examples. It contains no credentials, tokens, private password tables, runtime database or downloaded source recordings.

Goal: install and validate StreamClips on Grok Bot's cloud computer, then automate authorised creator clip production on a schedule without requiring the Mac to stay awake. Use free local transcription and rendering; do not purchase services or add paid API dependencies. Ask before any unavoidable cost.

Adapt macOS-only font paths, emoji rendering, launcher and launchctl scheduler for the cloud OS. Keep the approved full-picture layout with black space, soft lowercase hooks with inline emoji, animated lowercase dialogue captions below the footage, and creator/platform credit below the captions. YouTube creator credits retain normal capitalization; Twitch/Kick credits are lowercase. Preserve original source titles in post metadata. The practice hooks and moments were manually chosen after transcript review; they do not prove the automatic selector matches that quality.

Run the existing tests and make one local end-to-end sample per source platform. Validate sound, captions, logos, dimensions and intelligible grounded hooks. Keep at most two new clips per rolling 24 hours and discovery every six hours, timezone Australia/Sydney. Use one scheduler, persistent state, deduplication and job locks. Confirm that cloud runtime/storage/usage limits allow reliable scheduled runs; do not claim 24/7 service without verifying the execution model.

The source handoff is not a configured uploader. YouTube has no connected destination token in this archive; creator-specific channel routing is not implemented. Ask which destination to use and connect through a secure login/OAuth flow. TikTok is currently a prepared-video/caption handoff, not an automatic publisher. Do not label AI-assisted work as AI-free or fabricate platform disclosures.

Before enabling cloud production, obtain the existing nonsecret processing/upload history from the user or the current operator to prevent duplicate processing/posting. Confirm two manual public posts recorded in VALIDATION.md are excluded. Do not stop or alter the Mac scheduler until the cloud test succeeds and the user confirms cutover. Never run both schedulers against independent copies of the same watchlist without coordinated deduplication.

Create a routine after testing. Notify only for meaningful failures, required login/verification, or completed setup; stay quiet on unchanged routine checks. Maintain version numbers for deployments and document the actual remaining limitations.

Use Scout AUTOMATION.md as a reference for automatically publishing source changes, not as a working cloud updater. PRIMARY-CONTACT-AND-UPDATES.md explains the additional Grok receiver and deployment steps. StreamClips needs its own public repository.
