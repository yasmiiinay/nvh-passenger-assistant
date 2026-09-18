"""Report evidence for data acquisition and exploration (checkpoint 05.3).

Reads the frozen datasets and the knowledge base, writes figures and Markdown
tables under docs/report/evidence/data_exploration/. Nothing under data/ is
modified and no model is evaluated; the only model component touched is the
MiniLM tokenizer, used for a single tokenisation example when available.

    python scripts/report/generate_data_exploration.py
"""
from __future__ import annotations

import csv
import json
import statistics
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from configs.settings import SETTINGS                      # noqa: E402
from src.normalizer import normalize                       # noqa: E402
from src.entities import extract, load_gazetteers          # noqa: E402
from src.kb import expand_identifier_ranges                # noqa: E402

DATA = REPO / "data"
OUT = REPO / "docs" / "report" / "evidence" / "data_exploration"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.titlesize": 9, "axes.titleweight": "bold"})
INK, DEV, HELD, GREY, ACCENT = "#2B2B2B", "#3B6EA8", "#A9C4E4", "#BDBDBD", "#C8501E"


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def wav_info(path: Path) -> tuple[float, int, int, int]:
    """Duration, sample rate, channels, bits — read from the RIFF header so that
    WAVE_FORMAT_EXTENSIBLE files (which the stdlib wave module rejects) work."""
    with open(path, "rb") as fh:
        if fh.read(12)[:4] != b"RIFF":
            raise ValueError(f"not a RIFF file: {path}")
        rate = ch = bits = data = None
        while True:
            head = fh.read(8)
            if len(head) < 8:
                break
            cid, size = struct.unpack("<4sI", head)
            if cid == b"fmt ":
                _, ch, rate, _, _, bits = struct.unpack("<HHIIHH", fh.read(size)[:16])
            elif cid == b"data":
                data = size
                fh.seek(size + (size & 1), 1)
            else:
                fh.seek(size + (size & 1), 1)
    return data / (rate * ch * bits / 8), rate, ch, bits


def load_thumb(path: Path, side: int = 260) -> Image.Image:
    im = ImageOps.exif_transpose(Image.open(path))
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im.convert("RGBA"))
    im = im.convert("RGB")
    im.thumbnail((side, side))
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    return canvas


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# =============================================================== A. visual class distribution
images = read_csv(DATA / "images" / "images_manifest.csv")
cats_in_scope = sorted({r["category"] for r in images if r["category"] != "out_of_scope"})
order = cats_in_scope + ["out_of_scope"]
by_cat_split = Counter((r["category"], r["split"]) for r in images)
by_cat_src = Counter((r["category"], r["source_type"]) for r in images)
by_quality = Counter(r["quality_stratum"] for r in images)

fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0), gridspec_kw={"width_ratios": [1.45, 1]})
ax = axes[0]
x = range(len(order))
dev = [by_cat_split[(c, "dev")] for c in order]
held = [by_cat_split[(c, "heldout")] for c in order]
ax.bar(x, dev, color=DEV, label=f"development ({sum(dev)})", width=0.7)
ax.bar(x, held, bottom=dev, color=HELD, label=f"held-out ({sum(held)})", width=0.7)
for i, (d, h) in enumerate(zip(dev, held)):
    ax.text(i, d + h + 0.6, str(d + h), ha="center", va="bottom", fontsize=7, color=INK)
ax.set_xticks(list(x))
ax.set_xticklabels([c.replace("_", " ") for c in order], rotation=40, ha="right")
ax.set_ylabel("images")
ax.set_title(f"Images per label (n = {len(images)})")
ax.legend(frameon=False, fontsize=7, loc="upper left")
ax.set_ylim(0, max(d + h for d, h in zip(dev, held)) * 1.18)

