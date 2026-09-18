# Preprocessing: shared pipeline and critical notes

## One text pipeline for two modalities

```
typed text ──────────────────────────┐
                                     ├─► normalize_l1 ─► normalize_l2 ─► extract ─► resolve_deterministic ─► resolve_semantic (MiniLM)
voice ─► load_audio ─► check_audio ─► Whisper-base ─► transcript ─┘

image ─► load_image (EXIF, limits, 2048 px, flatten on white, RGB) ─► check_image ─► CLIPProcessor (224 px, crop, rescale, mean/std) ─► CLIP ViT-B/32 ─► cosine vs prompts / KB / anchors
```

Speech has no intent model of its own: `src/speech.py::process_transcript` calls the same `normalize_l1`, `normalize_l2`, `extract` and `resolve` that typed text uses (the docstring of `src/normalizer.py` states this as a design rule: "one text pipeline"). What the speech layer adds is the audio gate in front of Whisper and a record of the raw transcript, so that the evaluation can separate transcription errors from retrieval errors.

## Observations grounded in the implementation

- Identifier handling is deterministic and precedes any embedding: `resolve_deterministic` runs exact-identifier and alias matching before `resolve_semantic` is reached, so a gate, desk, belt or flight code is never left to cosine similarity.
- Alphanumeric codes fragment in MiniLM's WordPiece vocabulary (`xy456` → `x ##y ##45 ##6`), which is the practical reason for the point above; purely numeric identifiers that exist as vocabulary tokens survive intact.
- The L2 rules exist for ASR output: letter words and NATO words become pier letters only in gate/pier context, `b 12` collapses to `b12`, `t2` expands to `terminal 2`. Typed queries rarely trigger them.
- Whisper turns voice into text before retrieval; the decoder is forced to English and capped at 64 new tokens. Non-English speech is transcribed as best-effort English, not translated — the prototype is English-only.
- CLIP's resize, centre crop, rescale and mean/std normalisation live inside the Hugging Face `CLIPProcessor`; the project's own image code stops at a working RGB copy. Transparent pictograms are composited on white first, because dropping the alpha channel leaves a black square.
- The blur and brightness checks are diagnostics, not filters: a blurry image is still embedded, and the flag is shown with the answer.
- 16000 Hz mono is the target speech rate; resampling is polyphase (`scipy.signal.resample_poly`) and only runs when needed.
- No OCR is performed and no text is read off signs; no image augmentation happens at run time; no denoising, enhancement or voice-activity model is used on audio; none of the three models is fine-tuned.
