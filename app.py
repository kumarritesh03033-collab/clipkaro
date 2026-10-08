"""
ClipKaro - YouTube Viral Clip Extractor
Upload video → AI finds viral moments → Get Shorts-ready clips with subtitles
"""
import os
import re
import json
import uuid
import subprocess
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
CLIPS_DIR = BASE_DIR / "clips"
UPLOADS_DIR.mkdir(exist_ok=True)
CLIPS_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_video_info(video_path):
    """Get video duration and dimensions using ffprobe"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(video_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    info = json.loads(result.stdout)
    
    duration = float(info["format"]["duration"])
    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    width = int(video_stream["width"])
    height = int(video_stream["height"])
    
    return {"duration": duration, "width": width, "height": height}

def extract_audio_for_transcription(video_path, job_id):
    """Extract audio as wav for Whisper transcription"""
    audio_path = UPLOADS_DIR / f"{job_id}_audio.wav"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(audio_path)
    ]
    subprocess.run(cmd, capture_output=True, timeout=120)
    return audio_path

def transcribe_with_whisper(audio_path):
    """Transcribe using Whisper (if available) or fallback"""
    try:
        # Try whisper CLI
        cmd = [
            "whisper",
            str(audio_path),
            "--model", "base",
            "--output_format", "json",
            "--output_dir", "/tmp",
            "--language", "hi",  # Try Hindi first, falls back to auto
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        json_path = Path(f"/tmp/{audio_path.stem}.json")
        if json_path.exists():
            with open(json_path) as f:
                data = json.load(f)
            segments = [
                {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
                for s in data.get("segments", [])
                if s["text"].strip()
            ]
            json_path.unlink()
            return segments
    except Exception as e:
        print(f"Whisper error: {e}")
    
    return []

def find_viral_moments(segments, duration, num_clips=5, clip_length=30):
    """
    AI-powered viral moment detection with virality scores.
    Scores based on: hook words, questions, exclamations, emotional words,
    numbers/stats, contrast words. Supports English + Hindi/Hinglish.
    """
    if not segments:
        # Fallback: evenly spaced clips
        moments = []
        for i in range(num_clips):
            start = (duration / num_clips) * i + 5
            if start + clip_length < duration:
                moments.append({
                    "start": round(start, 1),
                    "end": round(start + clip_length, 1),
                    "score": 50,
                    "reason": "Auto-selected segment",
                    "hook_text": ""
                })
        return moments
    
    # Viral indicator words (English + Hindi/Hinglish)
    hook_words = [
        'secret', 'shocking', 'amazing', 'incredible', 'unbelievable', 'viral',
        'million', 'billion', 'free', 'never', 'always', 'best', 'worst',
        'mistake', 'hack', 'trick', 'truth', 'lie', 'exposed', 'breaking',
        'rahasya', 'sach', 'jhoot', 'dhokha', 'kamal', 'hairan', 'sachchai',
    ]
    question_words = ['?', 'kya', 'kyun', 'kaise', 'kab', 'kahan', 
                      'what', 'why', 'how', 'when', 'where', 'kaun']
    emotion_words = [
        'wow', 'omg', 'crazy', 'insane', 'mind-blowing', 'unreal', 'damn',
        'wah', 'kamaal', 'gazab', 'hairan', 'shandar', 'jabardast'
    ]
    
    scored = []
    for seg in segments:
        text_lower = seg["text"].lower()
        score = 30  # base score
        reasons = []
        
        # Hook words (+15 each, max 30)
        hook_hits = sum(1 for w in hook_words if w in text_lower)
        if hook_hits > 0:
            score += min(hook_hits * 15, 30)
            reasons.append("hook words")
        
        # Questions (+20)
        if any(w in text_lower for w in question_words):
            score += 20
            reasons.append("question hook")
        
        # Exclamations (+10)
        if '!' in seg["text"]:
            score += 10
            reasons.append("exclamation")
        
        # Emotion words (+15)
        if any(w in text_lower for w in emotion_words):
            score += 15
            reasons.append("emotional peak")
        
        # Numbers/stats (+10)
        if re.search(r'\d+', seg["text"]):
            score += 10
            reasons.append("has numbers")
        
        # ALL CAPS emphasis (+10)
        if re.search(r'\b[A-Z]{3,}\b', seg["text"]):
            score += 10
            reasons.append("emphasis")
        
        scored.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"],
            "score": min(score, 100),
            "reasons": reasons
        })
    
    # Sort by score, pick top moments with spacing
    scored.sort(key=lambda x: x["score"], reverse=True)
    
    moments = []
    used_ranges = []
    
    for seg in scored:
        if len(moments) >= num_clips:
            break
        
        # Center clip around the viral moment
        mid = (seg["start"] + seg["end"]) / 2
        clip_start = max(0, mid - clip_length / 2)
        clip_end = min(duration, clip_start + clip_length)
        clip_start = max(0, clip_end - clip_length)  # Adjust if hit end
        
        # Check overlap
        overlaps = any(
            not (clip_end < r[0] + 5 or clip_start > r[1] - 5)
            for r in used_ranges
        )
        if overlaps:
            continue
        
        used_ranges.append((clip_start, clip_end))
        moments.append({
            "start": round(clip_start, 1),
            "end": round(clip_end, 1),
            "score": seg["score"],
            "reason": ", ".join(seg["reasons"]) if seg["reasons"] else "high engagement",
            "hook_text": seg["text"][:120]
        })
    
    moments.sort(key=lambda x: x["start"])
    return moments, segments

def create_srt_for_clip(segments, clip_start, clip_end, srt_path):
    """Create SRT subtitle file for a clip"""
    clip_segments = [
        s for s in segments
        if s["end"] > clip_start and s["start"] < clip_end
    ]
    
    with open(srt_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(clip_segments, 1):
            # Adjust timestamps relative to clip start
            start = max(0, seg["start"] - clip_start)
            end = min(clip_end - clip_start, seg["end"] - clip_start)
            
            def fmt(t):
                h = int(t // 3600)
                m = int((t % 3600) // 60)
                s = int(t % 60)
                ms = int((t % 1) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            
            f.write(f"{i}\n")
            f.write(f"{fmt(start)} --> {fmt(end)}\n")
            f.write(f"{seg['text']}\n\n")
    
    return len(clip_segments) > 0

def create_viral_clip(input_path, start, end, output_path, srt_path=None, aspect="9:16"):
    """Create vertical clip with burned-in subtitles and fancy styling"""
    duration = end - start
    
    if aspect == "9:16":
        # Vertical 1080x1920 with blurred background
        vf_base = (
            "split[a][b];"
            "[a]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=20[bg];"
            "[b]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
    elif aspect == "1:1":
        vf_base = (
            "split[a][b];"
            "[a]scale=1080:1080:force_original_aspect_ratio=increase,"
            "crop=1080:1080,boxblur=20[bg];"
            "[b]scale=1080:1080:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
    else:  # 16:9
        vf_base = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    
    # Add subtitles with fancy styling if available
    if srt_path and Path(srt_path).exists():
        # Escape path for ffmpeg
        srt_escaped = str(srt_path).replace(":", "\\:").replace("'", "")
        # Fancy subtitle style: bold, yellow highlight, black outline
        vf = f"{vf_base},subtitles='{srt_escaped}':force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFF&,OutlineColour=&H80000000&,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=80'"
    else:
        vf = vf_base
    
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(input_path),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not output_path.exists():
        raise Exception(f"Clip creation failed")

    return output_path

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_video():
    """Handle video file upload"""
    if 'video' not in request.files:
        return jsonify({"error": "No video file"}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Use MP4, MOV, AVI, MKV, WEBM"}), 400
    
    job_id = str(uuid.uuid4())[:8]
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[1].lower()
    video_path = UPLOADS_DIR / f"{job_id}.{ext}"
    file.save(str(video_path))
    
    # Get video info
    try:
        info = get_video_info(video_path)
    except Exception as e:
        video_path.unlink()
        return jsonify({"error": f"Invalid video file: {e}"}), 400
    
    if info["duration"] < 60:
        video_path.unlink()
        return jsonify({"error": "Video too short (minimum 1 minute)"}), 400
    
    if info["duration"] > 1800:  # 30 min max
        video_path.unlink()
        return jsonify({"error": "Video too long (maximum 30 minutes)"}), 400
    
    return jsonify({
        "job_id": job_id,
        "filename": filename,
        "duration": round(info["duration"], 1),
        "width": info["width"],
        "height": info["height"],
        "video_path": str(video_path)
    })

@app.route('/api/extract', methods=['POST'])
def extract_clips():
    """Extract viral clips from uploaded video"""
    data = request.get_json()
    job_id = data.get('job_id')
    num_clips = min(data.get('num_clips', 5), 10)
    clip_length = data.get('clip_length', 30)  # 15, 30, or 60
    aspect = data.get('aspect', '9:16')
    
    if not job_id:
        return jsonify({"error": "job_id required"}), 400
    
    # Find uploaded video
    video_files = list(UPLOADS_DIR.glob(f"{job_id}.*"))
    # Exclude audio files
    video_files = [f for f in video_files if not f.name.endswith('_audio.wav')]
    if not video_files:
        return jsonify({"error": "Video not found. Upload again."}), 404
    
    video_path = video_files[0]
    
    try:
        info = get_video_info(video_path)
        
        # Step 1: Transcribe
        print(f"[{job_id}] Transcribing...")
        audio_path = extract_audio_for_transcription(video_path, job_id)
        segments = transcribe_with_whisper(audio_path)
        print(f"[{job_id}] Found {len(segments)} transcript segments")
        
        # Cleanup audio
        if audio_path.exists():
            audio_path.unlink()
        
        # Step 2: Find viral moments
        print(f"[{job_id}] Finding viral moments...")
        moments, all_segments = find_viral_moments(segments, info["duration"], num_clips, clip_length)
        
        # Step 3: Create clips with subtitles
        clips = []
        for i, moment in enumerate(moments):
            clip_filename = f"{job_id}_clip{i+1}.mp4"
            clip_path = CLIPS_DIR / clip_filename
            srt_path = CLIPS_DIR / f"{job_id}_clip{i+1}.srt"
            
            # Create SRT for this clip
            has_subs = False
            if all_segments:
                has_subs = create_srt_for_clip(all_segments, moment["start"], moment["end"], srt_path)
            
            print(f"[{job_id}] Creating clip {i+1}: {moment['start']}s-{moment['end']}s (subs: {has_subs})")
            create_viral_clip(
                video_path, moment["start"], moment["end"],
                clip_path, str(srt_path) if has_subs else None, aspect
            )
            
            # Cleanup SRT
            if srt_path.exists():
                srt_path.unlink()
            
            clips.append({
                "id": f"{job_id}_clip{i+1}",
                "filename": clip_filename,
                "start": moment["start"],
                "end": moment["end"],
                "duration": round(moment["end"] - moment["start"], 1),
                "score": moment["score"],
                "reason": moment["reason"],
                "hook_text": moment["hook_text"],
                "has_subtitles": has_subs,
                "download_url": f"/api/download/{clip_filename}"
            })
        
        # Cleanup source video
        if video_path.exists():
            video_path.unlink()
        
        return jsonify({
            "job_id": job_id,
            "duration": round(info["duration"], 1),
            "transcript_segments": len(all_segments),
            "clips_found": len(clips),
            "clips": clips
        })
        
    except Exception as e:
        print(f"[{job_id}] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/<filename>')
def download_clip(filename):
    """Download a generated clip"""
    safe_name = os.path.basename(filename)
    clip_path = CLIPS_DIR / safe_name
    
    if not clip_path.exists():
        return jsonify({"error": "Clip not found"}), 404
    
    return send_file(str(clip_path), as_attachment=True, download_name=safe_name)

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "service": "ClipKaro"})

if __name__ == '__main__':
    print("🎬 ClipKaro starting...")
    print("📁 Uploads:", UPLOADS_DIR)
    print("📁 Clips:", CLIPS_DIR)
    app.run(host='0.0.0.0', port=5000, debug=True)
