"""Native Linux port of VhsDecodeAutoAudioAlign "stream-align".

Reads a WAV/FLAC (anything libsndfile can read), takes sample rate, channel
count and sample format from the file header, aligns it to the video fields
recorded in a vhs-decode .tbc.json and writes a WAV/FLAC file.

The projection uses exactly the same integer arithmetic as the C# original
(including its 21 bit precision limit), so for the same input the output
samples are identical to `mono VhsDecodeAutoAudioAlign.exe stream-align`.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass

import numpy as np
import soundfile as sf

FIELD_RATE_PAL = (50, 1)
FIELD_RATE_NTSC = (60000, 1001)

# Output samples processed per step, ~20 s at 48 kHz
CHUNK_SAMPLES = 1024 * 1024


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def _first_primes(count):
    primes = []
    n = 2
    while len(primes) < count:
        if all(n % p for p in primes if p * p <= n):
            primes.append(n)
        n += 1
    return primes


# The original normalizes with a fixed list of the first 1000 primes (2..7919)
# instead of a full gcd, keep that for identical rounding.
_PRIMES = _first_primes(1000)

_SCALING_LIMIT = 1024 * 1024 * 2


def limit_precision_21bit(nom, den):
    """Port of ProjectionMisc.LimitPrecision21Bit, returns (nom, den)."""
    for p in _PRIMES:
        while nom % p == 0 and den % p == 0:
            nom //= p
            den //= p
    if nom > _SCALING_LIMIT:
        scale = nom // _SCALING_LIMIT + 1
        nom //= scale
        den //= scale
    return nom, den


def field_rate_from_system(system):
    system = (system or "").lower().strip(" \t\n\r")
    if not system:
        raise ValueError("The TBC json did not contain the video system")
    if system.startswith("pal-m"):
        return FIELD_RATE_NTSC
    if "pal" in system and "60" not in system:
        return FIELD_RATE_PAL
    if "ntsc" in system and "50" not in system:
        return FIELD_RATE_NTSC
    raise ValueError("Unsupported video system '%s'" % system)


def read_tbc_json(path):
    """Returns (field_rate, field file locations) from a .tbc.json."""
    with open(path, "rb") as f:
        doc = json.load(f)

    params = doc.get("videoParameters")
    if params is None:
        raise ValueError("The TBC json did not contain videoParameters")
    field_rate = field_rate_from_system(params.get("system"))

    # ld-decode-tools may write fileLoc as signed 32 bit, undo the rollover
    # (see https://gitlab.com/wolfre/vhs-decode-auto-audio-align/-/issues/13)
    locs = []
    correction = 0
    last = None
    for field in doc.get("fields") or []:
        loc = int(field.get("fileLoc", 0))
        if loc < 0 and (last is None or last > 0):
            correction += 0x100000000
            log("Fixing signed 32 bit rollover in field %s" % field.get("seqNo"))
        last = loc
        locs.append(loc + correction)

    if not locs:
        raise ValueError("The TBC json contains no fields")
    return field_rate, locs


@dataclass
class Section:
    first_field: int
    field_count: int
    speed_nom: int
    speed_den: int
    scaled_input_start: int
    scaled_output_start: int


def build_projection(field_locs, field_rate, rf_rate_hz, audio_rate_hz):
    """Port of LinearStreamProjection: gap-less sections with a linear speed each."""
    rate_nom, rate_den = field_rate

    def ideal_field_offset(fields):
        return (fields * rf_rate_hz * rate_den) // rate_nom

    # Split into sections at dropped / out of tolerance fields
    avg_len = (rf_rate_hz * rate_den) // rate_nom
    tol = avg_len // 3
    sections = []
    current = []
    for loc in field_locs:
        if current and not (avg_len - tol < loc - current[-1] < avg_len + tol):
            sections.append(current)
            current = []
        current.append(loc)
    if current:
        sections.append(current)

    scale_nom, scale_den = limit_precision_21bit(audio_rate_hz, rf_rate_hz)
    log("Reference to output sample rate scaling: %d/%d" % (scale_nom, scale_den))

    result = []
    next_output_start = 0
    for offsets in sections:
        output_start = next_output_start
        next_output_start += ideal_field_offset(len(offsets))
        if len(offsets) < 2:
            nom, den = 1, 1
        else:
            nom, den = limit_precision_21bit(offsets[-1] - offsets[0],
                                             ideal_field_offset(len(offsets) - 1))
        section = Section(
            first_field=offsets[0],
            field_count=len(offsets),
            speed_nom=nom,
            speed_den=den,
            scaled_input_start=(offsets[0] * scale_nom) // scale_den,
            scaled_output_start=(output_start * scale_nom) // scale_den,
        )
        log("Section @%d -> %d with %d fields, %d/%d factor=%.9f" % (
            section.first_field, output_start, section.field_count, nom, den, nom / den))
        result.append(section)
    return result


def project(section, out_idx):
    """Output sample indices (uint64 array) -> input sample indices."""
    rel = out_idx - np.uint64(section.scaled_output_start)
    return rel * np.uint64(section.speed_nom) // np.uint64(section.speed_den) \
        + np.uint64(section.scaled_input_start)


def _read_dtype(subtype):
    if subtype == "DOUBLE":
        return "float64"
    if subtype == "FLOAT":
        return "float32"
    # int32 holds every PCM format losslessly (libsndfile left-justifies)
    return "int32"


_BITS_TO_SUBTYPE = {"8": "PCM_U8", "16": "PCM_16", "24": "PCM_24", "32": "PCM_32", "float": "FLOAT"}
_FORMAT_BY_EXT = {".wav": "WAV", ".flac": "FLAC", ".w64": "W64", ".rf64": "RF64", ".aiff": "AIFF", ".aif": "AIFF"}


def choose_output_format(path, in_subtype, bits, channels, frames):
    ext = os.path.splitext(path)[1].lower()
    fmt = _FORMAT_BY_EXT.get(ext)
    if fmt is None:
        raise ValueError("Unsupported output file extension '%s' (use %s)" % (ext, ", ".join(_FORMAT_BY_EXT)))

    subtype = _BITS_TO_SUBTYPE[bits] if bits else in_subtype
    if not sf.check_format(fmt, subtype):
        fallback = "PCM_24" if fmt == "FLAC" else "PCM_32"
        log("Output format %s does not support %s, using %s" % (fmt, subtype, fallback))
        subtype = fallback

    # RIFF WAV is limited to 4 GiB, switch to RF64 for long captures
    if fmt == "WAV":
        bytes_per_sample = {"PCM_U8": 1, "PCM_16": 2, "PCM_24": 3}.get(subtype, 8 if subtype == "DOUBLE" else 4)
        if frames * channels * bytes_per_sample > 0xFFFFFFFF - 1024:
            log("Output will exceed 4 GiB, writing RF64 instead of plain WAV")
            fmt = "RF64"
    return fmt, subtype


def parse_channels(spec, available):
    if not spec:
        return None
    try:
        chans = [int(c) - 1 for c in spec.split(",")]
    except ValueError:
        raise ValueError("--channels expects a list like 1,2")
    for c in chans:
        if not 0 <= c < available:
            raise ValueError("Channel %d does not exist, input has %d channels" % (c + 1, available))
    return chans


def default_output_path(json_path):
    base = json_path
    for suffix in (".json", ".tbc"):
        if base.lower().endswith(suffix):
            base = base[:-len(suffix)]
    return base + "_al.wav"


def align(args):
    field_rate, field_locs = read_tbc_json(args.json)
    log("Loaded %d fields from '%s'" % (len(field_locs), args.json))

    with sf.SoundFile(args.input) as src:
        rate, in_channels, n_in = src.samplerate, src.channels, src.frames
        log("Input '%s': %s/%s, %d Hz, %d channels, %d samples (%.1f s)" % (
            args.input, src.format, src.subtype, rate, in_channels, n_in, n_in / rate))
        if not src.seekable():
            raise ValueError("Input must be seekable")

        chans = parse_channels(args.channels, in_channels)
        out_channels = len(chans) if chans else in_channels
        sections = build_projection(field_locs, field_rate, args.rf_video_sample_rate_hz, rate)

        output = args.output or default_output_path(args.json)
        if os.path.exists(output) and not args.overwrite:
            raise FileExistsError("Output file '%s' exists, use --overwrite" % output)
        fmt, subtype = choose_output_format(output, src.subtype, args.bits, out_channels, n_in)
        log("Output '%s': %s/%s, %d channels" % (output, fmt, subtype, out_channels))

        dtype = _read_dtype(src.subtype)
        written = 0
        last_report = time.monotonic()
        with sf.SoundFile(output, "w", samplerate=rate, channels=out_channels, format=fmt, subtype=subtype) as dst:
            for i, section in enumerate(sections):
                end = sections[i + 1].scaled_output_start if i + 1 < len(sections) else None
                pos = section.scaled_output_start
                done = False
                while end is None or pos < end:
                    stop = pos + CHUNK_SAMPLES if end is None else min(pos + CHUNK_SAMPLES, end)
                    in_idx = project(section, np.arange(pos, stop, dtype=np.uint64))
                    # like the original: stop at the first sample beyond the input
                    beyond = np.flatnonzero(in_idx >= np.uint64(n_in))
                    if beyond.size:
                        in_idx = in_idx[:beyond[0]]
                        done = True
                    if in_idx.size:
                        lo = int(in_idx[0])
                        hi = int(in_idx[-1]) + 1
                        src.seek(lo)
                        block = src.read(hi - lo, dtype=dtype, always_2d=True)
                        data = block[(in_idx - np.uint64(lo)).astype(np.intp)]
                        if chans:
                            data = data[:, chans]
                        dst.write(data)
                        written += len(in_idx)
                    if done:
                        break
                    pos = stop
                    now = time.monotonic()
                    if now - last_report >= 2:
                        log("... %.1f s of output written" % (written / rate))
                        last_report = now
                if done:
                    break

    log("Done: %d output samples (%.3f s) from %d input samples (%.3f s)" % (
        written, written / rate, n_in, n_in / rate))


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="vhs-decode-aaa",
        description="Align a (HiFi or linear) audio capture to the video fields of a vhs-decode .tbc.json. "
                    "Sample rate, channels and sample format are read from the input file.")
    p.add_argument("--json", required=True, help="the .tbc.json of the decoded video")
    p.add_argument("-i", "--input", required=True, help="audio file to align (WAV, FLAC, ... anything libsndfile reads)")
    p.add_argument("-o", "--output", help="output file, format from extension (.wav, .flac, .w64, .rf64); "
                                          "default: <json name without .tbc.json>_al.wav")
    p.add_argument("-b", "--bits", choices=sorted(_BITS_TO_SUBTYPE), help="output sample format, default: same as input")
    p.add_argument("-c", "--channels", help="only write these input channels, 1-based, e.g. 1,2 to drop the head switch channel")
    p.add_argument("--rf-video-sample-rate-hz", type=int, default=40000000,
                   help="sample rate of the original RF video capture (default 40000000)")
    p.add_argument("--overwrite", action="store_true", help="overwrite an existing output file")
    args = p.parse_args(argv)

    try:
        align(args)
    except (OSError, ValueError, sf.LibsndfileError) as e:
        log("Error: %s" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
