# Preprocessing code excerpts (verbatim from the repository)

Line numbers refer to the files at the frozen behavioural state. Three preprocessing paths, two short excerpts each.

## Text — L1 generic normalisation

`src/normalizer.py`, `normalize_l1` lines 143–151

```python
    if text is None:
        return ""
    t = unicodedata.normalize("NFKC", str(text)).lower()
    for key, value in CONTRACTIONS.items():
        t = t.replace(key, value)
    for rule in L1_RULES:
        t = rule.apply(t)
    t = _numbers_to_digits(t.strip())
    return t.strip()
```

_Shows:_ Unicode NFKC, lowercase, contraction expansion, the rule table, then number words → digits; identical for typed text and ASR output.

## Text — L2 airport normalisation

`src/normalizer.py`, `normalize_l2` lines 219–225

```python
def normalize_l2(text: str) -> str:
    """Airport normalisation applied on top of L1. Expects L1 output but is
    safe on raw text because it lowercases through normalize_l1 first."""
    t = normalize_l1(text)
    for rule in L2_RULES:
        t = rule.apply(t)
    return re.sub(r"\s+", " ", t).strip()
```

_Shows:_ L2 always runs on top of L1 (`normalize` = `normalize_l2`), so typed text and transcripts take the same path.

## Image — transparency handling before CLIP

`src/vision.py`, `flatten_on_white` lines 86–90

```python
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return image.convert("RGB")
```

_Shows:_ RGBA/LA/transparent-P files are composited on white, otherwise plain RGB; the CLIP processor then does resize, crop, rescale and mean/std normalisation.

## Image — load, size limits, EXIF and working copy

`src/vision.py`, `load_image` lines 70–77

```python
    if image.width * image.height > MAX_PIXELS:
        raise ValueError(f"image too large: {image.width}x{image.height}")
    if min(image.width, image.height) < MIN_SIDE:
        raise ValueError(f"image too small: {image.width}x{image.height}")
    image = ImageOps.exif_transpose(image)
    if max(image.width, image.height) > WORKING_SIDE:
        image.thumbnail((WORKING_SIDE, WORKING_SIDE))
    return flatten_on_white(image)
```

_Shows:_ Pixel and minimum-side limits, EXIF rotation, downscale to the 2048 px working side, then `flatten_on_white`.

## Speech — decode, mono, 16 kHz

`src/speech.py`, `load_audio` lines 45–52

```python
        samples, rate = sf.read(str(path), dtype="float32", always_2d=True)
    except (RuntimeError, sf.LibsndfileError) as exc:
        raise ValueError(f"cannot read audio {path.name}: {exc}") from exc
    mono = samples.mean(axis=1)
    if rate != target_rate:
        gcd = np.gcd(rate, target_rate)
        mono = resample_poly(mono, target_rate // gcd, rate // gcd).astype(np.float32)
    return mono, target_rate
```

_Shows:_ Channel mean to mono and polyphase resampling only when the file rate differs from the 16 kHz Whisper expects.

## Speech — the gate in front of Whisper

`src/speech.py`, `check_audio` lines 66–75

```python
    seconds = len(samples) / rate
    loudness = rms_dbfs(samples)
    check = AudioCheck(round(seconds, 2), round(loudness, 1), rate, ok=True)
    if seconds < min_seconds:
        check.ok, check.problem = False, f"too short ({seconds:.1f} s)"
    elif seconds > max_seconds:
        check.ok, check.problem = False, f"too long ({seconds:.0f} s)"
    elif loudness < min_rms_dbfs:
        check.ok, check.problem = False, f"too quiet ({loudness:.0f} dBFS)"
    return check
```

_Shows:_ Duration bounds and a loudness floor; a failing clip is never sent to the model.
