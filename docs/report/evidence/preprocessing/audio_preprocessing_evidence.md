# Speech preprocessing evidence

Two real clips from the project's own speech set (`data/audio/`; neither belongs to a blind evaluation set) through the frozen functions in `src/speech.py` and then into the shared text functions: a synthetic-voice clip carrying a gate identifier and the single human speaker's quietest clip. Transcripts are shown as evidence of the flow, not as an accuracy measurement — word error rates belong to the speech evaluation.

| step | aud_001 (TTS) | aud_121 (human) |
|---|---|---|
| file | data/audio/files/aud_001.wav | data/audio/files/aud_121.wav |
| manifest | speaker `tts_daniel`, `quiet` / `clean`, split `dev` | speaker `spk_01`, `quiet` / `clean`, split `heldout` |
| reference transcript (manifest) | Where is gate B12? | Where is belt 9? |
| as read by `soundfile` | shape (23443, 1) (frames × channels), 16000 Hz, float32 | shape (59029, 1) (frames × channels), 16000 Hz, float32 |
| after `load_audio` | mono, 23443 samples at 16000 Hz — no resampling needed | mono, 59029 samples at 16000 Hz — no resampling needed |
| `check_audio` | 1.47 s, -19.2 dBFS, ok = True | 3.69 s, -40.6 dBFS, ok = True |
| Whisper feature extractor (inside the HF pipeline) | log-Mel `input_features` (1, 80, 3000) torch.float32 | log-Mel `input_features` (1, 80, 3000) torch.float32 |
| `transcribe` (Whisper-base, English forced, ≤ 64 new tokens) | "Where is Gate B12?" | "Various bads mine." |
| `has_speech_text` | True | True |
| `normalize_l1` / `normalize_l2` | where is gate b12 | various bads mine |
| `extract` entities | gate_id=B12 | — |

Gate settings: 0.5–60.0 s, loudness ≥ -45.0 dBFS. Whisper's `input_features` are (batch, 80 Mel bins, 3000 frames): every clip is zero-padded to the 30 s window Whisper always receives.

## Order of operations (as implemented)

1. `load_audio`: `soundfile` decode to float32, channel mean → mono, polyphase resample to 16000 Hz only when the file rate differs.
2. `check_audio`: duration and RMS loudness gate; a failing clip is never transcribed — the passenger is asked to re-record or type.
3. `transcribe`: the Transformers ASR pipeline computes Whisper's log-Mel features and decodes with language=English, task=transcribe, `max_new_tokens=64`; `has_speech_text` rejects transcripts with no letters.
4. `process_transcript`: the raw transcript goes through `normalize_l1`, `normalize_l2` and `extract` — the same functions as typed text — and then into `resolve`. There is no speech-specific intent model.

## What the human clip shows

`aud_121` is transcribed as "Various bads mine." against the reference "Where is belt 9?". At -40.6 dBFS it clears the -45.0 dBFS floor, so the gate admits it, and `has_speech_text` accepts the output because it contains letters; no identifier is extracted and the request would reach the semantic stage as an unrecognised query. Two preprocessing facts follow: the loudness gate is a floor, not a normaliser — no gain adjustment is applied before Whisper — and nothing between the gate and the cascade can detect that a transcript is wrong. The editable transcript in the interface is the passenger's only recourse.

No denoising, enhancement, voice-activity detection or speaker adaptation is applied; the only speech-specific logic is the gate in front of Whisper.
