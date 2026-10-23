import os, uuid, subprocess
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

BASE = Path("/tmp/chatpattoytv")
BASE.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="Chatpattoytv Video Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise HTTPException(500, p.stderr[-1500:])
    return p.stdout

@app.get("/")
def home():
    return {"status": "running", "service": "Chatpattoytv Video Backend"}

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    job = uuid.uuid4().hex[:12]
    folder = BASE / job
    folder.mkdir()
    saved = []
    for i, f in enumerate(files):
        ext = Path(f.filename or "clip.mp4").suffix.lower()
        if ext not in [".mp4", ".mov", ".m4v", ".webm", ".mkv"]:
            continue
        path = folder / f"{i:03d}{ext}"
        with path.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                out.write(chunk)
        saved.append(path.name)
    if not saved:
        raise HTTPException(400, "No supported video files uploaded")
    (folder / "clips.txt").write_text("\n".join(saved))
    return {"job_id": job, "clips": saved, "message": "Upload complete"}

@app.post("/analyze/{job}")
def analyze(job: str):
    folder = BASE / job
    if not folder.is_dir():
        raise HTTPException(404, "Job not found")
    result = []
    for name in (folder / "clips.txt").read_text().splitlines():
        path = folder / name
        duration = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)]).strip()
        scenes = run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", "select='gt(scene,0.30)',showinfo", "-an", "-f", "null", "-"])
        result.append({"file": name, "duration_seconds": round(float(duration or 0), 2), "scene_changes_detected": scenes.count("pts_time:")})
    return {"job_id": job, "clips": result, "note": "Scene-change detection only; this is not semantic AI editing."}

@app.post("/render/{job}")
def render(job: str):
    folder = BASE / job
    if not folder.is_dir():
        raise HTTPException(404, "Job not found")
    clips = (folder / "clips.txt").read_text().splitlines()
    normalized = []
    for i, name in enumerate(clips):
        out = folder / f"normalized_{i:03d}.mp4"
        run(["ffmpeg", "-y", "-i", str(folder/name), "-vf", "scale=-2:720,fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-af", "aresample=async=1", "-movflags", "+faststart", str(out)])
        normalized.append(out)
    listing = folder / "concat.txt"
    listing.write_text("".join("file '" + str(p) + "'\n" for p in normalized))
    output = folder / "final.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(output)])
    return {"job_id": job, "preview_url": f"/preview/{job}", "download_url": f"/download/{job}"}

@app.get("/preview/{job}")
def preview(job: str):
    p = BASE / job / "final.mp4"
    if not p.exists():
        raise HTTPException(404, "Render video first")
    return FileResponse(p, media_type="video/mp4")

@app.get("/download/{job}")
def download(job: str):
    p = BASE / job / "final.mp4"
    if not p.exists():
        raise HTTPException(404, "Render video first")
    return FileResponse(p, media_type="video/mp4", filename="chatpattoytv-final.mp4")