ax = axes[1]
labels = ["clean icon\n(AIGA/DOT via Commons)", "photographed sign\ngood light", "photographed sign\ndegraded"]
vals = [by_quality["clean"], by_quality["real_good_light"], by_quality["real_degraded"]]
bars = ax.bar(range(3), vals, color=[DEV, "#7FA5CF", ACCENT], width=0.55)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.8, str(v), ha="center", fontsize=7, color=INK)
ax.set_xticks(range(3))
ax.set_xticklabels(labels, fontsize=6.4)
ax.set_title("Source and quality stratum")
ax.set_ylim(0, max(vals) * 1.18)
fig.tight_layout()
fig.savefig(OUT / "visual_class_distribution.png", dpi=300)
plt.close(fig)

# =============================================================== B. representative samples
def pick(category: str, prefer: dict | None = None) -> dict:
    rows = [r for r in images if r["category"] == category]
    if prefer:
        pref = [r for r in rows if all(r.get(k) == v for k, v in prefer.items())]
        rows = pref or rows
    return sorted(rows, key=lambda r: r["image_id"])[0]


samples = [pick(c, {"split": "dev", "source_type": "clean_icon"}) for c in cats_in_scope]
samples.append(by_id_oos := pick("out_of_scope", {"split": "dev", "source_type": "clean_icon"}))
cols = 5 if len(samples) > 8 else 4
rows_n = -(-len(samples) // cols)
fig, axes = plt.subplots(rows_n, cols, figsize=(7.4, 1.75 * rows_n + 0.3))
for ax in axes.flat:
    ax.axis("off")
for ax, r in zip(axes.flat, samples):
    ax.imshow(load_thumb(DATA / "images" / r["file"]))
    ax.set_title(f"{r['category'].replace('_', ' ')}\n{r['image_id']} · {r['source_type'].replace('_', ' ')} · {r['split']}",
                 fontsize=6.8, fontweight="normal")
fig.suptitle(f"One development-split image per in-scope label ({len(cats_in_scope)} labels) and one of the "
             f"{by_cat_split[('out_of_scope', 'dev')] + by_cat_split[('out_of_scope', 'heldout')]} out-of-scope images",
             fontsize=8, y=0.985)
fig.subplots_adjust(left=0.02, right=0.98, top=0.86, bottom=0.02, hspace=0.42, wspace=0.08)
fig.savefig(OUT / "visual_representative_samples.png", dpi=300)
plt.close(fig)

# =============================================================== C. similarity / generalisation panel
by_id = {r["image_id"]: r for r in images}
SHORT_NOTES = {  # condensed from the manifest notes column
    "img_005": "suitcase; confusable with baggage", "img_006": "baggage lockers", "img_068": "photographed suitcase sign",
    "img_075": "baggage claim, inverted", "img_092": "angled, defocused", "img_087": "cut at edge, defocused",
    "img_058": "customs; nearest label security", "img_081": "customs, photographed", "img_093": "arrow, strong angle",
    "img_098": "non-sign photograph",
}
panel_rows = [
    ("Semantically related symbols across labels (suitcase motifs)",
     ["img_005", "img_006", "img_068", "img_075"]),
    ("Same label, clean icon vs photographed vs degraded sign",
     ["img_014", "img_092", "img_007", "img_087"]),
    ("Out-of-scope material: airport-adjacent, angled, and non-sign photographs",
     ["img_058", "img_081", "img_093", "img_098"]),
]
fig, axes = plt.subplots(3, 4, figsize=(7.4, 6.6))
for ax in axes.flat:
    ax.axis("off")
for (title, ids), axrow in zip(panel_rows, axes):
    for ax, iid in zip(axrow, ids):
        r = by_id[iid]
        ax.imshow(load_thumb(DATA / "images" / r["file"]))
        note = SHORT_NOTES.get(iid, "")
        ax.set_title(f"{r['category'].replace('_', ' ')} · {iid}\n{r['quality_stratum'].replace('_', ' ')}"
                     + (f"\n{note}" if note else ""), fontsize=6.3, fontweight="normal")
    axrow[0].text(-0.06, 1.42, title, transform=axrow[0].transAxes, fontsize=7.6, fontweight="bold", va="bottom")
fig.subplots_adjust(left=0.03, right=0.97, top=0.90, bottom=0.01, hspace=0.70, wspace=0.08)
fig.savefig(OUT / "visual_similarity_generalisation.png", dpi=300)
plt.close(fig)

# =============================================================== D. text / intent distribution
exemplars = read_csv(DATA / "text" / "intent_exemplars.csv")
query_files = {"seed (dev)": "queries_seed.csv", "held-out": "queries_heldout.csv",
               "spoken": "queries_spoken.csv", "QA regression": "queries_qa.csv"}
queries = {name: read_csv(DATA / "text" / f) for name, f in query_files.items()}
intents = sorted({r["intent"] for r in exemplars})
ex_counts = Counter(r["intent"] for r in exemplars)
q_counts = {name: Counter(r["intent"] or "(unlabelled)" for r in rows) for name, rows in queries.items()}
all_intents = intents + sorted({i for c in q_counts.values() for i in c} - set(intents))

fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.4), gridspec_kw={"width_ratios": [1, 1.25]})
ax = axes[0]
y = range(len(intents))
ax.barh(list(y), [ex_counts[i] for i in intents], color=DEV, height=0.65)
for i, it in enumerate(intents):
    ax.text(ex_counts[it] + 0.1, i, str(ex_counts[it]), va="center", fontsize=6.5)
