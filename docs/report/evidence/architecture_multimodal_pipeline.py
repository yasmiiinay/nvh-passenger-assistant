"""Architecture figure for the Nordhaven International (NVH) passenger assistant.

Draws the system as implemented at commit 26dff5f (behavioural core identical to
the freeze 2d05b1c). Every box names the module that implements it; nothing that
is future work or unimplemented appears. Re-run to regenerate PNG and PDF:

    python architecture_multimodal_pipeline.py

Requires matplotlib only. Layout coordinates are in a 100 x 140 unit portrait
canvas (A4-like aspect ratio) so the figure stays legible on a report page.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Ellipse, Rectangle
from matplotlib.lines import Line2D

OUT = Path(__file__).resolve().parent
W, H = 100.0, 143.0
FONT = "DejaVu Sans"

INK = "#2B2B2B"
RULE = "#6B6B6B"
KB_INK = "#7A6A1E"
VOICE_INK = "#2E7D32"
FILL_UI = "#EDEDED"
FILL_TEXT, FILL_VOICE, FILL_IMAGE = "#F3F7FF", "#F2FBF3", "#FFF7EE"
FILL_FUSION, FILL_RESP = "#F3F3F3", "#F5F5FC"
EVID_TEXT, EVID_IMAGE, FILL_POLICY, FILL_KB = "#DDE8FB", "#FBE3CC", "#E2E2E2", "#FFF8D6"

fig = plt.figure(figsize=(8.27, 11.83), dpi=100)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(H, 0)          # y grows downwards, like a page
ax.axis("off")


def box(cx, cy, w, h, title, body="", fill="white", edge=RULE, lw=0.9, tsize=7.2, bsize=5.9):
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                                boxstyle="round,pad=0,rounding_size=1.1",
                                facecolor=fill, edgecolor=edge, linewidth=lw, zorder=3))
    if body:
        ax.text(cx, cy - h / 2 + 1.55, title, ha="center", va="center", fontsize=tsize,
                fontweight="bold", fontfamily=FONT, color=INK, zorder=4)
        ax.text(cx, cy + 0.9, body, ha="center", va="center", fontsize=bsize,
                fontfamily=FONT, color=INK, linespacing=1.25, zorder=4)
    else:
        ax.text(cx, cy, title, ha="center", va="center", fontsize=tsize, fontweight="bold",
                fontfamily=FONT, color=INK, zorder=4)
    return dict(l=cx - w / 2, r=cx + w / 2, t=cy - h / 2, b=cy + h / 2, cx=cx, cy=cy)


def cylinder(cx, cy, w, h, title, body):
    ry = 1.4
    ax.add_patch(Rectangle((cx - w / 2, cy - h / 2 + ry), w, h - 2 * ry, facecolor=FILL_KB,
                           edgecolor="none", zorder=3))
    ax.add_patch(Ellipse((cx, cy + h / 2 - ry), w, 2 * ry, facecolor=FILL_KB, edgecolor=KB_INK, lw=1.0, zorder=3))
    ax.add_line(Line2D([cx - w / 2, cx - w / 2], [cy - h / 2 + ry, cy + h / 2 - ry], color=KB_INK, lw=1.0, zorder=3))
    ax.add_line(Line2D([cx + w / 2, cx + w / 2], [cy - h / 2 + ry, cy + h / 2 - ry], color=KB_INK, lw=1.0, zorder=3))
    ax.add_patch(Ellipse((cx, cy - h / 2 + ry), w, 2 * ry, facecolor=FILL_KB, edgecolor=KB_INK, lw=1.0, zorder=3))
    ax.text(cx, cy - h / 2 + 4.4, title, ha="center", va="center", fontsize=7.2, fontweight="bold",
            fontfamily=FONT, color=INK, zorder=4)
    ax.text(cx, cy + 2.4, body, ha="center", va="center", fontsize=5.4, fontfamily=FONT,
            color=INK, linespacing=1.3, zorder=4)
    return dict(l=cx - w / 2, r=cx + w / 2, t=cy - h / 2, b=cy + h / 2, cx=cx, cy=cy)


def region(x0, y0, x1, y1, label, fill):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=1.6",
                                facecolor=fill, edgecolor="#B8B8B8", linewidth=0.7, zorder=1))
    ax.text(x0 + 1.6, y0 + 1.9, label, ha="left", va="center", fontsize=6.4, fontweight="bold",
            fontfamily=FONT, color="#555555", zorder=2)


def arrow(points, color=INK, lw=0.9, ls="-", label=None, lpos=None, lcolor=None, lsize=5.6, ha="left"):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if len(points) > 2:
        ax.add_line(Line2D(xs[:-1], ys[:-1], color=color, lw=lw, ls=ls, zorder=2.5, solid_capstyle="round"))
    ax.annotate("", xy=points[-1], xytext=points[-2], zorder=2.6,
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, ls=ls, mutation_scale=7,
                                shrinkA=0, shrinkB=0))
    if label:
        lx, ly = lpos if lpos else ((xs[-2] + xs[-1]) / 2, (ys[-2] + ys[-1]) / 2)
        ax.text(lx, ly, label, fontsize=lsize, fontfamily=FONT, color=lcolor or color,
                ha=ha, va="center", style="italic", zorder=5,
                bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none", alpha=0.85))


# ----------------------------------------------------------------- regions
XT, XV, XI = 21.0, 50.0, 79.0          # column centres
SW, VW = 34.0, 17.0                    # side-column / voice-column box widths
region(3.0, 20.0, 39.5, 85.0, "TEXT PATH", FILL_TEXT)
region(41.5, 20.0, 58.5, 52.0, "VOICE", FILL_VOICE)
region(60.5, 20.0, 97.0, 76.0, "IMAGE PATH", FILL_IMAGE)
region(17.0, 88.5, 83.0, 115.5, "MULTIMODAL FUSION", FILL_FUSION)
region(17.0, 117.0, 83.0, 139.5, "RESPONSE", FILL_RESP)

# ----------------------------------------------------------------- UI
passenger = box(XV, 4.5, 34, 5.2, "Passenger", "typed text · voice · photo · text + photo · voice + photo", FILL_UI)
ui = box(XV, 13.5, 62, 7.2, "Gradio Blocks interface  (app/app.py)",
         "single-row composer · photo upload · voice recorder / audio upload\neditable transcript · quick replies · session history · evidence panel", FILL_UI)

# ----------------------------------------------------------------- text path
BS = 5.6
t_in = box(XT, 25.5, SW, 4.8, "Typed query")
t_norm = box(XT, 35.0, SW, 8.6, "Normalisation  L1 generic · L2 airport",
             "lowercase · contractions · number words → digits\nNATO / letter words → pier letters · \"t2\" → \"terminal 2\"\nsrc/normalizer.py", bsize=BS)
t_ent = box(XT, 47.5, SW, 8.6, "Entity extraction",
            "regex identifiers: gate · desk · belt · terminal · flight · deictic\nservice gazetteer built from KB names and aliases\nsrc/entities.py", bsize=BS)
t_det = box(XT, 58.8, SW, 8.6, "Deterministic stages  (always preferred)",
            "volatile redirect (flight ref / live status) · exact identifier\nalias match · grounded negatives (unknown id, other terminal)\nsrc/retrieval.py", bsize=BS)
t_sem = box(XT, 70.3, SW, 9.6, "Semantic stages  MiniLM all-MiniLM-L6-v2",
            "L2-normalised embeddings · nearest-exemplar intent\ncategory filter · cosine ranking vs KB retrieval_text\nτ_high / τ_low / margin  ·  src/text_encoder.py · src/intent.py", bsize=BS)
t_out = box(XT, 80.3, SW, 6.2, "Text evidence  (RetrievalResult)",
            "decision · candidate records · cosine scores · entities · flags", EVID_TEXT, lw=1.1, bsize=BS)

# ----------------------------------------------------------------- voice path
v_in = box(XV, 25.5, VW, 4.8, "Voice input", "recording or audio upload", bsize=BS)
v_gate = box(XV, 35.0, VW, 8.6, "Audio load & gate",
             "mono · resample to 16 kHz\n0.5–60 s · ≥ −45 dBFS\nsrc/speech.py", bsize=BS)
v_asr = box(XV, 46.5, VW, 6.6, "Whisper-base",
            "HF Transformers\ntranscript shown, editable", bsize=BS)

# ----------------------------------------------------------------- image path
i_in = box(XI, 25.5, SW, 4.8, "Uploaded image")
i_pre = box(XI, 35.0, SW, 8.6, "Image load & checks",
            "EXIF orientation · size limits (≤ 2048 px working copy)\ntransparency flattened on white · RGB · blank / blur check\nsrc/vision.py", bsize=BS)
i_clip = box(XI, 46.5, SW, 6.6, "CLIP ViT-B/32",
             "Hugging Face Transformers · frozen encoder\nL2-normalised image embedding", bsize=BS)
i_sim = box(XI, 58.0, SW, 9.6, "NumPy cosine similarity  vs three text sets",
            "airport category prompts · KB record descriptions\nout-of-scope anchors   (data/vision_prompts.json)\nno FAISS · no fine-tuning · no OCR", bsize=BS)
i_out = box(XI, 69.8, SW, 7.4, "Visual evidence  (VisionResult)",
            "top-1 / top-3 category · margin · out-of-scope flag\nvision thresholds · similarities, not probabilities", EVID_IMAGE, lw=1.1, bsize=BS)

# ----------------------------------------------------------------- knowledge base
kb = cylinder(XV, 70.5, 20.0, 21.0, "Structured NVH KB",
              "data/kb/airport_kb.json\n32 records · 12 categories · T1 / T2\n"
              "name · category · terminal · zone\nlevel · description · opening_hours\ndirections · accessibility · aliases\n"
              "identifier ranges · related_records\nassistance_contact · volatility\n"
              "static JSON, not a model — read at\nload time by the dashed targets")

# ----------------------------------------------------------------- fusion
router = box(XV, 99.0, 62, 13.6, "Deterministic router  (src/router.py :: route)",
             "fixed rule order, first match wins — evidence is never averaged\n"
             "R0  nothing usable → abstain          R1  volatile text → official-information redirect\n"
             "R2  identifier in text → text leads; a strong image of another category is noted, not merged\n"
             "R3  vague / deictic text + usable image → image leads, text narrows terminal or candidates\n"
             "R4  text answered + strong image → same category reinforced, different → conflict\n"
             "R5  image only → terminal asked when several records match      R6  text stands alone")
policy = box(XV, 110.3, 46, 7.4, "Uncertainty & conflict policy",
             "outcome ∈ { answer · clarify · abstain · redirect · conflict }\n"
             "τ_high / τ_low and margin on cosine scores · one-turn pending clarification context", FILL_POLICY)
log = box(90.5, 105.0, 16.5, 9.0, "Event log", "src/event_log.py\nids · route · decision\nscores · latency only\nno audio, image or\ntranscript text",
          fill="#FAFAFA", edge="#9A9A9A", tsize=6.4, bsize=5.1)

# ----------------------------------------------------------------- response
resp = box(XV, 123.5, 56, 8.0, "Template response generation  (src/responses.py)",
           "every sentence is a KB field or a fixed template · empty fields omitted\n"
           "hours are given, open / closed is never claimed · no generative model")
panel = box(XV, 134.0, 56, 8.4, "Response panel  →  Gradio UI",
            "answer with location · hours · directions · accessibility\n"
            "match evidence: outcome · route · matched place · cosine score band (not a probability)\n"
            "clarification quick-replies · official-information redirect for live flight / gate status", FILL_UI)

# ----------------------------------------------------------------- edges: main flow
arrow([(XV, passenger["b"]), (XV, ui["t"])])
for x, node in ((XT, t_in), (XV, v_in), (XI, i_in)):
    arrow([(x, ui["b"]), (x, node["t"])])

for a, b in ((t_in, t_norm), (t_norm, t_ent), (t_ent, t_det), (t_det, t_sem), (t_sem, t_out)):
    arrow([(XT, a["b"]), (XT, b["t"])])
for a, b in ((v_in, v_gate), (v_gate, v_asr)):
    arrow([(XV, a["b"]), (XV, b["t"])])
for a, b in ((i_in, i_pre), (i_pre, i_clip), (i_clip, i_sim), (i_sim, i_out)):
    arrow([(XI, a["b"]), (XI, b["t"])])

# Whisper transcript joins the shared text path (the one cross-branch edge)
arrow([(v_asr["l"], v_asr["cy"]), (40.5, v_asr["cy"]), (40.5, t_norm["cy"]), (t_norm["r"], t_norm["cy"])],
      color=VOICE_INK, lw=1.5, label="transcript enters the\nsame text path as\na typed query",
      lpos=(39.2, 41.3), ha="right", lsize=5.3)

# evidence into the router
arrow([(XT, t_out["b"]), (XT, router["t"])])
arrow([(XI, i_out["b"]), (XI, router["t"])])
arrow([(XV, router["b"]), (XV, policy["t"])])
arrow([(XV, policy["b"]), (XV, resp["t"])])
arrow([(XV, resp["b"]), (XV, panel["t"])])
arrow([(router["r"], log["cy"]), (log["l"], log["cy"])], color="#9A9A9A", lw=0.8, ls=":")

# answer returns to the interface
arrow([(panel["r"], panel["cy"]), (98.2, panel["cy"]), (98.2, ui["cy"]), (ui["r"], ui["cy"])],
      color="#7A7A7A", lw=0.9, ls="--", label="answer + evidence\nrendered in the UI",
      lpos=(97.6, 90.0), ha="right")

# knowledge base feeds (dashed, KB colour) — legend below the cylinder
arrow([(kb["l"], 64.0), (t_ent["r"] + 0.9, 64.0), (t_ent["r"] + 0.9, t_ent["cy"] + 2.6), (t_ent["r"], t_ent["cy"] + 2.6)],
      color=KB_INK, ls="--", lw=0.9)
arrow([(kb["l"], 71.5), (t_sem["r"], 71.5)], color=KB_INK, ls="--", lw=0.9)
arrow([(kb["r"], 64.0), (i_sim["l"], 64.0)], color=KB_INK, ls="--", lw=0.9)
arrow([(XV + 8.0, kb["b"]), (XV + 8.0, 86.5), (8.5, 86.5), (8.5, resp["cy"]), (resp["l"], resp["cy"])],
      color=KB_INK, ls="--", lw=0.9, label="record fields\n(location, hours,\ndirections, access)", lpos=(9.3, 101.0), lcolor=KB_INK, ha="left")


# ----------------------------------------------------------------- footer
ax.text(2.0, 141.0, "Nordhaven International (NVH) passenger assistant — architecture as implemented at commit 26dff5f (behavioural core frozen at 2d05b1c).\n"
        "Models: Whisper-base, CLIP ViT-B/32, all-MiniLM-L6-v2 via Hugging Face Transformers. No generative LLM, OCR, FAISS, fine-tuning or live airport data.",
        fontsize=4.9, fontfamily=FONT, color="#666666", ha="left", va="center", linespacing=1.3)

fig.savefig(OUT / "architecture_multimodal_pipeline.png", dpi=300, facecolor="white")
fig.savefig(OUT / "architecture_multimodal_pipeline.pdf", facecolor="white")
print("written", OUT / "architecture_multimodal_pipeline.png", OUT / "architecture_multimodal_pipeline.pdf")
