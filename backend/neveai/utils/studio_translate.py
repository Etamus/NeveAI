"""Text-only caption translation. The worker exits (and frees RAM) after each edit."""
import json
import os
import re
import sys
from pathlib import Path

REPO = "JustFrederik/nllb-200-distilled-600M-ct2-int8"
REV = "302d78f00e6fdb50a1064059df7c392b735e9d05"
FILES = ("model.bin", "config.json", "sentencepiece.bpe.model", "shared_vocabulary.txt")
BR_REPO = "gow-solucoes/opus-mt-en-pt-ct2"
BR_REV = "884d2305736eb9c15e297bd2cb7fc95727283b32"
BR_FILES = ("model.bin", "config.json", "source.spm", "target.spm", "shared_vocabulary.json")
LANGUAGES = {"pt": "por_Latn", "en": "eng_Latn", "es": "spa_Latn", "fr": "fra_Latn",
             "de": "deu_Latn", "it": "ita_Latn", "ja": "jpn_Jpan"}


def translate(texts, source, target, cache):
    import ctranslate2
    import sentencepiece as sp
    from huggingface_hub import snapshot_download

    if source not in LANGUAGES or target not in LANGUAGES or source == target:
        raise ValueError("Choose two different languages.")
    brazil = target == "pt"
    if brazil:
        if source != "en":
            texts = translate(texts, source, "en", cache)
        # OPUS expects one sentence per input and has a trained Brazilian target token.
        groups = [re.split(r"(?<=[.!?])\s+", t.strip()) for t in texts]
        texts = [part for group in groups for part in group]
        cache = cache / "en-pt-br"
    files, repo, rev = (BR_FILES, BR_REPO, BR_REV) if brazil else (FILES, REPO, REV)
    if not all((cache / name).is_file() for name in files):
        snapshot_download(repo, revision=rev, allow_patterns=list(files), local_dir=cache)
    tokenizer = sp.SentencePieceProcessor(model_file=str(cache / files[2]))
    decoder = sp.SentencePieceProcessor(model_file=str(cache / "target.spm")) if brazil else tokenizer
    model = ctranslate2.Translator(str(cache), device="cpu", compute_type="int8",
                                   intra_threads=min(8, max(1, (os.cpu_count() or 2)//2)))
    unique = list(dict.fromkeys(texts))
    translated = {}
    for start in range(0, len(unique), 32):
        batch = unique[start:start+32]
        tokens = [[">>pob<<" if brazil else LANGUAGES[source], *tokenizer.encode(t, out_type=str), "</s>"] for t in batch]
        if any(len(row) > 512 for row in tokens):
            raise ValueError("Caption too long to translate without truncation.")
        output = model.translate_batch(tokens, target_prefix=None if brazil else [[LANGUAGES[target]] for _ in batch],
                                       beam_size=3, max_batch_size=1024, batch_type="tokens",
                                       max_decoding_length=512, max_input_length=512)
        for text, result in zip(batch, output, strict=True):
            pieces = result.hypotheses[0]
            if len(pieces) >= 512:
                raise ValueError("Translation exceeded the model window.")
            value = decoder.decode(pieces if brazil else pieces[1:]).strip()
            if not value:
                raise ValueError("Empty translation.")
            translated[text] = value
    if brazil:
        return [" ".join(translated[t] for t in group) for group in groups]
    return [translated[t] for t in texts]


if __name__ == "__main__":
    path, cache = map(Path, sys.argv[1:])
    data = json.loads(path.read_text(encoding="utf8"))
    output = translate(data["texts"], data["source"], data["target"], cache)
    path.write_text(json.dumps(output, ensure_ascii=False), encoding="utf8")
