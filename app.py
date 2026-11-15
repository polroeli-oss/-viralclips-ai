import os, re, subprocess, tempfile, shutil, json
from pathlib import Path
import gradio as gr

APP_DIR = Path(__file__).parent
OUT_DIR = APP_DIR / "outputs"
OUT_DIR.mkdir(exist_ok=True)

def run_cmd(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stdout[-3500:])
    return p.stdout

def get_video(url, work):
    # Only process videos the user owns or has permission to reuse.
    template = str(Path(work) / "source.%(ext)s")
    run_cmd(["yt-dlp", "--no-playlist", "--merge-output-format", "mp4",
             "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
             "-o", template, url])
    candidates = list(Path(work).glob("source.*"))
    candidates = [p for p in candidates if p.suffix.lower() in [".mp4", ".mkv", ".webm", ".mov"]]
    if not candidates:
        raise RuntimeError("No se pudo descargar el video. Prueba con otro enlace compatible.")
    return str(candidates[0])

def transcribe(video, work):
    # faster-whisper runs locally on the server; first run downloads the model.
    from faster_whisper import WhisperModel
    model_size = os.getenv("WHISPER_MODEL", "base")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(video, vad_filter=True, word_timestamps=False)
    rows = []
    for s in segments:
        txt = (s.text or "").strip()
        if txt:
            rows.append({"start": float(s.start), "end": float(s.end), "text": txt})
    if not rows:
        raise RuntimeError("No se detectó voz. Prueba con un video que tenga diálogo.")
    return rows

def score_segment(text):
    t = text.lower()
    score = min(len(t) / 100, 2.5)
    score += sum(1 for x in ["!", "?", "wow", "increíble", "nunca", "secreto",
                              "error", "mejor", "peor", "porque", "cómo", "por qué",
                              "dinero", "verdad", "sorpresa"] if x in t) * 0.35
    score += min(text.count("!") * 0.35 + text.count("?") * 0.2, 1.2)
    return score

def srt_time(seconds):
    ms = int(max(0, seconds) * 1000)
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def make_clips(video, rows, count, duration, work):
    # Create candidate windows around transcript passages, then rank them.
    total = float(run_cmd(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                           "-of", "default=noprint_wrappers=1:nokey=1", video]).strip())
    windows = []
    step = max(8, int(duration * 0.55))
    for row in rows:
        start = max(0, row["start"] - min(4, duration * 0.18))
        start = min(start, max(0, total - duration))
        end = min(total, start + duration)
        if end - start < min(12, duration * 0.6):
            continue
        text = " ".join(r["text"] for r in rows if r["start"] < end and r["end"] > start)
        if len(text.split()) < 8:
            continue
        windows.append((score_segment(text), start, end, text))
    windows.sort(reverse=True, key=lambda x: x[0])

    chosen = []
    for w in windows:
        if all(abs(w[1] - x[1]) > duration * 0.65 for x in chosen):
            chosen.append(w)
        if len(chosen) >= int(count):
            break
    if not chosen:
        # Fallback: evenly spaced clips.
        for i in range(int(count)):
            start = max(0, min(total-duration, i * max(1, (total-duration)/max(1,int(count)))))
            end = min(total, start + duration)
            text = " ".join(r["text"] for r in rows if r["start"] < end and r["end"] > start)
            if end-start > 5:
                chosen.append((0, start, end, text))

    results = []
    for i, (_, start, end, text) in enumerate(chosen, 1):
        clip = str(OUT_DIR / f"viralclip_{i}.mp4")
        srt = Path(work) / f"clip_{i}.srt"
        relevant = [r for r in rows if r["start"] < end and r["end"] > start]
        with open(srt, "w", encoding="utf-8") as f:
            for n, r in enumerate(relevant, 1):
                a = max(0, r["start"] - start)
                b = max(a + 0.25, min(end-start, r["end"] - start))
                f.write(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{r['text']}\n\n")
        # Center-crop to vertical 9:16, add readable subtitles.
        srt_filter = str(srt).replace("\\", "/").replace(":", r"\:")
        vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920, subtitles='{srt_filter}':force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=110'"
        run_cmd(["ffmpeg", "-y", "-ss", str(start), "-i", video, "-t", str(end-start),
                 "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                 "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", clip])
        results.append(clip)
    return results

def process(url, count, duration, progress=gr.Progress()):
    if not url or not re.match(r"^https?://", url.strip()):
        raise gr.Error("Pega un enlace válido que empiece por http:// o https://")
    # Clean previous outputs to keep storage under control.
    for p in OUT_DIR.glob("viralclip_*.mp4"):
        try: p.unlink()
        except: pass
    work = tempfile.mkdtemp(prefix="viralclips_")
    try:
        progress(0.08, desc="Obteniendo el video…")
        video = get_video(url.strip(), work)
        progress(0.35, desc="Analizando voz y momentos…")
        rows = transcribe(video, work)
        progress(0.65, desc="Seleccionando los mejores fragmentos…")
        clips = make_clips(video, rows, count, duration, work)
        progress(1, desc="¡Listo!")
        if not clips:
            raise gr.Error("No se pudieron crear clips con este video.")
        return clips, f"¡Listo! Se crearon {len(clips)} clips. Revísalos y descarga los que te gusten."
    except Exception as e:
        raise gr.Error(f"No se pudo procesar el enlace: {str(e)}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

with gr.Blocks(title="ViralClips AI", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # ✂️ ViralClips AI
    ### Pega un enlace y crea clips verticales automáticamente
    La herramienta analiza el audio, busca fragmentos con contenido hablado, añade subtítulos y los adapta a formato 9:16.
    """)
    url = gr.Textbox(label="Enlace del video", placeholder="Pega aquí el enlace de un video que tengas derecho a utilizar…")
    with gr.Row():
        count = gr.Slider(1, 10, value=5, step=1, label="Cantidad de clips")
        duration = gr.Slider(15, 60, value=35, step=5, label="Duración de cada clip (segundos)")
    btn = gr.Button("🚀 GENERAR CLIPS", variant="primary")
    status = gr.Markdown()
    gallery = gr.Gallery(label="Tus clips", columns=2, height="auto", preview=True)
    btn.click(process, inputs=[url, count, duration], outputs=[gallery, status])
    gr.Markdown("""
    ---
    **Aviso:** Usa enlaces de videos propios o para los que tengas permiso de descarga y reutilización. La selección automática es una primera propuesta: revisa los clips antes de publicarlos. El procesamiento puede tardar y el alojamiento gratuito puede tener límites.
    """)

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", "7860")))
