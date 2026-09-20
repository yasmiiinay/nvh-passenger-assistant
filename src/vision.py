"""Vision pipeline: CLIP ViT-B/32 used as a retrieval model (Architecture Freeze v1.1 4.1).

One frozen encoder, one embedding space, three text targets:
  category prompts        -> which kind of sign is this
  KB record descriptions  -> which record does it correspond to
  out-of-scope anchors    -> is this an airport sign at all

Category recognition and record matching are the same cosine operation
against different text sets, so they share one function. Scores are cosine
similarities; the "match score" shown later is never a probability.
Pictograms and photographed signs go through exactly the same path and are
separated only when results are tabulated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

try:
    # iPhone photos arrive as HEIC, which Pillow cannot open on its own; the
    # first browser test on a MacBook failed on exactly that. Registering the
    # opener here covers both the loader below and the interface's upload.
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from configs.settings import SETTINGS
from src.retrieval import decide

MIN_SIDE = 64            # pixels; anything smaller cannot carry a sign
MAX_PIXELS = 120_000_000 # refuse absurd uploads before decoding them fully (a 48 MP phone photo is 48e6)
WORKING_SIDE = 2048      # larger photos are reduced to this before analysis; CLIP sees 224 px anyway
BLUR_THRESHOLD = 60.0    # variance of the Laplacian on the grey image, below = blurry
DARK_THRESHOLD = 40.0    # mean grey level 0..255
BRIGHT_THRESHOLD = 225.0

BAND_FOR_DECISION = {"answer": "strong match", "clarify": "uncertain",
                     "abstain": "no reliable match"}


# ---------------------------------------------------------------------------
# image loading and checks
# ---------------------------------------------------------------------------

@dataclass
class ImageCheck:
    width: int
    height: int
    blur_score: float
    brightness: float
    flags: list[str] = field(default_factory=list)


def load_image(path: str | Path) -> Image.Image:
    """Open, apply the EXIF rotation, convert to RGB. Raises ValueError with a
    plain message on anything that is not a usable image."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"image file not found: {path}")
    try:
        image = Image.open(path)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"cannot read image {path.name}: {exc}") from exc
    if image.width * image.height > MAX_PIXELS:
        raise ValueError(f"image too large: {image.width}x{image.height}")
    if min(image.width, image.height) < MIN_SIDE:
        raise ValueError(f"image too small: {image.width}x{image.height}")
    image = ImageOps.exif_transpose(image)
    if max(image.width, image.height) > WORKING_SIDE:
        image.thumbnail((WORKING_SIDE, WORKING_SIDE))
    return flatten_on_white(image)


def flatten_on_white(image: Image.Image) -> Image.Image:
    """RGB on a white background. Pictogram files are usually black shapes on
    a transparent background; a plain RGB conversion drops the alpha channel
    and leaves an all-black image, which every such file then shares (found
    on the first run: dozens of different symbols produced one identical
    embedding)."""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return image.convert("RGB")


def check_image(image: Image.Image) -> ImageCheck:
    """Cheap quality signals: blur (Laplacian variance) and brightness."""
    grey = np.asarray(image.convert("L"), dtype=np.float32)
    laplacian = (grey[:-2, 1:-1] + grey[2:, 1:-1] + grey[1:-1, :-2] + grey[1:-1, 2:]
                 - 4 * grey[1:-1, 1:-1])
    check = ImageCheck(image.width, image.height, float(laplacian.var()), float(grey.mean()))
    if check.blur_score < BLUR_THRESHOLD:
        check.flags.append("blurry")
    if check.brightness < DARK_THRESHOLD:
        check.flags.append("dark")
    elif check.brightness > BRIGHT_THRESHOLD:
        check.flags.append("bright")
    return check


# ---------------------------------------------------------------------------
# CLIP, loaded on first use
# ---------------------------------------------------------------------------

_clip = None


def load_clip():
    global _clip
    if _clip is None:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        local_copy = SETTINGS.models_dir / SETTINGS.clip_model_id.split("/")[-1]
        source = str(local_copy) if local_copy.exists() else SETTINGS.clip_model_id
        model = CLIPModel.from_pretrained(source).eval()
        processor = CLIPProcessor.from_pretrained(source)
        _clip = (model, processor, torch)
    return _clip


def _unit(vectors) -> np.ndarray:
    arr = np.asarray(vectors, dtype=np.float32)
    return arr / np.linalg.norm(arr, axis=1, keepdims=True)


def embed_images(images: list[Image.Image]) -> np.ndarray:
    model, processor, torch = load_clip()
    with torch.no_grad():
        inputs = processor(images=images, return_tensors="pt")
        features = model.get_image_features(**inputs)
    return _unit(features.numpy())


def embed_texts(texts: list[str]) -> np.ndarray:
    model, processor, torch = load_clip()
    with torch.no_grad():
        inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True)
        features = model.get_text_features(**inputs)
    return _unit(features.numpy())


# ---------------------------------------------------------------------------
# index of text targets
# ---------------------------------------------------------------------------

