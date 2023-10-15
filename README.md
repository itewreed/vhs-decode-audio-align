# VHS-decode Auto Audio Align

A project to automatically align (RF) HiFi and linear audio captures to a video RF capture.
For this to work all 3 streams need to be captured with a synchronous clock source, like [cxadc-clock-generator-audio-adc](https://gitlab.com/wolfre/cxadc-clock-generator-audio-adc)

The app is written in C#/.NET, targeting Framework 4.7.2 and will work on Windows without additional requirements.
On linux / mac the amazing [mono project](https://www.mono-project.com) can be used to run.

## Example for linear audio alignment

```bash
local rate_hz=46875

sox -D \
	20231008-143140-linear-audio-46875sps-3ch-24bit-le.wav \
	-t raw -b 24 -c 3 -L -e unsigned-integer - \
| mono VhsDecodeAutoAudioAlign.exe stream-align \
	--sample-size-bytes $(( 3 * 3 )) \
	--stream-sample-rate-hz $rate_hz \
	--json video.tbc.json \
| sox -D \
	-t raw -r $rate_hz -b 24 -c 3 -L -e unsigned-integer - \
	linear-aligned.wav
```

[*TODO* more docu](https://gitlab.com/wolfre/vhs-decode-auto-audio-align/-/issues/3)