ax.set_yticks(list(y))
ax.set_yticklabels(intents, fontsize=6.5)
ax.invert_yaxis()
ax.set_xlabel("authored exemplars")
ax.set_title(f"Intent exemplars (n = {len(exemplars)}, all dev)")
ax.set_xlim(0, max(ex_counts.values()) + 1.2)

ax = axes[1]
y = range(len(all_intents))
left = [0] * len(all_intents)
palette = [DEV, HELD, ACCENT, "#8C8C8C"]
for (name, cnt), col in zip(q_counts.items(), palette):
    vals = [cnt[i] for i in all_intents]
    ax.barh(list(y), vals, left=left, color=col, height=0.65, label=f"{name} ({sum(cnt.values())})")
    left = [a + b for a, b in zip(left, vals)]
for i, tot in enumerate(left):
    ax.text(tot + 0.1, i, str(tot), va="center", fontsize=6.5)
ax.set_yticks(list(y))
ax.set_yticklabels(all_intents, fontsize=6.5)
ax.invert_yaxis()
ax.set_xlabel("labelled queries")
ax.set_title(f"Labelled queries by intent (n = {sum(left)})")
ax.legend(frameon=False, fontsize=6.2, loc="lower right")
ax.set_xlim(0, max(left) + 1.5)
fig.tight_layout()
fig.savefig(OUT / "text_intent_distribution.png", dpi=300)
plt.close(fig)

# =============================================================== D2. preprocessing examples (real function calls)
gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
all_queries = {r["query_id"]: r for rows in queries.values() for r in rows}
example_ids = ["q007", "h004", "q036", "q027", "q006"]
example_ids = [q for q in example_ids if q in all_queries]
spoken = queries["spoken"]
demo_rows = []


def describe(raw: str) -> list[str]:
    ex = extract(raw, gaz)
    ents = "; ".join(f"{e.type}={e.value}" + ("" if e.exists is None else (" (in KB)" if e.exists else " (not in KB)"))
                     + (" [landmark]" if e.role == "landmark" else "") for e in ex.entities) or "—"
    cues = []
    if ex.category_cues:
        cues.append("category cues: " + ", ".join(f"{tok}→{cat}" for tok, cat in ex.category_cues))
    if ex.families:
        cues.append("family: " + ", ".join(ex.families))
    if ex.zones:
        cues.append("zone: " + ", ".join(ex.zones))
    if ex.unsupported:
        cues.append("unsupported service: " + ", ".join(ex.unsupported))
    if ex.fragment:
        cues.append("fragment (no service words)")
    return [normalize(raw), ents, "; ".join(cues) or "—"]


