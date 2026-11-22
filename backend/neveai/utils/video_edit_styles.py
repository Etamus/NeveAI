"""Shared render filters for timed effects and titles in the local editor."""
import re


def write_intro(path, title, duration, portrait):
    # ASS commands are fixed; text cannot add override blocks or extra events.
    title = re.sub(r"[\\{}\x00-\x1f]", " ", title).strip()
    if not title:
        return
    lines = []
    words = title.split()
    line = ""
    for word in words:
        if line and len(line) + len(word) > (21 if portrait else 32):
            lines.append(line)
            line = ""
        line = f"{line} {word}".strip()
    lines.append(line)
    width, height = (360, 640) if portrait else (640, 360)
    length = round(min(2.7, duration) * 100)
    intro = r"\N".join(lines)
    move = f"{{\\move(23,{height - 102},36,{height - 102},0,270)\\fad(190,260)}}"
    path.write_text(
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Intro,Arial,27,&H00FFFFFF,&H00FFFFFF,&H50101520,&HA0000000,-1,0,0,0,100,100,0,0,1,2,1,4,26,26,0,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:{length // 100:02}.{length % 100:02},Intro,,0,0,0,,{move}{intro}\n",
        encoding="utf-8",
    )




def motion_filter(motion, offset, width, height, fps):
    if motion == "none":
        return ""
    t = f"(t+{offset:.6f})"
    if motion in ("flash", "dip"):
        d = .13 if motion == "flash" else .26
        if offset >= d:
            return ""
        # Exposure is timed in the original clip even if another track splits this render.
        levels = f"0.48*max(0,1-{t}/{d})" if motion == "flash" else f"-0.76*max(0,1-{t}/{d})"
        return f",eq=brightness='{levels}':eval=frame"
    if motion == "push":
        frame = f"(on+{offset * fps:.4f})/{fps}"
        return (f",zoompan=z='1+0.16*sin(PI*min(1,{frame}/0.95))':"
                f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps={fps}")
    crop_w, crop_h = max(2, int(width / 1.14) // 2 * 2), max(2, int(height / 1.14) // 2 * 2)
    x = f"(iw-ow)*(0.5+0.46*exp(-7*{t}))"
    y = "(ih-oh)/2"
    if motion == "glitch":
        x = f"(iw-ow)*(0.5+0.43*sin(75*{t})*exp(-4*{t}))"
        y = f"(ih-oh)*(0.5+0.38*sin(103*{t})*exp(-4*{t}))"
        effect = f",chromashift=cbh=8:crh=-8:enable='lt({t},0.23)'"
    else:
        effect = f",avgblur=sizeX=9:sizeY=1:enable='lt({t},0.12)'"
    return f",crop={crop_w}:{crop_h}:x='{x}':y='{y}',scale={width}:{height}{effect}"
