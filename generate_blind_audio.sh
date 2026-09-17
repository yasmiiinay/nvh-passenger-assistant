#!/usr/bin/env bash
set -euo pipefail

# Nordhaven blind-audio generator.
# Generates each pre-written case once. No variant selection is performed.
# Run on macOS from the directory where you want AUD_B01.wav ... AUD_B06.wav.

have_voice() {
  say -v '?' | awk '{print $1}' | grep -Fxq "$1"
}

pick_first_voice() {
  for v in "$@"; do
    if have_voice "$v"; then
      printf '%s\n' "$v"
      return 0
    fi
  done
  # Empty string means use the macOS default voice.
  printf '\n'
}

VOICE_A="$(pick_first_voice Samantha Alex Daniel Karen Moira)"
VOICE_B="$(pick_first_voice Alex Daniel Karen Moira Samantha)"

# If only one preferred English voice is installed, try to find a second distinct one.
if [[ -n "${VOICE_A}" && "${VOICE_B}" == "${VOICE_A}" ]]; then
  for v in Alex Daniel Karen Moira Samantha; do
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

  # 16-bit PCM, mono, 16 kHz WAV suitable for speech recognition.
  afconvert -f WAVE -d LEI16@16000 -c 1 "$aiff" "${out}.wav"
}

synth_one "AUD_B01" "$VOICE_A" 174 "Is the arrivals information desk still open at ten tonight?"
synth_one "AUD_B02" "$VOICE_B" 182 "Which way is the airport train station from the terminal?"
synth_one "AUD_B03" "$VOICE_A" 168 "My boarding pass says gate A11. Which pier should I follow?"
synth_one "AUD_B04" "$VOICE_B" 176 "I'm in Terminal 2 and need an accessible toilet. Where is it?"
synth_one "AUD_B05" "$VOICE_A" 194 "I've checked in and just need somewhere to eat before boarding, where's the sit-down restaurant?"

# AUD_B06 is generated once from the exact script, then mild stationary background noise
# is added deterministically. The temporary clean file is not retained.
synth_one "AUD_B06_clean_tmp" "$VOICE_B" 178 "Does the bus terminal stay open past midnight?"

python3 - <<'PY'
import math, random, wave, array, os

src = "AUD_B06_clean_tmp.wav"
dst = "AUD_B06.wav"
random.seed(7016)

with wave.open(src, "rb") as r:
    params = r.getparams()
    frames = r.readframes(r.getnframes())

samples = array.array("h")
samples.frombytes(frames)

if not samples:
    raise SystemExit("No audio samples generated for AUD_B06.")

rms = math.sqrt(sum(s*s for s in samples) / len(samples))
# Mild degradation: approximately 24 dB SNR.
target_noise_rms = max(1.0, rms / (10 ** (24.0 / 20.0)))

out = array.array("h")
for s in samples:
    n = random.gauss(0.0, target_noise_rms)
    v = int(round(s + n))
    out.append(max(-32768, min(32767, v)))

with wave.open(dst, "wb") as w:
    w.setparams(params)
    w.writeframes(out.tobytes())

os.remove(src)
PY

echo "Created:"
ls -1 AUD_B01.wav AUD_B02.wav AUD_B03.wav AUD_B04.wav AUD_B05.wav AUD_B06.wav
