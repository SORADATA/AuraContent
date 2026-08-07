def format_srt_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def chunk_words_for_subtitles(words, max_words=3):
    chunks = []
    current = []
    for word in words:
        current.append(word)
        if len(current) >= max_words:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def generate_grouped_srt(text, duration, output_path, max_words_per_caption=3, min_caption_dur=0.45):
    words = text.split()
    if not words:
        return None

    chunks = chunk_words_for_subtitles(words, max_words=max_words_per_caption)
    total_words = len(words)
    cursor = 0.0
    lines = []

    for idx, chunk in enumerate(chunks, start=1):
        proportion = len(chunk) / total_words
        seg_duration = max(duration * proportion, min_caption_dur)

        start = cursor
        end = min(start + seg_duration, duration)
        cursor = end

        caption_text = " ".join(chunk)
        lines.append(f"{idx}\n{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n{caption_text}\n")

    if lines:
        last_block = lines[-1].split("\n")
        if len(last_block) >= 3:
            start_line = last_block[1].split(" --> ")[0]
            lines[-1] = f"{len(lines)}\n{start_line} --> {format_srt_timestamp(duration)}\n{last_block[2]}\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path