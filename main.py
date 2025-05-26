import whisper
from moviepy.editor import VideoFileClip, concatenate_videoclips
import argparse
import tempfile
import os

MAX_PREVIEW_SECONDS = 300  # 5 minutos

def transcribe_segments_whisper(video_path, model, preview=False):
    if preview:
        with VideoFileClip(video_path) as clip:
            preview_clip = clip.subclip(0, min(MAX_PREVIEW_SECONDS, clip.duration))
            temp_path = tempfile.mktemp(suffix=".mp4")
            preview_clip.write_videofile(temp_path, codec="libx264", audio_codec="aac", verbose=False, logger=None)
            result = model.transcribe(temp_path, language='es', verbose=False)
            os.remove(temp_path)
    else:
        result = model.transcribe(video_path, language='es-MX', verbose=False)
    return result["segments"]

def generate_timeline(segments1, segments2, preview=False):
    timeline = []
    for seg in segments1:
        if preview and seg["end"] > MAX_PREVIEW_SECONDS:
            break
        timeline.append((seg["start"], seg["end"], "speaker1"))

    for seg in segments2:
        if preview and seg["end"] > MAX_PREVIEW_SECONDS:
            break
        timeline.append((seg["start"], seg["end"], "speaker2"))

    timeline.sort(key=lambda x: x[0])
    return timeline

def create_video_from_timeline(timeline, vid1, vid2):
    clips = []
    for start, end, speaker in timeline:
        clip = vid1.subclip(start, end) if speaker == "speaker1" else vid2.subclip(start, end)
        clips.append(clip)
    return concatenate_videoclips(clips)

def main():
    parser = argparse.ArgumentParser(description="Edita tomas entre dos videos según quién habla usando Whisper")
    parser.add_argument("--video1", required=True, help="Ruta al primer video (persona 1)")
    parser.add_argument("--video2", required=True, help="Ruta al segundo video (persona 2)")
    parser.add_argument("--output", default="cambio_tomas_whisper.mp4", help="Nombre del video de salida")
    parser.add_argument("--model", default="base", help="Modelo de Whisper (tiny, base, small, medium, large)")
    parser.add_argument("--preview", action="store_true", help="Modo de vista previa (solo procesa los primeros 5 minutos)")

    args = parser.parse_args()

    model = whisper.load_model(args.model)

    segments1 = transcribe_segments_whisper(args.video1, model, preview=args.preview)
    segments2 = transcribe_segments_whisper(args.video2, model, preview=args.preview)

    print("Generando timeline...")
    timeline = generate_timeline(segments1, segments2, preview=args.preview)

    print("Cargando videos...")
    vid1 = VideoFileClip(args.video1).subclip(0, MAX_PREVIEW_SECONDS if args.preview else None)
    vid2 = VideoFileClip(args.video2).subclip(0, MAX_PREVIEW_SECONDS if args.preview else None)

    print("Creando video final...")
    final = create_video_from_timeline(timeline, vid1, vid2)
    final.write_videofile(args.output)

if __name__ == "__main__":
    main()
