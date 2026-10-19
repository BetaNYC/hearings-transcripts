# New-hearing checklist

Every stage from a Legistar event id to a published hearing folder. Commands and file formats
for the scripted stages are in [`scripts/README.md`](../scripts/README.md). Stages marked
**manual** have no script; they are done by a person working with AI assistants.

Set two names first:

```sh
SLUG=2026-10-16-technology-ai                              # <date>-<body>-<topic>
D=~/Movies/BetaNYC/council-hearings/$SLUG                  # raw files; never inside the repo
```

## 1. Legistar documents (scripted)

- [ ] Find the event id on the Council's Legistar calendar (`MeetingDetail.aspx?LEGID=<id>`).
- [ ] `python3 scripts/fetch_legistar.py <id> --out "$D/legistar"` (needs `LEGISTAR_TOKEN`).
- [ ] Read `$D/legistar/README.md`: agenda items, attachments, and whether `Video` is filled in.
      The committee report usually names the invited witnesses.
- [ ] Re-run a day or more after the hearing, into a dated subfolder, to collect testimony and
      transcripts the Council posts late:
      `python3 scripts/fetch_legistar.py <id> --out "$D/legistar/<YYYY-MM-DD>-post-hearing"`.
      `build_hearing.py --legistar-post-dir` merges it with the first download; where both have
      a file, the post-hearing copy wins.

## 2. Video, captions, audio (scripted)

- [ ] Wait until the event's `EventVideoPath` is set (the Council links the recording after the
      hearing ends).
- [ ] `python3 scripts/fetch_media.py --event-json "$D/legistar/event.json" --out "$D"`.
- [ ] Check `$D/media.json`: the MP4, MP3 and Opus durations should agree within a second.

## 3. Transcription (scripted, paid)

