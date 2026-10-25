# vhs-decode-aaa (native Python port)

A native Linux port of the `stream-align` action, no mono / .NET needed.
It reads WAV, FLAC (and everything else libsndfile reads) directly, takes
sample rate, channel count and bit depth from the file header and writes the
aligned audio as WAV/FLAC/W64/RF64.

The projection uses the same integer arithmetic as the C# version, so the
aligned samples are identical to the output of
`sox | mono VhsDecodeAutoAudioAlign.exe stream-align | sox`.

## Install

```bash
pipx install ./python
```

Dependencies are `numpy` and `soundfile` (which bundles libsndfile).

## Usage

```bash
# HiFi/linear FLAC -> aligned WAV, same bit depth as the input
vhs-decode-aaa --json video.tbc.json -i audio.flac -o audio_al.wav

# 3 channel 24 bit linear capture from the clock gen: drop the head switch channel, write 16 bit FLAC
vhs-decode-aaa --json video.tbc.json -i linear-audio-46875sps-3ch-24bit-le.wav -c 1,2 -b 16 -o linear_al.flac
```

Without `-o` the output is written next to the json as `<name>_al.wav`.
WAV output that would exceed 4 GiB is written as RF64 automatically.
Use `--rf-video-sample-rate-hz` if the RF video was not captured at 40 MSps.
