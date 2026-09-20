#!/bin/bash
# generate_blind_v3_audio.sh
# Makes the TTS clips of the v3 blind evaluation set, once each, on macOS.
#
# Covers only the rows of final_blind_v3_audio_manifest.csv whose
# recording_source is TTS: AUD3_B01, AUD3_B03, AUD3_B05, AUD3_B06.
# AUD3_B02 (fast_natural) and AUD3_B04 (mild_noise) are human recordings and
# are NOT produced here; they are read verbatim from the manifest in one take.
#
# Output: AUD3_B0N.wav, WAV, mono, 16 kHz, 16-bit little-endian PCM.
# Each clip is made once. There are no variants and no takes to choose between.
# Re-run only after deleting a file that has an audible technical fault
# (clipping, silence, corruption) - never after trying a clip on the chatbot.

set -euo pipefail

VOICE="Daniel"      # fixed voice, so the run is reproducible
RATE=175            # fixed rate (words per minute), macOS default speaking rate

make_clip () {
  local id="$1"
  local text="$2"

  if [ -f "${id}.wav" ]; then
    echo "${id}.wav already exists - leaving it untouched."
    return 0
  fi

  say -v "$VOICE" -r "$RATE" -o "${id}.aiff" "$text"
  afconvert -f WAVE -d LEI16@16000 -c 1 "${id}.aiff" "${id}.wav"
  rm -f "${id}.aiff"
  echo "wrote ${id}.wav"
}

make_clip "AUD3_B01" "Where is the lost property office?"
make_clip "AUD3_B03" "How do I get to gate B twelve?"
make_clip "AUD3_B05" "I am in Terminal two, where is the information desk?"
make_clip "AUD3_B06" "Where is the nearest toilet?"

echo
echo "Verify format (expect: 1 channel, 16000 Hz, 16-bit signed integer):"
for f in AUD3_B01.wav AUD3_B03.wav AUD3_B05.wav AUD3_B06.wav; do
  [ -f "$f" ] && afinfo "$f" | sed -n '2,4p'
done
