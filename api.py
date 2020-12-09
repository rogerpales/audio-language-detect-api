from flask import Flask, render_template, request, jsonify, Response
from werkzeug.utils import secure_filename
import uuid
import time
import threading
from datetime import datetime, timedelta
from worker import Worker, audio_requests, mutex
import os

# background processing

temp_dir = "tmp"

if not os.path.isdir(temp_dir):
    os.mkdir(temp_dir)


def work():
    while True:
        Worker.process()
        time.sleep(10)


thread = threading.Thread(target=work, args=())
thread.start()


# api

app = Flask(__name__)


@app.route('/api/audio/upload', methods=['GET', 'POST'])
def post_audio():
    cand_param = request.args.get('candidates', default='en-US,fr-FR,de-DE,es-ES,ca-ES,it-IT')
    candidates = cand_param.split(',')
    max_samples = request.args.get('max_samples', default=20, type=int)

    audio_id = str(uuid.uuid4())
    file_path = ''

    if request.method == 'POST':
        directory = f"{temp_dir}/{audio_id}"
        if not os.path.isdir(directory):
            os.mkdir(directory)

        f = request.files['file']
        file_path = f"{directory}/{secure_filename(f.filename)}"
        f.save(file_path)

    mutex.acquire()

    audio_requests[audio_id] = {
        "file_path": file_path,
        "status": "processing",
        "id": audio_id,
        "errors": [],
        "language": "und",
        "candidates": candidates,
        "expires_at": datetime.now() + timedelta(minutes=30),
        "max_samples": max_samples
    }

    mutex.release()

    resp = jsonify(audio_requests[audio_id])
    return resp


@app.route('/api/audio/<audio_id>', methods=['GET'])
def get_audio(audio_id):
    if audio_id in audio_requests.keys():
        return jsonify(audio_requests[audio_id])
    else:
        return Response('{"error":"not found"}', status=404, mimetype='application/json')


if __name__ == '__main__':
    app.run(debug=True)