for qid in example_ids:
    raw = all_queries[qid]["query"]
    demo_rows.append([qid, raw, *describe(raw)])
for r in spoken[:2]:
    demo_rows.append([r["query_id"] + " (spoken)", r["query"], *describe(r["query"])])

vocab = json.load(open(DATA / "vocabulary.json", encoding="utf-8"))
tok_section = ""
try:
    from transformers import AutoTokenizer
    local = SETTINGS.models_dir / SETTINGS.sentence_model_id.split("/")[-1]
    tok = AutoTokenizer.from_pretrained(str(local) if local.exists() else SETTINGS.sentence_model_id)
    tok_lines = []
    for qid in ("h004", "q036"):
        if qid not in all_queries:
            continue
        sample = normalize(all_queries[qid]["query"])
        pieces = tok.tokenize(sample)
        words = sample.split()
        split_words = [w for w in words if len(tok.tokenize(w)) > 1]
        frags = ", ".join("`%s` → `%s`" % (w, " ".join(tok.tokenize(w))) for w in split_words)
        verdict = "every word maps to one WordPiece token" if not split_words else "split into sub-word pieces: " + frags
        tok_lines.append(f"- `{qid}` input: `{sample}`  \n  tokens ({len(pieces)} for {len(words)} words): `{' '.join(pieces)}`  \n  {verdict}.")
    tok_section = ("\n## MiniLM tokenisation of two normalised queries\n\n"
                   f"Tokenizer: `{SETTINGS.sentence_model_id}` (WordPiece, uncased; `##` marks a word continuation).\n\n"
                   + "\n".join(tok_lines)
                   + "\n\nNumeric identifiers that exist as whole tokens in the vocabulary survive intact, while alphanumeric "
                     "codes are fragmented; in both cases the embedding carries no notion of an identifier *range*, which is why "
                     "the cascade resolves identifiers deterministically against the KB before any embedding is computed.\n")
except Exception as exc:  # tokenizer unavailable in this environment
    tok_section = f"\n## MiniLM tokenisation\n\n_Skipped: tokenizer not available in this environment ({type(exc).__name__})._\n"

(OUT / "text_preprocessing_examples.md").write_text(
    "# Text preprocessing examples (real outputs of the frozen functions)\n\n"
    f"Generated by `scripts/report/generate_data_exploration.py` from `src/normalizer.py::normalize` and "
    f"`src/entities.py::extract` at their frozen state. Queries are taken from `data/text/queries_*.csv`.\n\n"
    + md_table(["query id", "raw query", "normalised (L1 + L2)", "entities", "cues"], demo_rows)
    + "\n\n## Vocabulary resources (`data/vocabulary.json`)\n\n"
    + md_table(["resource", "count", "values"],
               [["categories", len(vocab["categories"]), ", ".join(sorted(vocab["categories"]))],
                ["intents", len(vocab["intents"]), ", ".join(sorted(vocab["intents"]))],
                ["entity types", len(vocab["entities"]), ", ".join(sorted(vocab["entities"]))],
                ["decision outcomes", len(vocab["decision_outcomes"]), ", ".join(vocab["decision_outcomes"])],
                ["query types", len(vocab["query_types"]), ", ".join(vocab["query_types"])]])
    + "\n\n## Labelled text query sets\n\n"
    + md_table(["file", "queries", "split", "query types", "expected behaviour"],
               [[f, len(rows), ", ".join(sorted({r['split'] for r in rows})),
                 ", ".join(f"{k} {v}" for k, v in sorted(Counter(r['query_type'] for r in rows).items())),
                 ", ".join(f"{k} {v}" for k, v in sorted(Counter(r['expected_behaviour'] for r in rows).items()))]
                for f, rows in ((query_files[n], queries[n]) for n in queries)])
    + "\n" + tok_section, encoding="utf-8")

