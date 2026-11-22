"""Burn animated captions independently of the clean, downloadable SRT."""


def ass_time(t):
    seconds, cs = divmod(round(t*100), 100)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes//60}:{minutes%60:02}:{seconds:02}.{cs:02}"


def write_animated(path, cues, style, width, height):
    h, w = 288, round(288*width/height)
    align, y = {"top": (8, 20), "bottom": (2, h-20), "center": (5, h//2)}[style.position]
    x = {"left": round(.06*w), "center": w//2, "right": round(.94*w)}[style.horizontal]
    align += {"left":-1,"center":0,"right":1}[style.horizontal]
    cues = list(cues)
    default = (style.font, style.size, style.theme)
    styles = {default: "Main"}

    def appearance(cue):
        if len(cue) < 8:
            return default
        return tuple(value or fallback for value, fallback in zip(cue[5:], default))

    for cue in cues:
        styles.setdefault(appearance(cue), f"Cue{len(styles)}")
    definitions = []
    for (font, size, theme), name in styles.items():
        color = "&H005EE4FF" if theme == "highlight" else "&H00FFFFFF"
        definitions.append(f"Style: {name},{font},{size},{color},{color},&H60000000,&H80000000,0,0,0,0,100,100,0,0,{3 if theme=='box' else 1},2,0,{align},8,8,20,1")
    style_table = "\n".join(definitions)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
{style_table}
[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    with path.open("w", encoding="utf8") as out:
        out.write(header)
        for cue in cues:
            a,b,text,*placement = cue
            name = styles[appearance(cue)]
            horizontal, position = placement[:2] or (None, None)
            anchor, y = {"top": (8,20), "center": (5,h//2), "bottom": (2,h-20)}[position or style.position]
            side = horizontal or style.horizontal
            x = {"left":round(.06*w), "center":w//2, "right":round(.94*w)}[side]
            anchor += {"left":-1, "center":0, "right":1}[side]
            text = text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n"," ")
            anim = style.animation
            tags = rf"\pos({x},{y})"
            if anim in ("rise","drop"):
                tags = rf"\move({x},{y+(9 if anim=='rise' else -9)},{x},{y},0,180)"
            elif anim == "fade":
                tags += r"\fad(180,120)"
            elif anim == "slide":
                tags = rf"\move({x-14},{y},{x},{y},0,200)"
            elif anim == "zoom":
                tags += r"\fscx60\fscy60\t(0,200,\fscx100\fscy100)"
            elif anim == "blur":
                tags += r"\fad(140,0)\blur4\t(0,200,\blur0)"
            elif anim == "spin":
                tags += r"\frz18\t(0,220,\frz0)"
            elif anim == "pulse":
                tags += r"\fscx82\fscy82\t(0,100,\fscx108\fscy108)\t(100,200,\fscx100\fscy100)"
            elif anim == "wave":
                tags += r"\frz-3\t(0,110,\frz3)\t(110,240,\frz0)"
            def line(start, stop, visible):
                if ass_time(stop) != ass_time(start):
                    out.write(f"Dialogue: 0,{ass_time(start)},{ass_time(stop)},{name},,0,0,0,,{{\\an{anchor}{tags}}}{visible}\n")
            if anim == "type":
                # Reveal on media time; seeking and exporting never restart the animation.
                step = min(.035, (b-a)*.55/max(1,len(text)))
                for i in range(len(text)):
                    line(a+step*i, a+step*(i+1) if i+1<len(text) else b, text[:i+1])
            else:
                line(a,b,text)
