# 🎬 ClipKaro — AI Viral Clip Extractor

Upload any video → AI finds viral moments → Get Shorts-ready clips with subtitles!

## ✨ Features
- 🤖 AI viral moment detection with virality scores (1-100)
- 📝 Auto subtitles (Hindi + English) burned into clips
- 📱 9:16 vertical, 1:1 square, 16:9 horizontal exports
- 🎯 Customizable: 3-10 clips, 15/30/60 second lengths
- 🆓 100% FREE — No watermark, no expiry
- ✨ Fancy glowing dark UI

## 🚀 Free Deployment on Render

1. Push this folder to GitHub
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo
4. Settings:
   - **Build Command:** `pip install -r requirements.txt && apt-get update && apt-get install -y ffmpeg`
   - **Start Command:** `cd backend && gunicorn app:app --bind 0.0.0.0:$PORT --timeout 600 --workers 1`
   - **Plan:** Free
5. Add `nixpacks.toml` for ffmpeg (see below)
6. Deploy! 🎉

### nixpacks.toml (for ffmpeg on Render)
```toml
[phases.setup]
nixPkgs = ["ffmpeg"]
```

## 💻 Local Run
```bash
pip install -r requirements.txt
# Install ffmpeg: apt install ffmpeg (Linux) or brew install ffmpeg (Mac)
# Install whisper: pip install openai-whisper
cd backend
python app.py
# Open http://localhost:5000
```

## 📝 Notes
- Max video: 500MB, 30 minutes
- First load after idle: ~30s (Render free tier cold start)
- One job at a time recommended on free tier
- YouTube URL mode: coming in v2 (requires self-hosted setup due to YT IP blocking)

Made with 💜 by ClipKaro