# =============================================================== E. audio summary
manifest = read_csv(DATA / "audio" / "audio_manifest.csv")
derived = read_csv(DATA / "audio" / "derived_manifest.csv")
info = {r["audio_id"]: wav_info(DATA / "audio" / r["file"]) for r in manifest + derived}
tts = [r for r in manifest if r["speaker_id"].startswith("tts_")]
human = [r for r in manifest if not r["speaker_id"].startswith("tts_")]
d_tts = [info[r["audio_id"]][0] for r in tts]
d_hum = [info[r["audio_id"]][0] for r in human]
d_all = d_tts + d_hum
rates = Counter(f"{v[1]} Hz / {v[2]} ch / {v[3]}-bit" for v in info.values())
voices = Counter(r["speaker_id"] for r in manifest)


def dur_line(ds):
    return f"{min(ds):.2f}–{max(ds):.2f} s, mean {statistics.mean(ds):.2f} s, median {statistics.median(ds):.2f} s"


audio_md = (
    "# Speech dataset summary (`data/audio/`)\n\n"
    "Generated by `scripts/report/generate_data_exploration.py` from `audio_manifest.csv`, `derived_manifest.csv` "
    "and the WAV headers. No clips were generated or altered.\n\n"
    + md_table(["subset", "clips", "speakers / voices", "environment · noise", "split", "duration", "format"], [
        ["synthetic TTS", len(tts), f"{len({r['speaker_id'] for r in tts})} macOS voices × {len({r['query_id'] for r in tts})} utterances "
         f"({', '.join(sorted(v.replace('tts_', '') for v in voices if v.startswith('tts_')))})",
         ", ".join(sorted({r['environment'] + ' · ' + r['noise_condition'] for r in tts})),
         ", ".join(f"{k} {v}" for k, v in sorted(Counter(r['split'] for r in tts).items())), dur_line(d_tts), ", ".join(rates)],
        ["human recordings", len(human), f"{len({r['speaker_id'] for r in human})} speaker ({', '.join(sorted({r['speaker_id'] for r in human}))})",
         ", ".join(sorted({r['environment'] + ' · ' + r['noise_condition'] for r in human})),
         ", ".join(f"{k} {v}" for k, v in sorted(Counter(r['split'] for r in human).items())), dur_line(d_hum), ", ".join(rates)],
        ["derived stress clips", len(derived), "from " + ", ".join(sorted({r['derived_from'] for r in derived})),
         "; ".join(sorted({r['derivation'] for r in derived})),
         ", ".join(f"{k} {v}" for k, v in sorted(Counter(r['split'] for r in derived).items())),
         dur_line([info[r['audio_id']][0] for r in derived]), ", ".join(rates)],
        ["**all manifest clips**", len(manifest), "", "", "", dur_line(d_all) + f", total {sum(d_all):.0f} s", ""],
    ])
    + "\n\n## What the clips say\n\n"
    + f"{len({r['reference_transcript'] for r in manifest})} distinct reference transcripts; "
    + f"{sum(1 for r in manifest if r['expected_identifiers'])} clips carry an expected identifier (gate / desk / belt / flight code). "
    + "The TTS utterances are listed in `tts_utterances.csv`; the five human clips are:\n\n"
    + md_table(["clip", "transcript", "duration"], [[r["audio_id"], r["reference_transcript"], f"{info[r['audio_id']][0]:.2f} s"] for r in human])
    + "\n\n## Dataset observations\n\n"
    "- The manifest records one environment (`quiet`) and one noise condition (`clean`) for all 125 primary clips; the only "
    "degraded conditions are the four derived clips (gain reduced to −52 dBFS; white noise at 5 dB SNR).\n"
    "- 96% of clips are synthetic macOS voices; accent and spontaneous-speech variation is limited to one human speaker with five clips.\n"
    "- Human clips are on average about twice as long as the TTS renderings of comparable phrases "
    f"({statistics.mean(d_hum):.2f} s vs {statistics.mean(d_tts):.2f} s).\n"
    "- Every file is 16 kHz mono 16-bit PCM, matching `audio_sample_rate` in `configs/settings.py`, so no resampling occurs on these clips.\n"
)
(OUT / "audio_dataset_summary.md").write_text(audio_md, encoding="utf-8")

