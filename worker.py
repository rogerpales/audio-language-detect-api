import threading
from datetime import datetime, timedelta
import speech_recognition as sr
import os
from pydub import AudioSegment
from pydub.silence import split_on_silence
import shutil
import time
from pathlib import Path

audio_requests = {}
mutex = threading.Lock()
r = sr.Recognizer()


class Worker(object):

    @staticmethod
    def process():
        mutex.acquire()
        ids = list(audio_requests.keys()).copy()
        mutex.release()

        for a_id in ids:
            if audio_requests[a_id]['expires_at'] < datetime.now():
                print("expired, delete: "+a_id)
                mutex.acquire()
                del audio_requests[a_id]
                mutex.release()
            else:
                if audio_requests[a_id]['status'] == 'processing':
                    start_time = time.time()
                    lan = Worker.get_audio_language(
                        audio_requests[a_id]['file_path'], audio_requests[a_id]['candidates'], audio_requests[a_id]['max_samples'])
                    mutex.acquire()
                    audio_requests[a_id]['status'] = 'completed'
                    audio_requests[a_id]['language'] = lan
                    audio_requests[a_id]['processing_time'] = time.time() - start_time
                    mutex.release()
                    print("processing "+audio_requests[a_id]['file_path']+" took: "+str(audio_requests[a_id]['processing_time']))


    @staticmethod
    def get_audio_language(path, candidates, max_samples):
        scores = {}

        for lan in candidates:
            scores[lan] = list()

        sound = AudioSegment.from_wav(path)
        chunks = split_on_silence(sound, min_silence_len=500, silence_thresh=sound.dBFS-14, keep_silence=500)
        incr = 1
        if len(chunks) > max_samples:
            incr = int(len(chunks)/max_samples)

        audio_dir = str(Path(path).parent)
        chunks_dir = os.path.join(audio_dir, "audio-chunks")

        if not os.path.isdir(chunks_dir):
            os.mkdir(chunks_dir)

        next_sample = 1
        for i, audio_chunk in enumerate(chunks, start=1):
            if i != next_sample:
                continue

            next_sample += incr

            chunk_filename = os.path.join(chunks_dir, f"chunk{i}.wav")
            audio_chunk.export(chunk_filename, format="wav")
            with sr.AudioFile(chunk_filename) as source:
                audio_listened = r.record(source)
                threads = []
                for lan in candidates:
                    t = threading.Thread(target=Worker.recognize_lan, args=(audio_listened, lan, scores))
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join()

        result_lan = 'und'
        best_score = 0
        for lan in candidates:
            if len(scores[lan]) == 0:
                continue
            score = sum(scores[lan]) / len(scores[lan])
            if best_score < score:
                best_score = score
                result_lan = lan
        print(path+" language: "+result_lan)
        print("removing "+audio_dir)
        shutil.rmtree(audio_dir, ignore_errors=True)
        return result_lan

    @staticmethod
    def recognize_lan(audio_listened, lan, scores):
        score = 0.0
        try:
            res = r.recognize_google(audio_listened, language=lan, show_all=True)
            found = False
            if isinstance(res, dict):
                for al in res['alternative']:
                    if found:
                        continue
                    if 'confidence' in al.keys():
                        score = al['confidence']
                        found = True
            if not found:
                score = 0.0
        except sr.UnknownValueError as e:
            score = 0.0
            print("Error:", str(e))

        mutex.acquire()
        scores[lan].append(score)
        mutex.release()
