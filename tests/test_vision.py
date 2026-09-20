"""Vision pipeline: image checks and the ranking/decision logic with
synthetic vectors (always run), plus CLIP itself when the weights exist."""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.settings import SETTINGS
from src.entities import load_gazetteers
from src import vision
from src.vision import (VisionIndex, analyse_vector, check_image, load_image, load_prompts,
                        out_of_scope, rank, top_margin)


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def photo(tmp_path):
    rng = np.random.default_rng(0)
    path = tmp_path / "sign.png"
    Image.fromarray((rng.random((240, 320, 3)) * 255).astype("uint8")).save(path)
    return path


# ---- always run ----

def test_load_and_check_valid_image(photo):
    image = load_image(photo)
    assert image.mode == "RGB" and image.size == (320, 240)
    check = check_image(image)
    assert check.flags == [] and check.blur_score > vision.BLUR_THRESHOLD


def test_invalid_images_raise_plain_errors(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load_image(tmp_path / "missing.jpg")
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"this is not an image")
    with pytest.raises(ValueError, match="cannot read"):
        load_image(bad)
    tiny = tmp_path / "tiny.png"
    Image.new("RGB", (16, 16)).save(tiny)
    with pytest.raises(ValueError, match="too small"):
        load_image(tiny)


def test_transparent_pictograms_keep_their_shape(tmp_path):
    """Two different black symbols on transparent backgrounds must load as
    two different images on white, not as the same all-black image."""
    for name, box in (("square.png", (40, 40, 160, 160)), ("bar.png", (20, 90, 180, 110))):
        image = Image.new("LA", (200, 200), (0, 0))
        image.paste((0, 255), box)
        image.save(tmp_path / name)
    square = np.asarray(load_image(tmp_path / "square.png"))
    bar = np.asarray(load_image(tmp_path / "bar.png"))
    assert 120 < square.mean() < 255 and 200 < bar.mean() < 255   # white background survives, symbol survives
    assert not np.array_equal(square, bar)


def test_large_and_heic_photos_are_reduced_and_readable(tmp_path):
    big = tmp_path / "big.jpg"
    Image.new("RGB", (6000, 4000), (200, 200, 200)).save(big)
    loaded = load_image(big)
    assert max(loaded.size) == vision.WORKING_SIDE and loaded.size == (2048, 1365)
    pytest.importorskip("pillow_heif")
    heic = tmp_path / "phone.heic"
    Image.new("RGB", (300, 200), (10, 10, 10)).save(heic, format="HEIF")
    assert load_image(heic).size == (300, 200)


def test_quality_flags():
    dark_flat = Image.new("RGB", (200, 200), (10, 10, 10))
    assert set(check_image(dark_flat).flags) == {"blurry", "dark"}
    bright_flat = Image.new("RGB", (200, 200), (250, 250, 250))
    assert set(check_image(bright_flat).flags) == {"blurry", "bright"}


def test_rank_orders_by_cosine_and_margin():
    vecs = np.stack([unit([1, 0, 0]), unit([0, 1, 0]), unit([0.7, 0.7, 0])])
    ranked = rank(unit([1, 0.1, 0]), vecs, ["a", "b", "c"])
    assert [label for label, _ in ranked] == ["a", "c", "b"]
    assert ranked[0][1] > ranked[1][1] > ranked[2][1]
    assert top_margin(ranked) == pytest.approx(ranked[0][1] - ranked[1][1], abs=1e-4)
    assert top_margin([("only", 0.4)]) == 0.4


def test_out_of_scope_when_anchor_wins():
    assert out_of_scope([("gate", 0.25)], [("a photograph of a person", 0.30)])
    assert not out_of_scope([("gate", 0.30)], [("a photograph of a person", 0.25)])
    assert not out_of_scope([("gate", 0.30)], [])


def synthetic_index():
    return VisionIndex(
        categories=["gate", "baggage"], category_vecs=np.stack([unit([1, 0, 0]), unit([0, 1, 0])]),
        anchors=["a photograph of a person"], anchor_vecs=np.stack([unit([0, 0, 1])]),
        record_ids=["gates_pier_a", "gates_pier_b", "baggage_reclaim_t1"],
        record_vecs=np.stack([unit([1, 0.05, 0]), unit([1, 0, 0.05]), unit([0, 1, 0])]),
        record_categories=["gate", "gate", "baggage"])


def test_structured_result_without_thresholds():
    check = check_image(Image.new("RGB", (100, 100), (128, 128, 128)))
    r = analyse_vector("x.png", check, unit([1, 0.2, 0]), synthetic_index())
    assert r.top_category == "gate" and r.category_ranking[0][0] == "gate"
    assert len(r.category_ranking) == 2
    assert [rid for rid, _ in r.record_ranking] == ["gates_pier_a", "gates_pier_b"]   # only the top category's records
    assert r.top_record == "gates_pier_a" and r.record_margin >= 0
    assert r.band is None and not r.out_of_scope
    assert set(r.as_dict()) >= {"category_ranking", "record_ranking", "best_anchor", "out_of_scope", "band"}


def test_bands_and_out_of_scope_result():
    thresholds = {"vision_tau_high": 0.5, "vision_tau_low": 0.2, "vision_margin_delta": 0.05}
    check = check_image(Image.new("RGB", (100, 100), (128, 128, 128)))
    strong = analyse_vector("x.png", check, unit([1, 0, 0.3]), synthetic_index(), thresholds)
    assert strong.band == "strong match"        # decided on the category ranking, not the twin records
    close = analyse_vector("x.png", check, unit([1, 0.98, 0]), synthetic_index(), thresholds)
    assert close.band == "uncertain" and not close.out_of_scope
    oos = analyse_vector("x.png", check, unit([0, 0.1, 1]), synthetic_index(), thresholds)
    assert oos.out_of_scope and oos.band == "no reliable match"
    assert oos.top_category is None and oos.top_record is None


def test_prompt_file_covers_every_visual_category():
    from src.foundation_audit import load_vocabulary
    prompts = load_prompts(SETTINGS.vision_prompts_path)
    vocabulary = load_vocabulary(SETTINGS.vocabulary_path)
    visual = {c for c, v in vocabulary["categories"].items() if v["visual_class"]}
    assert set(prompts["categories"]) == visual
    assert all(1 <= len(p) <= 4 for p in prompts["categories"].values())
    assert len(prompts["out_of_scope_anchors"]) >= 3


# ---- CLIP needed ----

@pytest.fixture(scope="module")
def clip_index():
    pytest.importorskip("transformers")
    gaz = load_gazetteers(SETTINGS.kb_path, SETTINGS.vocabulary_path)
    try:
        return vision.build_vision_index(gaz, load_prompts(SETTINGS.vision_prompts_path))
    except Exception as exc:
        pytest.skip(f"CLIP not available here: {type(exc).__name__}")


def test_clip_embeddings_are_unit_length(clip_index, photo):
    assert clip_index.category_vecs.shape[1] == 512
    assert np.allclose(np.linalg.norm(clip_index.category_vecs, axis=1), 1.0, atol=1e-4)
    vec = vision.embed_images([load_image(photo)])
    assert vec.shape == (1, 512) and abs(np.linalg.norm(vec[0]) - 1.0) < 1e-4


def test_random_noise_image_is_out_of_scope_or_low(clip_index, photo):
    r = vision.analyse_image(photo, clip_index)
    assert len(r.category_ranking) == 3 and len(r.record_ranking) >= 1
    # random noise should not look like a strong airport sign; either an anchor
    # wins or the best category similarity is modest
    assert r.out_of_scope or r.category_ranking[0][1] < 0.35


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