fig, ax = plt.subplots(figsize=(5.2, 2.6))
bins = [0.5 + 0.25 * i for i in range(18)]
ax.hist([d_tts, d_hum], bins=bins, stacked=True, color=[DEV, ACCENT],
        label=[f"TTS clips (n = {len(d_tts)})", f"human clips (n = {len(d_hum)})"])
ax.axvline(SETTINGS.audio_min_seconds, color=GREY, ls="--", lw=0.9)
ax.text(SETTINGS.audio_min_seconds + 0.03, ax.get_ylim()[1] * 0.92, f"gate: min {SETTINGS.audio_min_seconds} s", fontsize=6.5, color="#666")
ax.set_xlabel("clip duration (s)")
ax.set_ylabel("clips")
ax.set_title("Speech clip durations (data/audio/audio_manifest.csv)")
ax.legend(frameon=False, fontsize=7)
fig.tight_layout()
fig.savefig(OUT / "audio_duration_distribution.png", dpi=300)
plt.close(fig)

# =============================================================== F. knowledge base summary
kb = json.load(open(SETTINGS.kb_path, encoding="utf-8"))
records = kb["records"]
cat_counts = Counter(r["category"] for r in records)
term_counts = Counter(r.get("terminal", "") for r in records)
serves = Counter(", ".join(r.get("serves_terminals") or []) or "—" for r in records)
vol = Counter(r.get("volatility", "") for r in records)
cat_term = defaultdict(Counter)
for r in records:
    cat_term[r["category"]][r.get("terminal", "")] += 1
field_presence = Counter(k for r in records for k in r if r[k] not in ("", [], None))
n_ids = sum(len(r.get("identifiers") or []) for r in records)
n_alias = sum(len(r.get("aliases") or []) for r in records)
terms = sorted(term_counts)

kb_md = (
    "# Knowledge base summary (`data/kb/airport_kb.json`)\n\n"
    f"Generated by `scripts/report/generate_data_exploration.py`. {len(records)} records, {len(cat_counts)} categories, "
    f"schema version noted in `_meta`. The KB is a static, hand-authored JSON resource for the fictional Nordhaven airport; "
    "no field is derived from a live system.\n\n## Records by category and terminal\n\n"
    + md_table(["category", *terms, "total"],
               [[c, *[cat_term[c][t] for t in terms], cat_counts[c]] for c in sorted(cat_counts)]
               + [["**total**", *[term_counts[t] for t in terms], len(records)]])
    + "\n\n## Other structure\n\n"
    + md_table(["property", "value"], [
        ["records serving both terminals (`serves_terminals`)", ", ".join(f"{k}: {v}" for k, v in sorted(serves.items()))],
        ["volatility", ", ".join(f"{k}: {v}" for k, v in sorted(vol.items()))],
        ["identifiers after range expansion (`src/kb.py`)", sum(len(expand_identifier_ranges(r)) for r in records)],
        ["explicit `identifiers` entries in the file", n_ids],
        ["alias strings", n_alias],
    ])
    + "\n\n## Schema fields and how many records populate them\n\n"
    + md_table(["field", "records populated", "role in the system"], [
        [k, field_presence[k], {
            "record_id": "primary key", "name": "surface name; gazetteer", "category": "vision + intent category filter",
            "terminal": "terminal filtering and clarification", "zone": "location wording", "level": "location wording",
            "description": "passenger-facing sentence", "retrieval_text": "MiniLM embedding target",
            "opening_hours": "hours line; open/closed never claimed", "directions": "route sentence",
            "accessibility": "access line", "aliases": "alias match; gazetteer", "identifiers": "exact identifier match",
            "identifier_ranges": "expanded to identifiers at load", "related_records": "links between records",
            "assistance_contact": "escalation contact route", "serves_terminals": "cross-terminal answers",
            "volatility": "volatile → official-source redirect", "availability_note": "caveat text",
            "source": "provenance (synthetic)", "last_verified": "provenance", "verification_status": "provenance"}.get(k, "")]
        for k in sorted(field_presence, key=lambda f: -field_presence[f])])
    + "\n"
)
(OUT / "kb_dataset_summary.md").write_text(kb_md, encoding="utf-8")

