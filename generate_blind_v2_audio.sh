#!/usr/bin/env bash
set -euo pipefail

# Nordhaven Airport Assistant — independent final evaluation v1.1
# Six pre-written TTS cases. Generate each case once; do not create variants and select by model result.
# Output: WAV, mono, 16 kHz, 16-bit PCM.
# All six cases are TTS because real human recordings were not available at authoring time.

have_voice() {
  say -v '?' | awk '{print $1}' | grep -Fxq "$1"
}

pick_voice() {
  for v in "$@"; do
    if have_voice "$v"; then
      printf '%s\n' "$v"
      return 0
    fi
  done
  printf '\n'
}

VOICE_A="$(pick_voice Samantha Alex Daniel Karen Moira)"
VOICE_B="$(pick_voice Alex Daniel Karen Moira Samantha)"

if [[ -n "${VOICE_A}" && "${VOICE_B}" == "${VOICE_A}" ]]; then
  for v in Daniel Karen Moira Samantha Alex; do
    if [[ "$v" != "${VOICE_A}" ]] && have_voice "$v"; then
      VOICE_B="$v"
      break
    fi
  done
fi

echo "Voice A: ${VOICE_A:-macOS default}"
echo "Voice B: ${VOICE_B:-macOS default}"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

synth_one() {
  local out="$1"
  local voice="$2"
  local rate="$3"
  local text="$4"
  local txt="$tmpdir/${out}.txt"
  local aiff="$tmpdir/${out}.aiff"

  printf '%s\n' "$text" > "$txt"

  if [[ -n "$voice" ]]; then
    say -v "$voice" -r "$rate" -f "$txt" -o "$aiff"
  else
    say -r "$rate" -f "$txt" -o "$aiff"
  fi

  afconvert -f WAVE -d LEI16@16000 -c 1 "$aiff" "${out}.wav"
}

synth_one "AUD2_B01" "$VOICE_A" 174 "What time does the bus terminal close tonight?"
synth_one "AUD2_B02" "$VOICE_B" 180 "Is Harbour Café open at half past nine tonight?"
synth_one "AUD2_B03" "$VOICE_A" 168 "They've sent my luggage to belt five. Which reclaim area is that?"
synth_one "AUD2_B04" "$VOICE_B" 176 "I'm in Terminal 2 and need the security checkpoint. Which way is it?"
synth_one "AUD2_B05" "$VOICE_A" 194 "I've checked in and just need somewhere to sit down and eat before boarding, where's the restaurant?"

# Mild-noise case: synthesize the exact pre-written utterance once,
# then apply one deterministic mild stationary-noise degradation.
synth_one "AUD2_B06_clean_tmp" "$VOICE_B" 178 "Are taxis available after eleven at night?"

python3 - <<'PY'
import array, math, os, random, wave

src = "AUD2_B06_clean_tmp.wav"
dst = "AUD2_B06.wav"
random.seed(1101)

with wave.open(src, "rb") as r:
    params = r.getparams()
    frames = r.readframes(r.getnframes())

samples = array.array("h")
samples.frombytes(frames)
if not samples:
    raise SystemExit("AUD2_B06 source contains no samples.")

rms = math.sqrt(sum(s*s for s in samples) / len(samples))
noise_rms = max(1.0, rms / (10 ** (24.0 / 20.0)))  # approx. 24 dB SNR

out = array.array("h")
for s in samples:
    v = int(round(s + random.gauss(0.0, noise_rms)))
    out.append(max(-32768, min(32767, v)))

with wave.open(dst, "wb") as w:
    w.setparams(params)
    w.writeframes(out.tobytes())

os.remove(src)
PY

echo "Created:"
ls -1 AUD2_B01.wav AUD2_B02.wav AUD2_B03.wav AUD2_B04.wav AUD2_B05.wav AUD2_B06.wav
