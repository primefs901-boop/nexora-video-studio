from flask import Flask, render_template, request, jsonify, send_file
import os
import threading
import uuid
import yt_dlp

app = Flask(__name__)

DOWNLOAD_DIR = os.path.expanduser("~/storage/downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

jobs = {}
lock = threading.Lock()


def download_video(job_id, url):
    try:
        jobs[job_id] = {
            "status": "downloading",
            "progress": 0,
            "speed": "Starting...",
            "eta": "--",
            "file": None,
            "error": None
        }

        def progress_hook(data):
            if data["status"] == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                downloaded = data.get("downloaded_bytes", 0)
                percent = round(downloaded * 100 / total, 1) if total else 0

                jobs[job_id].update({
                    "progress": percent,
                    "speed": data.get("_speed_str", "Calculating..."),
                    "eta": data.get("_eta_str", "--")
                })

            elif data["status"] == "finished":
                jobs[job_id]["progress"] = 100

        options = {
            "format": "best[ext=mp4]/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, job_id + ".%(ext)s"),
            "noplaylist": True,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        matches = [
            os.path.join(DOWNLOAD_DIR, name)
            for name in os.listdir(DOWNLOAD_DIR)
            if name.startswith(job_id + ".")
        ]

        if not matches:
            raise Exception("Download file nahi mili.")

        jobs[job_id].update({
            "status": "completed",
            "progress": 100,
            "file": matches[0]
        })

    except Exception as error:
        jobs[job_id] = {
            **jobs.get(job_id, {}),
            "status": "error",
            "error": str(error)
        }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/download", methods=["POST"])
def start_download():
    data = request.get_json(silent=True) or request.form
    url = (data.get("url") or "").strip()

    if not url.startswith(("https://", "http://")):
        return jsonify({"error": "Valid video URL daalo."}), 400

    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "queued", "progress": 0}

    threading.Thread(
        target=download_video,
        args=(job_id, url),
        daemon=True
    ).start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def download_status(job_id):
    job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Download job nahi mila."}), 404

    return jsonify(job)


@app.route("/file/<job_id>")
def get_file(job_id):
    job = jobs.get(job_id, {})
    path = job.get("file")

    if job.get("status") != "completed" or not path or not os.path.isfile(path):
        return jsonify({"error": "File abhi ready nahi hai."}), 404

    return send_file(
        path,
        as_attachment=True,
        download_name=os.path.basename(path)
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