@dataclass
class VisionIndex:
    categories: list[str]
    category_vecs: np.ndarray          # one vector per category (mean of its prompts)
    anchors: list[str]
    anchor_vecs: np.ndarray
    record_ids: list[str]
    record_vecs: np.ndarray
    record_categories: list[str] = field(default_factory=list)   # parallel to record_ids


def load_prompts(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def category_vectors(prompts: dict, embed=embed_texts) -> tuple[list[str], np.ndarray]:
    """Average the prompt vectors of each category and re-normalise, so a
    category with two phrasings is not favoured over one with a single phrasing."""
    categories = list(prompts["categories"])
    vecs = []
    for category in categories:
        sentences = [prompts["template"].format(p) for p in prompts["categories"][category]]
        vecs.append(embed(sentences).mean(axis=0))
    return categories, _unit(np.stack(vecs))


def build_vision_index(gaz, prompts: dict, embed=embed_texts) -> VisionIndex:
    categories, category_vecs = category_vectors(prompts, embed)
    anchors = list(prompts["out_of_scope_anchors"])
    visual = [r for r in gaz.kb["records"] if gaz.vocabulary["categories"][r["category"]]["visual_class"]]
    record_ids = [r["record_id"] for r in visual]
    return VisionIndex(categories, category_vecs, anchors, embed(anchors),
                       record_ids, embed([r["retrieval_text"] for r in visual]),
                       [r["category"] for r in visual])


# ---------------------------------------------------------------------------
# ranking and decision logic (pure NumPy, testable without the model)
# ---------------------------------------------------------------------------

def rank(query_vec: np.ndarray, vecs: np.ndarray, labels: list[str]) -> list[tuple[str, float]]:
    sims = vecs @ query_vec
    order = np.argsort(-sims)
    return [(labels[i], round(float(sims[i]), 4)) for i in order]


def top_margin(ranked: list[tuple[str, float]]) -> float:
    if len(ranked) < 2:
        return ranked[0][1] if ranked else 0.0
    return round(ranked[0][1] - ranked[1][1], 4)


def out_of_scope(category_ranked: list[tuple[str, float]], anchor_ranked: list[tuple[str, float]]) -> bool:
    """Out of scope when the best anchor beats the best category prompt. This
    is the relative abstain mechanism from the freeze; an absolute floor is
    applied afterwards through the band."""
    return bool(anchor_ranked) and anchor_ranked[0][1] > category_ranked[0][1]


@dataclass
class VisionResult:
    path: str
    check: ImageCheck
    category_ranking: list[tuple[str, float]]     # top 3 categories
    category_margin: float
    best_anchor: tuple[str, float]
    out_of_scope: bool
    record_ranking: list[tuple[str, float]]       # KB records of the top category, best first
    record_margin: float
    band: str | None                              # set only when thresholds are known

    @property
    def top_category(self) -> str | None:
        return None if self.out_of_scope else self.category_ranking[0][0]

    @property
    def top_record(self) -> str | None:
        return None if self.out_of_scope else self.record_ranking[0][0]

    def as_dict(self) -> dict:
        return asdict(self)


def analyse_vector(path: str, check: ImageCheck, image_vec: np.ndarray, index: VisionIndex,
                   thresholds: dict | None = None) -> VisionResult:
    """Everything after the encoder; split out so the logic is testable with
    synthetic vectors.

    The band is decided on the category ranking, because a sign identifies a
    kind of place and not which terminal's instance of it: the KB holds one
    record per terminal for most categories, so a record ranking from an
    image alone has near-zero margins by construction (measured on the first
    labelled run) and would send every image to the uncertain band. The
    records of the top category are still returned, ranked, as the candidate
    list that text or a follow-up question can narrow later."""
    categories = rank(image_vec, index.category_vecs, index.categories)
    anchors = rank(image_vec, index.anchor_vecs, index.anchors)
    oos = out_of_scope(categories, anchors)
    top_category = categories[0][0] if categories else None
    all_records = rank(image_vec, index.record_vecs, index.record_ids)
    if index.record_categories:
        category_of = dict(zip(index.record_ids, index.record_categories))
        records = [(rid, s) for rid, s in all_records if category_of[rid] == top_category]
    else:
        records = all_records
    band = None
    if thresholds is not None:
        if oos:
            band = "no reliable match"
        else:
            decision, _, _ = decide(categories, thresholds["vision_tau_high"], thresholds["vision_tau_low"],
                                    thresholds["vision_margin_delta"])
            band = BAND_FOR_DECISION[decision]
    return VisionResult(path=path, check=check, category_ranking=categories[:3],
                        category_margin=top_margin(categories), best_anchor=anchors[0] if anchors else ("", 0.0),
                        out_of_scope=oos, record_ranking=records, record_margin=top_margin(records) if records else 0.0,
                        band=band)


def analyse_image(path: str | Path, index: VisionIndex, thresholds: dict | None = None) -> VisionResult:
    image = load_image(path)
    check = check_image(image)
    image_vec = embed_images([image])[0]
    return analyse_vector(str(path), check, image_vec, index, thresholds)
