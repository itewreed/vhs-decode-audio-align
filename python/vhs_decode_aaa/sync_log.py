"""Human readable log of the places where the audio had to be re-synchronised.

Every section boundary of the projection is a discontinuity in the tbc: the
decoder skipped fields, went back to an earlier field, or a field had an odd
length. At each one the audio jumps (or repeats) to stay in sync with the
decoded video. The log lists them with the position in the decoded video, so
a user can look up the spot in the video and check it.
"""

from datetime import datetime


def _field_time(index, field_rate):
    nom, den = field_rate
    return index * den / nom


def hms(seconds):
    """Real time as HH:MM:SS.mmm"""
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d.%03d" % (h, m, s, ms)


def timecode(field_index, field_rate):
    """HH:MM:SS:FF of the frame holding this field, drop frame (;) for 59.94 fields/s."""
    frame = field_index // 2
    if field_rate == (50, 1):
        fps, sep = 25, ":"
    else:
        # SMPTE drop frame: skip frame numbers 0 and 1 every minute except every 10th
        tens, rest = divmod(frame, 17982)
        frame += 18 * tens + (2 * ((rest - 2) // 1798) if rest > 1 else 0)
        fps, sep = 30, ";"
    ff = frame % fps
    s = frame // fps
    return "%02d:%02d:%02d%s%02d" % (s // 3600, s // 60 % 60, s % 60, sep, ff)


def _plural(n, word):
    return "%d %s%s" % (n, word, "s" if n != 1 else "")


def _classify(gap_fields, slots=1):
    """gap_fields: capture distance covered by `slots` decoded fields, in nominal fields."""
    if slots > 1:
        # back jump directly followed by a forward jump: the decoder went back,
        # decoded a field again and then skipped ahead to where it should be
        missing = max(int(round(gap_fields)) - 1, 0)
        if missing == 0:
            return "field repeated (decoder re-sync)"
        return "field repeated, %s skipped (decoder re-sync)" % _plural(missing, "field")
    if gap_fields <= 0:
        return "went back %s (field repeated)" % _plural(int(round(1 - gap_fields)), "field")
    missing = int(round(gap_fields)) - 1
    if missing >= 1:
        return "%s skipped" % _plural(missing, "field")
    if gap_fields < 1:
        return "short field (%d%% of nominal)" % round(gap_fields * 100)
    return "long field (%d%% of nominal)" % round(gap_fields * 100)


def _skipped(gap_fields, slots):
    return max(int(round(gap_fields)) - 1, 0) if gap_fields > 0 else 0


def _speed_ppm(section):
    return (section.speed_nom / section.speed_den - 1) * 1e6


def write_sync_log(path, tbc, sections, json_path, input_path, output_path,
                   audio_rate, rf_rate, input_samples, output_samples):
    field_rate = tbc.field_rate
    nom, den = field_rate
    avg_field_len = rf_rate * den / nom
    to_ms = 1000 / audio_rate

    locs = tbc.field_locs
    jumps = []
    for prev, sec in zip(sections, sections[1:]):
        # where the audio would have continued without re-syncing
        expected = (sec.scaled_output_start - prev.scaled_output_start) * prev.speed_nom // prev.speed_den \
            + prev.scaled_input_start
        jumps.append((sec.first_index, (sec.scaled_input_start - expected) * to_ms))

    # events: (field index, capture gap in fields, decoded slots, audio jump ms, running total ms)
    events = []
    total_ms = 0.0
    i = 0
    while i < len(jumps):
        idx, jump_ms = jumps[i]
        slots = 1
        back = locs[idx] <= locs[idx - 1]
        if back and i + 1 < len(jumps) and jumps[i + 1][0] == idx + 1 and locs[idx + 1] > locs[idx - 1]:
            slots = 2
            jump_ms += jumps[i + 1][1]
            i += 1
        gap_fields = (locs[idx + slots - 1] - locs[idx - 1]) / avg_field_len
        total_ms += jump_ms
        events.append((idx, gap_fields, slots, jump_ms, total_ms))
        i += 1

    video_fields = len(tbc.field_locs)
    video_s = _field_time(video_fields, field_rate)
    skipped = sum(_skipped(g, n) for _, g, n, _, _ in events)
    repeated = sum(1 for _, g, n, _, _ in events if n > 1 or g <= 0)
    # short sections are dominated by the jitter of the field positions
    min_fields = int(10 * nom / den)
    speeds = [_speed_ppm(s) for s in sections if s.field_count >= min_fields]

    lines = [
        "vhs-decode-aaa sync log, %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "tbc json:     %s" % json_path,
        "audio input:  %s" % input_path,
        "audio output: %s" % output_path,
        "video:        %s, %g fields/s, %d fields (%s), RF %d Hz" % (
            tbc.system, nom / den, video_fields, hms(video_s), rf_rate),
        "audio:        %d Hz, input %s, output %s" % (
            audio_rate, hms(input_samples / audio_rate), hms(output_samples / audio_rate)),
        "",
        "Video starts at capture time %s, the audio before it is not used." % hms(tbc.field_locs[0] / rf_rate),
    ]
    if speeds:
        lines.append("Playback speed vs. nominal: %+.0f .. %+.0f ppm (%d of %d sections, those >= 10 s)" % (
            min(speeds), max(speeds), len(speeds), len(sections)))
    lines.append("")

    if not events:
        lines.append("No discontinuities: no fields were skipped, the audio was only stretched/compressed.")
    else:
        lines += [
            "%d re-syncs: %s skipped, %s repeated, net audio jump %+.1f ms" % (
                len(events), _plural(skipped, "field"), _plural(repeated, "field"), total_ms),
            "",
            "Positions refer to the decoded video (tbc field index, timecode HH:MM:SS:FF, real time).",
            "Audio jump: + = audio skipped forward, - = audio repeated; total = sum of all jumps so far.",
            "",
            "%8s  %-11s  %-12s  %8s  %-12s  %-52s  %10s  %10s" % (
                "field", "timecode", "video time", "seqNo", "capture time", "event", "audio jump", "total"),
        ]
        for idx, gap_fields, slots, jump_ms, total in events:
            lines.append("%8d  %-11s  %-12s  %8s  %-12s  %-52s  %+7.1f ms  %+7.1f ms" % (
                idx, timecode(idx, field_rate), hms(_field_time(idx, field_rate)),
                tbc.seq_nos[idx] if tbc.seq_nos[idx] is not None else "?",
                hms(locs[idx] / rf_rate), _classify(gap_fields, slots), jump_ms, total))

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return len(events), skipped, total_ms