- [ ] Note the audio duration from `media.json` before sending: Deepgram bills by audio length.
- [ ] **Build the keyterm list** `hearings/$SLUG/lexicon.txt` (rules and format:
      [`lexicon/README.md`](../lexicon/README.md)). Only this hearing's people, organizations and
      terms, each with a source comment: the committee roster and the Speaker from the Legistar
      Web API (OfficeRecords), the committee report, and the Council's `.vtt` captions. No
      BetaNYC names and no general list. Deepgram allows 100 terms and 500 tokens per request and
      recommends 20 to 50 (https://developers.deepgram.com/docs/keyterm).
      On 2026-10-19, for the 2026-10-16 hearing, the workspace `core` list turned the SpaceX witness's self-introduction
      ("Gabriella Madrid" in the Council's captions) into a BetaNYC staff name.
- [ ] Run Deepgram once, saving `--raw-out` so the response is never paid for twice. From the
      BetaNYC workspace `scripts/` folder:

      ```sh
      python deepgram_transcribe.py "$D/hearing-audio-64k.mp3" \
        --out "$D/deepgram-intermediate.json" --raw-out "$D/deepgram-response.json" \
        --keyterms-file ~/Code/hearings-transcripts/hearings/$SLUG/lexicon.txt --no-core
      ```

      Before any rerun, rename the previous outputs (`*-run1-<what>.*`); never overwrite them.
- [ ] `python3 scripts/render_deepgram_raw.py "$D/deepgram-intermediate.json" "$D/$SLUG-transcript-deepgram-raw.txt"`.

## 4. Speaker naming and panels (manual, AI-assisted)

- [ ] Split the raw transcript into chunks of about 2.5 hours of video, one line per turn
      (`#<i> [HH:MM:SS] S<n>: text`), and label each chunk with an AI agent using
      [`docs/prompts/speaker-naming.md`](prompts/speaker-naming.md). Fill its placeholders from
      the Legistar roster, the committee report and the captions; never from memory.
- [ ] Merge into `$D/speaker-labels.json`, `[{i,name,role,confidence,evidence}]`, one entry per
      turn, `i` equal to the turn's position. A turn that holds two voices keeps one name and
      says so in its evidence (`MIXED: …`); turns are never re-split.
- [ ] Evidence: self-introductions, the chair calling on people, the oath roll call, the
      on-screen banner and Zoom name labels (read from video frames), voice clusters, and the
      Council's `.vtt` captions for names Deepgram garbles.
- [ ] Check elected officials against the Legistar roster and NYS Open Legislation; check
      witnesses against the committee report and any posted testimony.
- [ ] Every role needs a category rule in `build_hearing.py` (`categorize()`); the build stops on
      a role it does not know. An invited AI company goes into `AI_COMPANY_ORGS` deliberately.
- [ ] Write `$D/panels.json`, the parts of the hearing in order:
      `[{panel_id, title, start_hms, end_hms, turn_ids, members:[{name, role, org}]}]`. Each
      turn id appears in at most one part; parts are in time order (`build_hearing.py --panels`
      checks both).
- [ ] Write `$D/$SLUG-transcript.txt` (names replacing `Speaker <n>`, same timestamps).
- [ ] Lesson (2026-10-19, 2026-10-16 hearing): an accented keyterm did not help. "Gutiérrez" on the keyterm list
      came out "Gutirez" twice; run 1, without it, had "Gutierrez". Untested hypothesis: list the
      unaccented spelling and restore the accent here, in naming and the clean edit.

The prompts in [`docs/prompts/`](prompts/) are the public version of the ones used for the
2026-10-05 and 2026-10-16 hearings; the originals, with the session's commands, are kept in the
operator's private workspace.

## 5. Clean verbatim and validation (manual, AI-assisted)

- [ ] Copy edit the named transcript, in parts, with
      [`docs/prompts/clean-verbatim.md`](prompts/clean-verbatim.md), into
      `$D/$SLUG-transcript-clean.txt`: fillers, stutters and false starts out; punctuation,
      spelling, numbers and misheard words fixed. Never change a timestamp or a speaker label.
- [ ] Validate the whole file:

      ```sh
      python3 scripts/validate_clean.py "$D/$SLUG-transcript.txt" "$D/$SLUG-transcript-clean.txt" --names
      ```

      It must exit 0 (same turn count, identical `[HH:MM:SS] Name:` prefixes, which the build
      also enforces). Read `big_shrinks` (turns over 200 characters cut by more than 40%; shorter turns are not checked) and the `--names` list of
      proper nouns added or removed, and check each one.
- [ ] **Lesson: check meaning-changing edits against the Council's captions.** On 2026-10-19 (2026-10-16 hearing) four
      clean-edit changes were reverted because both Deepgram and the captions disagreed with
      them: "lunch" to "launch" (twice), "dictated" to "abdicated", "stopped" to "stalked". A fix
      that changes what someone said needs a second source, not a better-sounding word.

## 6. Build (scripted)

- [ ] Write `scripts/meta/$SLUG.json` (copy an existing one). Leave unknowns empty; do not guess.
      Optional keys: `context` (`{text, source}`, why the hearing happened, as a document states
      it, cited), `council_members_present` (from the labels, not the committee roster),
      `naming_sources`, `mixed_turns`. Empty `internet_archive_url` and `release_url` render as
      "not uploaded yet" and "not published yet".
- [ ] Build:

      ```sh
      python3 scripts/build_hearing.py --meta scripts/meta/$SLUG.json \
        --deepgram "$D/deepgram-intermediate.json" --labels "$D/speaker-labels.json" \
        --transcript "$D/$SLUG-transcript.txt" --transcript-clean "$D/$SLUG-transcript-clean.txt" \
        --audio-opus "$D/hearing-audio-16k.opus" --panels "$D/panels.json" \
        --legistar-pre-dir "$D/legistar"
      ```

      Add `--legistar-post-dir "$D/legistar/<YYYY-MM-DD>-post-hearing"` once there is a
      post-hearing download. Both folders are read through their `manifest.csv`.
- [ ] `python3 scripts/build_panels.py --slug $SLUG` when there is a `panels.json` ("Who spoke,
      panel by panel"), then `python3 scripts/build_hearing.py --index-only` to link it.
- [ ] Write the hearing's own known gaps into the meta file (`known_gaps`, a list of sentences;
      `witness_spelling` if names do not simply follow the transcription). The build writes the
      README from the meta, so anything typed into the README by hand is lost on the next build.

## 7. Word clouds (scripted)

- [ ] Write `scripts/meta/$SLUG-wordclouds.json` with `"extends": "wordclouds.json"` and this
      hearing's `groups`, `people` and `people_method`; say in `removed_note_html` whether its
      lists were reviewed by hand. (2026-10-16's file is an example.)
- [ ] `python3 scripts/build_wordclouds.py --slug $SLUG`, then `python3 scripts/build_hearing.py --index-only`.

## 8. Validate the hearing record (manual)

The scripts check structure: turn counts, timestamps, speaker labels, links. They cannot tell
whether a name is right or an edit changed what someone said. This stage does, and it is where
most of the work on the 2026-10-16 hearing went. Do every step before publishing.

**a. Meaning-changing clean edits.** List every edit that changes a word rather than removing
filler (`scripts/validate_clean.py … --names` lists name changes; diff the two transcripts for the
rest). Keep an edit only if the Council's captions or the context support it. If both Deepgram and
the captions say otherwise, revert it. On 2026-10-19 four edits were reverted this way: "lunch" to
"launch" (twice), "dictated" to "abdicated", "stopped" to "stalked".

**b. Every name and affiliation, against a public source.** Check each speaker's name and
affiliation against the Legistar roster, the committee report, posted testimony, the
organization's own pages or press coverage. Record the source. **Never publish an inferred
affiliation for a private person.** On 2026-10-19 a witness's law firm had been inferred from a
garbled transcription. The guess turned out to be right, but publishing it unchecked would still
have been wrong: until a source confirmed it, her label said only "counsel to Devin Kim". When a
name or an affiliation cannot be confirmed, say so in the meta file's `known_gaps`. A group's own
name wins over how a speaker said it, and a self-description is published as one ("as stated at
the hearing").

**c. On-screen labels, from a video frame.** When a name rests on a name banner or a Zoom tile,
look at the frame rather than trusting a transcription of it:

```sh
ffmpeg -v error -ss 00:09:15 -i "$D/<video>.mp4" -frames:v 1 "$D/frame-00-09-15.png"
```

**d. Two reviews until both say ship.** One reviewer checks the code and the build (a fresh
reader trying to break it); one checks credibility (every public claim, name, title, number and
disclosure against its source). Fix, rebuild, and send the changes back to both until both say
ship.

**e. A person looks at every page in a browser.** Serve the repository locally and open the
homepage, the hearing's README, `panels.html`, the word-cloud pages and any Q&A page:

```sh
python3 -m http.server 8000      # from the repository root, then open http://localhost:8000/
```

**f. After publishing, corrections arrive as issues.** Every page's footer links to the
correction form (`.github/ISSUE_TEMPLATE/correction.yml`) with the hearing and page filled in.
Check each report against its source, fix the inputs (labels, clean transcript, meta), and open a
pull request that reruns the build. Never edit generated files by hand.

Checklist:

- [ ] Every meaning-changing clean edit checked against the captions and Deepgram; unsupported ones reverted.
- [ ] Every speaker name and affiliation checked against a public source, with the source recorded; nothing inferred is published for a private person.
- [ ] Unconfirmed names and affiliations listed in `known_gaps`.
- [ ] On-screen labels confirmed from a video frame.
- [ ] Code review and credibility review both say ship.
- [ ] Every page looked at in a browser.
- [ ] `python3 -m unittest discover -s scripts -v` passes.

## 9. Publish (manual)

- [ ] `hearings/$SLUG/lexicon.txt` stays in git: it records what Deepgram was told.
- [ ] Opus audio goes into git (`hearings/$SLUG/media/hearing-audio-16k.opus`, well under 100 MB).
- [ ] MP3 goes to a GitHub Release tagged `$SLUG`, asset `hearing-audio-64k.mp3`; then set
      `media.audio_mp3.release_url` and `release_published: true` in the meta file and rebuild.
- [ ] Upload the MP4 to the Internet Archive; set `video.internet_archive_url`, and
      `archive_playable: true` once the item plays; rebuild.
- [ ] Add the hearing to the table in the top-level `README.md`.
- [ ] `python3 -m unittest discover -s scripts -v` passes.
- [ ] The MP4 and MP3 never go into git.
- [ ] After publishing: handle correction issues as in stage 8f.
