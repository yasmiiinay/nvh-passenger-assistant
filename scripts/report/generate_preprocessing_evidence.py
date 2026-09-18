"""Preprocessing evidence for the report (checkpoint 05.4).

Runs the frozen preprocessing functions on real inputs from the repository and
records what they produce. Reads data only; writes Markdown and two figures to
docs/report/evidence/preprocessing/. No dataset, configuration or behavioural
file is touched and no evaluation metric is computed.

    python scripts/report/generate_preprocessing_evidence.py

Needs the project virtual environment (torch, transformers, soundfile, scipy),
because the CLIP and Whisper processors are called to report tensor shapes.
"""
from __future__ import annotations

import csv
import inspect
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from configs.settings import SETTINGS                                          # noqa: E402
from src import normalizer, entities, retrieval, speech, vision                # noqa: E402
from src.normalizer import normalize_l1, normalize_l2, normalize               # noqa: E402
from src.entities import extract, load_gazetteers                              # noqa: E402
from src.retrieval import resolve_deterministic                                # noqa: E402

OUT = REPO / "docs" / "report" / "evidence" / "preprocessing"
OUT.mkdir(parents=True, exist_ok=True)
DATA = REPO / "data"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(out)


def rel(path: Path) -> str:
    return str(Path(path).resolve().relative_to(REPO))


def source_excerpt(func, first: int, last: int) -> str:
    """Lines first..last (1-based, inclusive) of a function as it exists in the repository."""
    lines, start = inspect.getsourcelines(func)
    chunk = lines[first - 1:last]
    path = rel(Path(inspect.getsourcefile(func)))
    return f"`{path}`, `{func.__name__}` lines {start + first - 1}–{start + last - 1}\n\n```python\n{''.join(chunk).rstrip()}\n```"


