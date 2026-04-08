# AI Video Tool (SRT -> Edge-TTS -> FFmpeg)

Tool tự động:
- Đọc file `.srt`
- Tạo voice bằng `edge-tts`
- Ghép audio voice vào video bằng `ffmpeg`
- Có web admin để upload video và file SRT

## Cài đặt

Yêu cầu:
- Python 3.10+
- ffmpeg đã cài trong hệ thống

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Chạy

```bash
python app.py
```

Mở: `http://localhost:8080`

## Luồng xử lý

1. Upload video + file SRT ở trang admin.
2. App đọc từng subtitle trong SRT.
3. Với mỗi câu subtitle:
   - Generate MP3 bằng Edge-TTS.
   - Fit đúng thời lượng subtitle (pad/trim bằng ffmpeg).
4. Chèn đoạn im lặng theo khoảng trống timeline của SRT.
5. Concat toàn bộ thành một track narration.
6. Ghép narration vào video để tạo file MP4 output.

## Lưu ý

- App hiện tại thay audio gốc video bằng audio narration.
- Có thể đổi voice Edge-TTS tại form (ví dụ `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`).
