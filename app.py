import asyncio
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import edge_tts
import pysrt
from flask import Flask, redirect, render_template, request, send_from_directory, url_for, flash

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
WORK_DIR = BASE_DIR / "work"

for d in [UPLOAD_DIR, OUTPUT_DIR, WORK_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = "change-me-in-production"


def run_cmd(cmd: list[str]):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stderr}")


async def generate_tts(text: str, voice: str, rate: str, output_file: Path):
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(output_file))


def seconds_from_srt_time(t) -> float:
    return t.hours * 3600 + t.minutes * 60 + t.seconds + t.milliseconds / 1000


def create_silence_wav(duration: float, out_file: Path):
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=24000:cl=mono",
        "-t", f"{duration:.3f}",
        "-acodec", "pcm_s16le",
        str(out_file),
    ])


def fit_audio_duration(input_file: Path, duration: float, out_file: Path):
    run_cmd([
        "ffmpeg", "-y",
        "-i", str(input_file),
        "-af", f"apad=pad_dur={duration:.3f},atrim=0:{duration:.3f}",
        "-ar", "24000",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        str(out_file),
    ])


def build_voice_track(srt_file: Path, voice: str, rate: str, work_dir: Path) -> Path:
    subs = pysrt.open(str(srt_file), encoding="utf-8")
    if len(subs) == 0:
        raise ValueError("SRT không có dữ liệu subtitle.")

    segment_files: list[Path] = []
    timeline = 0.0

    for i, sub in enumerate(subs):
        start = seconds_from_srt_time(sub.start)
        end = seconds_from_srt_time(sub.end)
        duration = max(0.05, end - start)

        if start > timeline:
            silence_file = work_dir / f"silence_{i:04d}.wav"
            create_silence_wav(start - timeline, silence_file)
            segment_files.append(silence_file)
            timeline = start

        raw_tts = work_dir / f"tts_{i:04d}.mp3"
        fitted_tts = work_dir / f"seg_{i:04d}.wav"

        text = sub.text.replace("\n", " ").strip()
        if text:
            asyncio.run(generate_tts(text, voice, rate, raw_tts))
            fit_audio_duration(raw_tts, duration, fitted_tts)
        else:
            create_silence_wav(duration, fitted_tts)

        segment_files.append(fitted_tts)
        timeline = end

    concat_file = work_dir / "concat.txt"
    concat_file.write_text("\n".join([f"file '{p.resolve()}'" for p in segment_files]), encoding="utf-8")

    narration_file = work_dir / "narration.wav"
    run_cmd([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(narration_file),
    ])

    return narration_file


def merge_video_and_audio(video_file: Path, audio_file: Path, output_file: Path):
    run_cmd([
        "ffmpeg", "-y",
        "-i", str(video_file),
        "-i", str(audio_file),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_file),
    ])


@app.route("/", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        video = request.files.get("video")
        srt = request.files.get("srt")
        voice = request.form.get("voice", "vi-VN-HoaiMyNeural")
        rate = request.form.get("rate", "+0%")

        if not video or not srt:
            flash("Vui lòng upload đầy đủ video và file SRT.", "error")
            return redirect(url_for("admin"))

        job_id = uuid.uuid4().hex[:10]
        job_work = WORK_DIR / job_id
        job_work.mkdir(parents=True, exist_ok=True)

        video_path = UPLOAD_DIR / f"{job_id}_{video.filename}"
        srt_path = UPLOAD_DIR / f"{job_id}_{srt.filename}"
        output_path = OUTPUT_DIR / f"{job_id}_output.mp4"

        try:
            video.save(video_path)
            srt.save(srt_path)

            narration = build_voice_track(srt_path, voice, rate, job_work)
            merge_video_and_audio(video_path, narration, output_path)

            flash("Xử lý thành công!", "success")
            return redirect(url_for("result", filename=output_path.name))
        except Exception as e:
            flash(f"Lỗi xử lý: {e}", "error")
            return redirect(url_for("admin"))
        finally:
            shutil.rmtree(job_work, ignore_errors=True)

    return render_template("admin.html")


@app.route("/result/<filename>")
def result(filename: str):
    return render_template("result.html", filename=filename)


@app.route("/download/<filename>")
def download(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
