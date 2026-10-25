# vhs-decode-aaa (native Python port)

A native Linux port of the `stream-align` and `gen-drift-csv` actions, no mono / .NET needed.
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
`stream-align` is the default command and may be left out.

## Sync log

`stream-align` writes `<output without extension>.sync.log` next to the
output (`--log FILE` to choose another name, `--no-log` to switch it off).
It lists every place where fields were missing or out of order in the tbc
and the audio had to be re-synchronised, with the position in the decoded
video, so the spot can be checked in the video:

```
   field  timecode     video time       seqNo  capture time  event                                                 audio jump       total
      29  00:00:00:14  00:00:00.580        30  00:00:03.275  1 field skipped                                         +19.9 ms    +19.9 ms
     778  00:00:15:14  00:00:15.560       777  00:00:18.234  field repeated, 1 field skipped (decoder re-sync)        -2.4 ms    +31.4 ms
```

- `field`: index of the field in the tbc / decoded video
- `timecode`: HH:MM:SS:FF of the frame in the decoded video (drop frame `HH:MM:SS;FF` for NTSC)
- `video time`, `capture time`: real time in the decoded video and in the RF capture
- `audio jump`: `+` audio was skipped, `-` audio was repeated; `total` is the running sum

The header also shows where the video starts in the capture and the playback
speed deviation of the tape.

## Drift CSV

```bash
vhs-decode-aaa gen-drift-csv --json video.tbc.json --csv-output my-tape.csv
```

Writes the same columns as the C# version. Numbers always use `.` as decimal
separator, independent of the system locale.
