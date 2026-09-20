# Image preprocessing evidence

Real outputs of `src/vision.py::load_image`, `check_image` and the Hugging Face `CLIPProcessor` on two dataset images: a clean pictogram with a transparent background and a photographed, defocused sign.

## What the project's own code does (`src/vision.py`)

1. `load_image`: open and fully decode; refuse files above 120,000,000 pixels or with a side below 64 px; apply EXIF orientation; shrink so the longer side is at most 2048 px (the working copy); `flatten_on_white`: composite RGBA/LA/transparent-P images onto white, then convert to RGB.
2. `check_image`: variance of the Laplacian on the grey image (blur, threshold 60) and mean grey level (dark < 40, bright > 225); the flags travel with the result and are shown in the evidence panel.
3. `embed_images`: hands the working RGB image to `CLIPProcessor`, runs `get_image_features`, L2-normalises the vector.

## What the Hugging Face processor does (`CLIPProcessor.image_processor`, not project code)

| step | setting read from the loaded processor |
|---|---|
| resize | shortest edge → {'shortest_edge': 224} |
| centre crop | {'height': 224, 'width': 224} |
| rescale | × 0.003922 (0–255 → 0–1) |
| normalise | mean [0.4815, 0.4578, 0.4082], std [0.2686, 0.2613, 0.2758] |
| convert_rgb | True |

The mean/std normalisation therefore happens inside the processor; the project never applies it by hand.

## Measured on two real images

| image | label | source | file | original mode / size | working copy | quality check | processor `pixel_values` | value range | `get_image_features` |
|---|---|---|---|---|---|---|---|---|---|
| img_015 | restroom | clean_icon | img_015.png | LA 960×886 | RGB 960×886 | blur 917, brightness 124, flags — | (1, 3, 224, 224) torch.float32 | min -1.79 / max 2.15 | (1, 512) → L2-normalised |
| img_092 | restroom | photo_signage | img_092.jpg | RGB 350×430 | RGB 350×430 | blur 6, brightness 119, flags ['blurry'] | (1, 3, 224, 224) torch.float32 | min -1.79 / max 1.53 | (1, 512) → L2-normalised |

## Reading the numbers

- The pictogram arrives with an alpha channel (`LA`: greyscale + alpha); a plain RGB conversion would drop the alpha and leave a black square (the first-run bug that `flatten_on_white` fixes), so it is composited on white first.
- The photographed sign's Laplacian variance falls below the blur threshold and is flagged `blurry`; the flag does not stop inference, it is surfaced as uncertainty context.
- Whatever the working size, the processor's resize and centre crop yield a `(1, 3, 224, 224)` float32 tensor, and `get_image_features` yields one 512-dimensional vector per image; CLIP compares this vector with text vectors by cosine.
- No OCR, no augmentation, no fine-tuning and no text extraction take place anywhere on this path.