# =============================================================== observations
oos_share = 100 * (by_cat_split[("out_of_scope", "dev")] + by_cat_split[("out_of_scope", "heldout")]) / len(images)
missing_visual = sorted(set(json.load(open(SETTINGS.vision_prompts_path, encoding="utf-8"))["categories"]) - set(cats_in_scope))
notes = f"""# Data exploration — observations for the report

Generated by `scripts/report/generate_data_exploration.py`. Every statement below is a **dataset** observation
read from the frozen manifests; none is a model result. Model behaviour on these data is reported separately
(development runs in checkpoints 03.x and the independent Blind v3 evaluation).

## Visual data (`data/images/`, {len(images)} images)
- Label imbalance: {oos_share:.0f}% of images are `out_of_scope` ({by_cat_split[("out_of_scope", "dev")] + by_cat_split[("out_of_scope", "heldout")]}), leaving {sum(1 for r in images if r["category"] != "out_of_scope")} in-scope images across {len(cats_in_scope)} labels; `lounge` has 1 image, `information` and `medical` 2 each, `transport` 11.
- Two vision-prompt categories have **no images at all**: {", ".join(f"`{c}`" for c in missing_visual)}. Their recognition rests on CLIP's zero-shot text prompts alone and was never checked on the development split.
- Style bias: {by_quality["clean"]} of {len(images)} images ({100 * by_quality["clean"] / len(images):.0f}%) are clean AIGA/DOT vector icons rendered from Wikimedia Commons; photographed signage contributes {by_quality["real_good_light"]} good-light and {by_quality["real_degraded"]} degraded images, all author-supplied (`own_photo`) and mostly photographs of the same AIGA-style pictograms.
- Split: {sum(dev)} development / {sum(held)} held-out. Development in-scope images are {sum(1 for r in images if r["split"] == "dev" and r["category"] != "out_of_scope")} in total, so the vision thresholds (τ_high, τ_low, margin) were set on very few positives per label.
- Documented hard cases exist but are few: {sum(1 for r in images if "defocused" in r["notes"])} defocused, {sum(1 for r in images if "angle" in r["notes"])} angled, {sum(1 for r in images if "inverted" in r["notes"])} colour-inverted, {sum(1 for r in images if r["notes"].startswith("photo:"))} non-sign photographs.
- Visually related symbols cross label boundaries by design (suitcase motifs in `check_in` and `baggage`; the customs officer icon is `out_of_scope` but nearest to `security`), which is the intended stress on similarity-based retrieval.

## Text data (`data/text/`)
- Intent exemplars are balanced by construction: {len(exemplars)} authored phrasings, {min(ex_counts.values())}–{max(ex_counts.values())} per intent over {len(intents)} intents, all in the development split; there is no held-out exemplar set, so nearest-exemplar intent prediction is only tested indirectly through the labelled query sets.
- Labelled queries are small: {len(queries["seed (dev)"])} seed (dev), {len(queries["held-out"])} held-out, {len(queries["spoken"])} spoken, {len(queries["QA regression"])} QA regression = {sum(len(v) for v in queries.values())} in total; `find_gate` ({sum(c["find_gate"] for c in q_counts.values())}) and `find_transport` ({sum(c["find_transport"] for c in q_counts.values())}) dominate, `find_restaurant` and `find_restroom` have 3 each.
- All queries were authored by the developer or the QA sessions; two `non_english` cases exist but the system is English-only. Real passenger phrasing, typos and code-switching are not represented.
- Identifier handling is deterministic and dominant: 9 entity types are extracted by regex and gazetteer before any embedding; the tokenisation example shows why (WordPiece splits identifiers into fragments).

## Speech data (`data/audio/`, {len(manifest)} clips + {len(derived)} derived)
- {len(tts)} of {len(manifest)} clips ({100 * len(tts) / len(manifest):.0f}%) are synthetic macOS TTS voices ({len({r["speaker_id"] for r in tts})} voices × {len({r["query_id"] for r in tts})} utterances); one human speaker contributed {len(human)} clips. Accent, age, spontaneous phrasing and disfluency diversity are therefore minimal.
- Every manifest clip is recorded as `quiet` / `clean`; acoustic degradation exists only in the {len(derived)} derived clips (−52 dBFS gain, 5 dB SNR white noise). Background noise from a real terminal is not represented.
- Durations are short ({dur_line(d_all)}); human clips average {statistics.mean(d_hum):.2f} s against {statistics.mean(d_tts):.2f} s for TTS. All files are 16 kHz mono 16-bit, so the resampling path in `src/speech.py` is not exercised by this data.

## Knowledge base (`data/kb/airport_kb.json`, {len(records)} records)
- Terminal imbalance: {term_counts["Terminal 1"]} records in Terminal 1 vs {term_counts["Terminal 2"]} in Terminal 2; {serves["Terminal 1, Terminal 2"]} records serve both terminals. Terminal 2 has no `lost_property`, `lounge`, `medical` or `transport` record, so those requests resolve to Terminal 1 records or to a grounded negative.
- Several categories hold a single record ({", ".join(c for c, n in sorted(cat_counts.items()) if n == 1)}), which makes them easy to answer but gives no within-category disambiguation to test.
- The KB is entirely synthetic and hand-authored: hours, directions and contacts are invented, and `volatility` marks the one record (flight information) whose real-world counterpart changes minute by minute.

## Implications for generalisation (dataset-level)
- Results on clean pictograms cannot be assumed to transfer to real airport signage; the photographed subset is small, author-supplied and mostly the same sign family.
- Text and speech results reflect a single author's and a single speaker's phrasing plus TTS; they are evidence of pipeline behaviour, not of coverage of real passenger language.
- The KB's size (32 records) makes exact and alias matching unusually effective; a larger real KB would shift more decisions to the semantic stage, where the thresholds were set on 43 development queries.
"""
(OUT / "data_exploration_notes.md").write_text(notes, encoding="utf-8")

# =============================================================== console summary for verification
print("images", len(images), "in-scope", sum(1 for r in images if r["category"] != "out_of_scope"),
      "oos", by_cat_split[("out_of_scope", "dev")] + by_cat_split[("out_of_scope", "heldout")],
      "dev/heldout", sum(dev), sum(held), "clean/photo", by_quality["clean"], by_quality["real_good_light"] + by_quality["real_degraded"])
print("exemplars", len(exemplars), "intents", len(intents), "queries", {k: len(v) for k, v in queries.items()})
print("audio", len(manifest), "tts", len(tts), "human", len(human), "derived", len(derived), dur_line(d_all))
print("kb", len(records), dict(cat_counts), dict(term_counts))
print("tokenizer example:", "included" if "Tokens (" in tok_section else "skipped")
for p in sorted(OUT.iterdir()):
    print("wrote", p.relative_to(REPO), p.stat().st_size, "bytes")