# ======================================================================= A. text
gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
queries = {}
for name in ("queries_seed.csv", "queries_heldout.csv", "queries_spoken.csv"):
    with open(DATA / "text" / name, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            queries[r["query_id"]] = r


def find_query(*needles: str) -> dict:
    for r in queries.values():
        if all(n.lower() in r["query"].lower() for n in needles):
            return r
    raise KeyError(needles)


text_cases = [
    ("exact identifier (desk)", find_query("desk 145")),
    ("exact identifier (gate)", find_query("gate B12")),
    ("terminal reference + service", find_query("Check-in desks Terminal 2")),
    ("service request, no identifier", find_query("wheelchair assistance")),
    ("flight reference (volatile)", find_query("flight XY456")),
]
text_rows, text_detail = [], []
for label, q in text_cases:
    raw = q["query"]
    l1, l2 = normalize_l1(raw), normalize_l2(raw)
    ex = extract(raw, gaz)
    ents = "; ".join(f"{e.type}={e.value}" + ("" if e.exists is None else (" ✓KB" if e.exists else " ✗KB")) for e in ex.entities) or "—"
    cues = []
    if ex.category_cues:
        cues.append("cue " + ", ".join(f"{t}→{c}" for t, c in ex.category_cues))
    if ex.families:
        cues.append("family " + ", ".join(ex.families))
    if ex.unsupported:
        cues.append("unsupported " + ", ".join(ex.unsupported))
    det = resolve_deterministic(raw, gaz)
    interp = (f"stage `{det.stage}` → **{det.decision}**" + (f", record `{det.matched_record_id}`" if det.matched_record_id else "")
              + (f", flags {det.flags}" if det.flags else "")) if det.resolved else "unresolved → handed to the semantic stage"
    text_rows.append([q["query_id"], label, raw, l1 if l1 != l2 else l1, l2 if l1 != l2 else "(= L1)", ents, "; ".join(cues) or "—", interp])
    text_detail.append(f"- **{q['query_id']}** — {det.reason}" if det.resolved else f"- **{q['query_id']}** — not resolved deterministically; handoff = `{json.dumps(det.handoff)}`")

# a spoken-form transcript through L1 and L2 (L2 exists for exactly this case)
spoken_demo = "How do I get to gate bee twelve in T2"
spoken_rows = [[spoken_demo, normalize_l1(spoken_demo), normalize_l2(spoken_demo),
                "; ".join(f"{e.type}={e.value}" for e in extract(spoken_demo, gaz).entities)]]

try:
    from transformers import AutoTokenizer
    local = SETTINGS.models_dir / SETTINGS.sentence_model_id.split("/")[-1]
    tok = AutoTokenizer.from_pretrained(str(local) if local.exists() else SETTINGS.sentence_model_id)
    tsample = normalize(find_query("flight XY456")["query"])
    tok_note = (f"\n## Where the embedding sees the text\n\nAfter the deterministic stages, `src/text_encoder.py::encode` passes the "
                f"normalised string to `{SETTINGS.sentence_model_id}`. Its WordPiece tokenizer turns `{tsample}` into "
                f"`{' '.join(tok.tokenize(tsample))}` ({len(tok.tokenize(tsample))} pieces); the alphanumeric code is fragmented, "
                "so identifier matching cannot be left to the embedding — it is done before this point. (Full tokenisation "
                "examples: 05.3, `data_exploration/text_preprocessing_examples.md`.)\n")
except Exception as exc:
    tok_note = f"\n_Tokenizer example skipped ({type(exc).__name__})._\n"

(OUT / "text_preprocessing_evidence.md").write_text(
    "# Text preprocessing evidence\n\n"
    "Real outputs of the frozen functions `src/normalizer.py::normalize_l1` / `normalize_l2`, "
    "`src/entities.py::extract` and `src/retrieval.py::resolve_deterministic` on queries from `data/text/queries_*.csv`. "
    "`✓KB` / `✗KB` marks whether an identifier or terminal exists in the knowledge base. The last column is the deterministic "
    "interpretation only; queries it leaves unresolved go on to the MiniLM semantic stage (not run here).\n\n"
    + md_table(["id", "case", "raw query", "L1 generic", "L2 airport", "entities", "cues", "deterministic interpretation"], text_rows)
    + "\n\n**Reasons recorded by the cascade**\n\n" + "\n".join(text_detail)
    + "\n\n## The same functions on a spoken-style transcript\n\n"
    "Typed queries rarely need the L2 rules; ASR output does. This string is not from the dataset — it is a constructed example of the "
    "letter-word and terminal-short-form forms that Whisper produces for spoken identifiers, shown to make the L2 step visible:\n\n"
    + md_table(["input", "L1 generic", "L2 airport", "entities"], spoken_rows)
    + "\n\n## Order of operations (as implemented)\n\n"
    "1. `normalize_l1`: NFKC, lowercase, contraction expansion, punctuation and whitespace rules, cardinal number words → digits.\n"
    "2. `normalize_l2`: letter / NATO words → pier letters in gate context, identifier spacing collapse (`b 12` → `b12`), "
    "terminal short forms (`t2` → `terminal 2`), service-name homophones.\n"
    "3. `extract`: regex identifiers (flight refs on the raw text, gate/desk/belt/terminal/time/deictic on the normalised text), "
    "then the service gazetteer built from KB names and aliases; each identifier is marked as existing or not in the KB.\n"
    "4. `resolve_deterministic`: volatile redirect → exact identifier → alias/gazetteer → grounded negatives; anything unresolved "
    "is handed to the semantic stage with the entities and cues found here.\n"
    + tok_note, encoding="utf-8")

# ======================================================================= B. image
image_ids = ["img_015", "img_092"]
with open(DATA / "images" / "images_manifest.csv", encoding="utf-8", newline="") as fh:
    manifest = {r["image_id"]: r for r in csv.DictReader(fh)}
model, processor, torch = vision.load_clip()
ip = processor.image_processor
img_rows, figs = [], []
for iid in image_ids:
    path = DATA / "images" / manifest[iid]["file"]
    original = Image.open(path)
    original.load()
    o_mode, o_size = original.mode, original.size
    working = vision.load_image(path)
    check = vision.check_image(working)
    with torch.no_grad():
        inputs = processor(images=[working], return_tensors="pt")
        feats = model.get_image_features(**inputs)
    pv = inputs["pixel_values"]
    img_rows.append([iid, manifest[iid]["category"], manifest[iid]["source_type"], rel(path).split("/")[-1],
                     f"{o_mode} {o_size[0]}×{o_size[1]}", f"{working.mode} {working.width}×{working.height}",
                     f"blur {check.blur_score:.0f}, brightness {check.brightness:.0f}, flags {check.flags or '—'}",
                     f"{tuple(pv.shape)} {pv.dtype}", f"min {pv.min():.2f} / max {pv.max():.2f}",
                     f"{tuple(feats.shape)} → L2-normalised"])
    figs.append((iid, o_mode, original.convert("RGBA"), working, check))

processor_facts = [
    ["resize", f"shortest edge → {ip.size}"], ["centre crop", f"{ip.crop_size}"],
    ["rescale", f"× {ip.rescale_factor:.6f} (0–255 → 0–1)"],
    ["normalise", f"mean {[round(m, 4) for m in ip.image_mean]}, std {[round(s, 4) for s in ip.image_std]}"],
    ["convert_rgb", str(getattr(ip, 'do_convert_rgb', True))],
]
(OUT / "image_preprocessing_evidence.md").write_text(
    "# Image preprocessing evidence\n\n"
    "Real outputs of `src/vision.py::load_image`, `check_image` and the Hugging Face `CLIPProcessor` on two dataset images: a clean "
    "pictogram with a transparent background and a photographed, defocused sign.\n\n"
    "## What the project's own code does (`src/vision.py`)\n\n"
    f"1. `load_image`: open and fully decode; refuse files above {vision.MAX_PIXELS:,} pixels or with a side below {vision.MIN_SIDE} px; "
    f"apply EXIF orientation; shrink so the longer side is at most {vision.WORKING_SIDE} px (the working copy); "
    "`flatten_on_white`: composite RGBA/LA/transparent-P images onto white, then convert to RGB.\n"
    f"2. `check_image`: variance of the Laplacian on the grey image (blur, threshold {vision.BLUR_THRESHOLD:.0f}) and mean grey level "
    f"(dark < {vision.DARK_THRESHOLD:.0f}, bright > {vision.BRIGHT_THRESHOLD:.0f}); the flags travel with the result and are shown in the evidence panel.\n"
    "3. `embed_images`: hands the working RGB image to `CLIPProcessor`, runs `get_image_features`, L2-normalises the vector.\n\n"
    "## What the Hugging Face processor does (`CLIPProcessor.image_processor`, not project code)\n\n"
    + md_table(["step", "setting read from the loaded processor"], processor_facts)
    + "\n\nThe mean/std normalisation therefore happens inside the processor; the project never applies it by hand.\n\n"
    "## Measured on two real images\n\n"
    + md_table(["image", "label", "source", "file", "original mode / size", "working copy", "quality check",
                "processor `pixel_values`", "value range", "`get_image_features`"], img_rows)
    + "\n\n## Reading the numbers\n\n"
    "- The pictogram arrives with an alpha channel (`LA`: greyscale + alpha); a plain RGB conversion would drop the alpha and leave a black square (the first-run bug that "
    "`flatten_on_white` fixes), so it is composited on white first.\n"
    "- The photographed sign's Laplacian variance falls below the blur threshold and is flagged `blurry`; the flag does not stop "
    "inference, it is surfaced as uncertainty context.\n"
    "- Whatever the working size, the processor's resize and centre crop yield a `(1, 3, 224, 224)` float32 tensor, "
    "and `get_image_features` yields one 512-dimensional vector per image; CLIP compares this vector with text vectors by cosine.\n"
    "- No OCR, no augmentation, no fine-tuning and no text extraction take place anywhere on this path.\n", encoding="utf-8")

fig, axes = plt.subplots(len(figs), 2, figsize=(5.6, 2.6 * len(figs)))
axes = np.atleast_2d(axes)
for (iid, o_mode, orig_rgba, working, check), (ax0, ax1) in zip(figs, axes):
    checker = Image.new("RGBA", orig_rgba.size, (255, 255, 255, 255))
    tile = 32
    px = checker.load()
    for yy in range(0, orig_rgba.height, tile):
        for xx in range(0, orig_rgba.width, tile):
            if ((xx // tile) + (yy // tile)) % 2:
                for j in range(yy, min(yy + tile, orig_rgba.height)):
                    for i in range(xx, min(xx + tile, orig_rgba.width)):
                        px[i, j] = (205, 205, 205, 255)
    ax0.imshow(Image.alpha_composite(checker, orig_rgba))
    ax0.set_title(f"{iid} as stored: {o_mode} {orig_rgba.width}×{orig_rgba.height}\n"
                  + ("(checkerboard = transparent pixels)" if o_mode in ("RGBA", "LA", "P") else "(no alpha channel)"), fontsize=7)
    ax1.imshow(working)
    ax1.set_title(f"after load_image: {working.mode} {working.width}×{working.height}\nblur {check.blur_score:.0f}, "
                  f"brightness {check.brightness:.0f}, flags {', '.join(check.flags) or 'none'}", fontsize=7)
    for ax in (ax0, ax1):
        ax.axis("off")
fig.suptitle("Project-side image preprocessing (src/vision.py::load_image)\nCLIPProcessor then resizes to 224 px, centre-crops, rescales and normalises", fontsize=7.5)
fig.tight_layout()
fig.savefig(OUT / "image_preprocessing_example.png", dpi=300)
plt.close(fig)

# ======================================================================= C. audio
with open(DATA / "audio" / "audio_manifest.csv", encoding="utf-8", newline="") as fh:
    audio_manifest = {r["audio_id"]: r for r in csv.DictReader(fh)}
import soundfile as sf                                     # noqa: E402
asr = speech.load_whisper()
clip_ids = ["aud_001", "aud_121"]                          # a TTS clip with an identifier and the quietest-speaker human clip; neither is a blind-set clip
clips = {}
for aid in clip_ids:
    arow = audio_manifest[aid]
    apath = DATA / "audio" / arow["file"]
    raw_samples, raw_rate = sf.read(str(apath), dtype="float32", always_2d=True)
    samples, rate = speech.load_audio(apath)
    check = speech.check_audio(samples, rate)
    feat = asr.feature_extractor(samples, sampling_rate=rate, return_tensors="pt")["input_features"]
    transcript = speech.transcribe(samples, rate)
    ok_text = speech.has_speech_text(transcript)
    ex = extract(transcript, gaz)
    clips[aid] = dict(row=arow, path=apath, raw_shape=raw_samples.shape, raw_rate=raw_rate, samples=samples, rate=rate,
                      check=check, feat=feat, transcript=transcript, ok_text=ok_text,
                      l1=normalize_l1(transcript), l2=normalize_l2(transcript),
                      ents="; ".join(f"{e.type}={e.value}" for e in ex.entities) or "—")


def col(c, key):
    return c[key]


steps = [
    ("file", lambda c: rel(c["path"])),
    ("manifest", lambda c: f"speaker `{c['row']['speaker_id']}`, `{c['row']['environment']}` / `{c['row']['noise_condition']}`, split `{c['row']['split']}`"),
    ("reference transcript (manifest)", lambda c: c["row"]["reference_transcript"]),
    ("as read by `soundfile`", lambda c: f"shape {c['raw_shape']} (frames × channels), {c['raw_rate']} Hz, float32"),
    ("after `load_audio`", lambda c: f"mono, {len(c['samples'])} samples at {c['rate']} Hz — {'resampled' if c['raw_rate'] != c['rate'] else 'no resampling needed'}"),
    ("`check_audio`", lambda c: f"{c['check'].seconds} s, {c['check'].rms_dbfs} dBFS, ok = {c['check'].ok}"),
    ("Whisper feature extractor (inside the HF pipeline)", lambda c: f"log-Mel `input_features` {tuple(c['feat'].shape)} {c['feat'].dtype}"),
    ("`transcribe` (Whisper-base, English forced, ≤ 64 new tokens)", lambda c: f"\"{c['transcript']}\""),
    ("`has_speech_text`", lambda c: str(c["ok_text"])),
    ("`normalize_l1` / `normalize_l2`", lambda c: c["l1"] + ("" if c["l2"] == c["l1"] else f" → {c['l2']}")),
    ("`extract` entities", lambda c: c["ents"]),
]
audio_rows = [[name] + [fn(clips[a]) for a in clip_ids] for name, fn in steps]
fe = asr.feature_extractor
human = clips["aud_121"]
(OUT / "audio_preprocessing_evidence.md").write_text(
    "# Speech preprocessing evidence\n\n"
    "Two real clips from the project's own speech set (`data/audio/`; neither belongs to a blind evaluation set) through the frozen "
    "functions in `src/speech.py` and then into the shared text functions: a synthetic-voice clip carrying a gate identifier and the "
    "single human speaker's quietest clip. Transcripts are shown as evidence of the flow, not as an accuracy measurement — word error "
    "rates belong to the speech evaluation.\n\n"
    + md_table(["step", "aud_001 (TTS)", "aud_121 (human)"], audio_rows)
    + f"\n\nGate settings: {SETTINGS.audio_min_seconds}–{SETTINGS.audio_max_seconds} s, loudness ≥ {SETTINGS.audio_min_rms_dbfs} dBFS. "
    f"Whisper's `input_features` are (batch, {fe.feature_size} Mel bins, {human['feat'].shape[-1]} frames): every clip is zero-padded to "
    f"the {fe.chunk_length} s window Whisper always receives.\n\n"
    "## Order of operations (as implemented)\n\n"
    "1. `load_audio`: `soundfile` decode to float32, channel mean → mono, polyphase resample to "
    f"{SETTINGS.audio_sample_rate} Hz only when the file rate differs.\n"
    "2. `check_audio`: duration and RMS loudness gate; a failing clip is never transcribed — the passenger is asked to re-record or type.\n"
    "3. `transcribe`: the Transformers ASR pipeline computes Whisper's log-Mel features and decodes with language=English, task=transcribe, "
    "`max_new_tokens=64`; `has_speech_text` rejects transcripts with no letters.\n"
    "4. `process_transcript`: the raw transcript goes through `normalize_l1`, `normalize_l2` and `extract` — the same functions as typed "
    "text — and then into `resolve`. There is no speech-specific intent model.\n\n"
    "## What the human clip shows\n\n"
    f"`aud_121` is transcribed as \"{human['transcript']}\" against the reference \"{human['row']['reference_transcript']}\". "
    f"At {human['check'].rms_dbfs} dBFS it clears the {SETTINGS.audio_min_rms_dbfs} dBFS floor, so the gate admits it, and "
    "`has_speech_text` accepts the output because it contains letters; no identifier is extracted and the request would reach the "
    "semantic stage as an unrecognised query. Two preprocessing facts follow: the loudness gate is a floor, not a normaliser — no gain "
    "adjustment is applied before Whisper — and nothing between the gate and the cascade can detect that a transcript is wrong. "
    "The editable transcript in the interface is the passenger's only recourse.\n\n"
    "No denoising, enhancement, voice-activity detection or speaker adaptation is applied; the only speech-specific logic is the gate in front of Whisper.\n",
    encoding="utf-8")

fig, axes = plt.subplots(3, 1, figsize=(5.8, 4.6), gridspec_kw={"height_ratios": [1, 1, 1.35]})
peak = max(float(np.abs(clips[a]["samples"]).max()) for a in clip_ids)
for ax, aid in zip(axes[:2], clip_ids):
    c = clips[aid]
    t = np.arange(len(c["samples"])) / c["rate"]
    ax.plot(t, c["samples"], lw=0.35, color="#3B6EA8" if aid == "aud_001" else "#C8501E")
    ax.set_xlim(0, 4.7)
    ax.set_ylim(-peak, peak)
    ax.set_ylabel("amplitude")
    ax.set_title(f"{aid} ({c['row']['speaker_id']}): {c['check'].seconds} s, {c['check'].rms_dbfs} dBFS → \"{c['transcript']}\"", fontsize=7.2)
mel = human["feat"][0].numpy()
n_valid = int(np.ceil(len(human["samples"]) / human["rate"] / fe.chunk_length * mel.shape[1]))
axes[2].imshow(mel[:, :n_valid], aspect="auto", origin="lower", cmap="magma")
axes[2].set_ylabel(f"{mel.shape[0]} Mel bins")
axes[2].set_xlabel(f"frames (first {n_valid} of {mel.shape[1]}; the remainder is the {fe.chunk_length} s zero-pad)")
axes[2].set_title("aud_121: Whisper log-Mel input_features (computed inside the Transformers pipeline)", fontsize=7.2)
fig.tight_layout()
fig.savefig(OUT / "audio_preprocessing_example.png", dpi=300)
plt.close(fig)

# ======================================================================= E. code snippets (real source lines)
snips = [
    ("Text — L1 generic normalisation", normalize_l1, 5, 13,
     "Unicode NFKC, lowercase, contraction expansion, the rule table, then number words → digits; identical for typed text and ASR output."),
    ("Text — L2 airport normalisation", normalize_l2, 1, 7,
     "L2 always runs on top of L1 (`normalize` = `normalize_l2`), so typed text and transcripts take the same path."),
    ("Image — transparency handling before CLIP", vision.flatten_on_white, 7, 11,
     "RGBA/LA/transparent-P files are composited on white, otherwise plain RGB; the CLIP processor then does resize, crop, rescale and mean/std normalisation."),
    ("Image — load, size limits, EXIF and working copy", vision.load_image, 12, 19,
     "Pixel and minimum-side limits, EXIF rotation, downscale to the 2048 px working side, then `flatten_on_white`."),
    ("Speech — decode, mono, 16 kHz", speech.load_audio, 10, 17,
     "Channel mean to mono and polyphase resampling only when the file rate differs from the 16 kHz Whisper expects."),
    ("Speech — the gate in front of Whisper", speech.check_audio, 7, 16,
     "Duration bounds and a loudness floor; a failing clip is never sent to the model."),
]
snip_md = ["# Preprocessing code excerpts (verbatim from the repository)\n",
           "Line numbers refer to the files at the frozen behavioural state. Three preprocessing paths, two short excerpts each.\n"]
for title, fn, a, b, what in snips:
    snip_md.append(f"## {title}\n\n{source_excerpt(fn, a, b)}\n\n_Shows:_ {what}\n")
(OUT / "preprocessing_code_snippets.md").write_text("\n".join(snip_md), encoding="utf-8")

# ======================================================================= D + F. notes
(OUT / "preprocessing_pipeline_notes.md").write_text(
    "# Preprocessing: shared pipeline and critical notes\n\n"
    "## One text pipeline for two modalities\n\n"
    "```\n"
    "typed text ──────────────────────────┐\n"
    "                                     ├─► normalize_l1 ─► normalize_l2 ─► extract ─► resolve_deterministic ─► resolve_semantic (MiniLM)\n"
    "voice ─► load_audio ─► check_audio ─► Whisper-base ─► transcript ─┘\n\n"
    "image ─► load_image (EXIF, limits, 2048 px, flatten on white, RGB) ─► check_image ─► CLIPProcessor (224 px, crop, rescale, mean/std) ─► CLIP ViT-B/32 ─► cosine vs prompts / KB / anchors\n"
    "```\n\n"
    "Speech has no intent model of its own: `src/speech.py::process_transcript` calls the same `normalize_l1`, `normalize_l2`, `extract` "
    "and `resolve` that typed text uses (the docstring of `src/normalizer.py` states this as a design rule: \"one text pipeline\"). "
    "What the speech layer adds is the audio gate in front of Whisper and a record of the raw transcript, so that the evaluation can "
    "separate transcription errors from retrieval errors.\n\n"
    "## Observations grounded in the implementation\n\n"
    "- Identifier handling is deterministic and precedes any embedding: `resolve_deterministic` runs exact-identifier and alias matching "
    "before `resolve_semantic` is reached, so a gate, desk, belt or flight code is never left to cosine similarity.\n"
    "- Alphanumeric codes fragment in MiniLM's WordPiece vocabulary (`xy456` → `x ##y ##45 ##6`), which is the practical reason for the point above; "
    "purely numeric identifiers that exist as vocabulary tokens survive intact.\n"
    "- The L2 rules exist for ASR output: letter words and NATO words become pier letters only in gate/pier context, `b 12` collapses to `b12`, "
    "`t2` expands to `terminal 2`. Typed queries rarely trigger them.\n"
    "- Whisper turns voice into text before retrieval; the decoder is forced to English and capped at 64 new tokens. Non-English speech is "
    "transcribed as best-effort English, not translated — the prototype is English-only.\n"
    "- CLIP's resize, centre crop, rescale and mean/std normalisation live inside the Hugging Face `CLIPProcessor`; the project's own image code "
    "stops at a working RGB copy. Transparent pictograms are composited on white first, because dropping the alpha channel leaves a black square.\n"
    "- The blur and brightness checks are diagnostics, not filters: a blurry image is still embedded, and the flag is shown with the answer.\n"
    f"- {SETTINGS.audio_sample_rate} Hz mono is the target speech rate; resampling is polyphase (`scipy.signal.resample_poly`) and only runs when needed.\n"
    "- No OCR is performed and no text is read off signs; no image augmentation happens at run time; no denoising, enhancement or "
    "voice-activity model is used on audio; none of the three models is fine-tuned.\n", encoding="utf-8")

for p in sorted(OUT.iterdir()):
    print("wrote", rel(p), p.stat().st_size, "bytes")
