# Independent evaluation set v3: authoring brief

You are writing a held-back evaluation set for a passenger-assistance chatbot at
**Nordhaven International Airport (NVH)**, a fictional airport. Someone else
built the chatbot. Your set will be run against it exactly once, after it has
been frozen, and nobody may change the set or the chatbot after seeing the
results. What you write therefore decides what the evaluation can show, so
write what a passenger would realistically ask and label what the airport data
supports, not what you guess the chatbot does.

## What you may use

Only these two attached files:

- `airport_spec.md`: the written description of the airport.
- `airport_kb.json`: the 32 knowledge-base records (`record_id`, name,
  category, terminal, level, zone, hours, directions, accessibility and
  related fields).

Do not use or ask for anything else about the chatbot: its code, rules, word
lists, thresholds, earlier test sets or results, development queries, known
weaknesses or reports. If you already know any of these, say so in the self
check. Do not run, imagine running or tune cases against the chatbot.

## Labels

Each case gets one expected decision:

| decision | use when |
|---|---|
| `answer` | The KB holds exactly one record that answers the request as asked. Give its `record_id`. |
| `clarify` | The KB holds the service but the request fits more than one record (for example two terminals) and nothing in the request decides between them. Give the `expected_category`; leave the record empty. |
| `redirect` | The request needs live or official information that the KB deliberately does not answer (flight status, gate changes, delays). Give the category if one applies. |
| `abstain` | The request is outside what the airport data covers (a service the specification excludes or the KB does not hold), not about the airport, or not usable input. |
| `conflict` | Multimodal only: the photo and the words/voice point to different services. |

Categories must come from this list: gate, check_in, security, baggage,
lost_property, information, lounge, restaurant, restroom, accessibility,
transport, medical.

Rules for labelling:

1. Write every label from the specification and KB before creating any image
   or audio file.
2. A case should test one thing. If a request is both ambiguous and in a
   language the system may not support, split it into two cases or drop one
   factor.
3. Do not force an answer on an ambiguous request, and do not give an answer
   to a service the airport data does not contain.
4. No expectation may depend on reading text inside an image (no OCR). A sign
   whose meaning is only in its words is labelled from what a passenger could
   know without reading it, or left out.
5. Explain each label in one sentence in `reason`, citing the record or the
   specification section.

## What to deliver

Exactly these files, with these names and columns (UTF-8 CSV, header row
first, no extra columns):

**`final_blind_v3_text.csv`**: 20 rows.
`blind_id,query,expected_decision,expected_category,expected_record_id,reason`
Use ids `T3_B001` … `T3_B020`. Aim for a realistic mix of decisions (most
cases answerable, several ambiguous, some redirect, some out of scope) and of
phrasing (short, long, indirect, with a location, a time, an identifier such
as a gate, desk or belt number, typos a passenger might make).

**`final_blind_v3_images_manifest.csv`**: 8 rows.
`image_id,image_description,expected_decision,expected_category,expected_record_id,quality_stratum,reason`
Ids `IMG3_B01` … `IMG3_B08`. `quality_stratum` is one of clean, photographed,
angled, blurred, out_of_scope. Include at least two out-of-scope images
(`abstain`). Describe each image precisely enough that another person can
source or draw it without seeing your intentions: the symbol, style,
background, viewpoint and any degradation. Label images with the same rule as
text: `answer` only when the image alone points to exactly one KB record,
otherwise `clarify` with the category.

**`final_blind_v3_audio_manifest.csv`**: 6 rows.
`audio_id,spoken_text,expected_decision,expected_category,expected_record_id,audio_condition,recording_source,reason`
Ids `AUD3_B01` … `AUD3_B06`. `audio_condition` is one of clean, fast_natural,
identifier, mild_noise, terminal_specific. `recording_source` is `TTS` or
`human`, and states how the file will actually be made. `spoken_text` is the
exact script; the recording must say exactly that.

**`final_blind_v3_multimodal.csv`**: 12 rows.
`scenario_id,modality,text,image_id,audio_id,expected_decision,expected_category,expected_record_id,expected_route,reason`
Ids `MM3_B01` … `MM3_B12`. `modality` is one of image-only, voice-only,
text+image, voice+image. Reuse the image and audio ids above; `text` is empty
unless the modality includes text. `expected_route` is one of:

| expected_route | meaning |
|---|---|
| `fuse_consistent` | Words or voice and photo agree; both are used. |
| `flag_cross_modal_conflict` | They disagree; the passenger should be told. |
| `image_resolves_deictic` | The words point at the photo ("where is this?") and the photo supplies the service. |
| `image_only` | Photo alone. |
| `voice_only` | Voice alone. |

**`generate_blind_v3_audio.sh`** (only if any `recording_source` is `TTS`): a
macOS script that makes each TTS clip once with `say` and `afconvert` as WAV,
mono, 16 kHz, 16-bit PCM, named `AUD3_B0N.wav`. No variants; no selecting
among takes.

**`SELF_CHECK_V3.txt`**: what you used, what you did not consult, anything
you already knew about the chatbot, counts per file, the decision
distribution, any label you changed after first writing it and why, and the
limitations of the set.

## Recording and image rules for the person making the files

- Make each file once from its manifest row. Re-record or re-source only for
  a technical fault you can hear or see (clipping, silence, a corrupt file),
  never after trying it on the chatbot.
- Human recordings read `spoken_text` verbatim, in one take where possible.
- Images are saved as PNG with the ids above. Photographs must contain no
  identifiable people, boarding passes or personal documents, and no
  third-party logos.
- If an image cannot be found or drawn as described, change the description
  and the label together before any evaluation, and record the change in the
  self check.

## Freezing

When all files exist, record SHA-256 hashes (`shasum -a 256` on macOS):

```
shasum -a 256 final_blind_v3_text.csv final_blind_v3_images_manifest.csv \
  final_blind_v3_audio_manifest.csv final_blind_v3_multimodal.csv SELF_CHECK_V3.txt > blind_v3_manifests_sha256.txt
shasum -a 256 IMG3_B0*.png > blind_v3_images_sha256.txt
shasum -a 256 AUD3_B0*.wav > blind_v3_audio_sha256.txt
```

After hashing, nothing in the set changes.
