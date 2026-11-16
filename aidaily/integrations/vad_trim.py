#!/usr/bin/env python3
"""silero-VAD(onnx) 무음 제거 전처리 — 16kHz mono wav → speech-only wav.

MLX Whisper는 VAD가 없어 무음/음악 구간에서 환각(반복루프)을 낸다. 이 스크립트가
발화 구간만 남긴 wav를 만들어 주면 (1) 환각↓ (2) 전사시간↓ 효과를 얻는다.

torch 불필요(onnxruntime + silero_vad.onnx만). silero-vad 공식 get_speech_timestamps
알고리즘을 onnx 런타임용으로 포팅(MIT). 16kHz mono 입력 가정(호출측이 ffmpeg로 보장).

usage: python3 vad_trim.py <in_16k_mono.wav> <out.wav>
       [--threshold 0.5] [--min-silence-ms 100] [--speech-pad-ms 30] [--min-speech-ms 250]
stdout: JSON {ok, kept_ratio, speech_sec, total_sec, n_segments}
비발화만 있거나 실패 시 exit!=0 (호출측은 원본 전체로 폴백).
"""
import argparse, json, os, sys
import numpy as np
import soundfile as sf
import onnxruntime as ort

SR = 16000
WINDOW = 512   # silero v5 @16k 고정 창 크기
CONTEXT = 64   # ⚠️ v5는 각 창 앞에 이전 창 끝 64샘플(context)을 붙여 576으로 입력해야 함
MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silero_vad.onnx")


def _speech_probs(audio, sess):
    """각 512샘플 창의 발화확률 시퀀스.

    silero v5 onnx는 입력이 [context(64) + window(512)] = 576샘플이어야 한다. context를
    빼먹으면 모델이 전 구간을 침묵으로 오판한다(2026-07-02 실측: prob 전부 0 → 발화없음 오탐).
    """
    state = np.zeros((2, 1, 128), dtype=np.float32)
    sr = np.array(SR, dtype=np.int64)
    context = np.zeros(CONTEXT, dtype=np.float32)
    probs = []
    n = len(audio)
    for i in range(0, n, WINDOW):
        chunk = audio[i:i + WINDOW]
        if len(chunk) < WINDOW:
            chunk = np.pad(chunk, (0, WINDOW - len(chunk)))
        x = np.concatenate([context, chunk])          # 64 + 512 = 576
        out, state = sess.run(
            None, {"input": x[np.newaxis, :].astype(np.float32),
                   "state": state, "sr": sr})
        context = chunk[-CONTEXT:]
        probs.append(float(out[0, 0]))
    return probs


def get_speech_timestamps(audio, sess, threshold=0.5, min_speech_ms=250,
                          min_silence_ms=100, speech_pad_ms=30):
    """silero-vad 공식 알고리즘 포팅(max_speech 분할은 생략). [{start,end}] 샘플단위."""
    min_speech = SR * min_speech_ms / 1000
    min_silence = SR * min_silence_ms / 1000
    pad = int(SR * speech_pad_ms / 1000)
    neg_threshold = threshold - 0.15
    n = len(audio)

    probs = _speech_probs(audio, sess)
    triggered, temp_end = False, 0
    speeches, cur = [], {}
    for i, p in enumerate(probs):
        if p >= threshold and temp_end:
            temp_end = 0
        if p >= threshold and not triggered:
            triggered = True
            cur["start"] = WINDOW * i
            continue
        if p < neg_threshold and triggered:
            if not temp_end:
                temp_end = WINDOW * i
            if (WINDOW * i) - temp_end < min_silence:
                continue
            cur["end"] = temp_end
            if cur["end"] - cur["start"] > min_speech:
                speeches.append(cur)
            cur, temp_end, triggered = {}, 0, False
    if cur and (n - cur["start"]) > min_speech:
        cur["end"] = n
        speeches.append(cur)

    # 패딩 적용(구간 경계 앞뒤 여유)
    for i, s in enumerate(speeches):
        if i == 0:
            s["start"] = int(max(0, s["start"] - pad))
        if i != len(speeches) - 1:
            gap = speeches[i + 1]["start"] - s["end"]
            if gap < 2 * pad:
                s["end"] += gap // 2
                speeches[i + 1]["start"] = int(max(0, speeches[i + 1]["start"] - gap // 2))
            else:
                s["end"] = int(min(n, s["end"] + pad))
                speeches[i + 1]["start"] = int(max(0, speeches[i + 1]["start"] - pad))
        else:
            s["end"] = int(min(n, s["end"] + pad))
    return speeches


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--min-silence-ms", type=int, default=100)
    ap.add_argument("--speech-pad-ms", type=int, default=30)
    ap.add_argument("--min-speech-ms", type=int, default=250)
    a = ap.parse_args()

    if not os.path.exists(MODEL):
        sys.stderr.write(f"[vad] 모델 없음: {MODEL}\n"); sys.exit(2)

    audio, sr = sf.read(a.infile, dtype="float32", always_2d=False)
    if audio.ndim > 1:               # 스테레오 방어(호출측이 mono 보장하지만)
        audio = audio.mean(axis=1)
    if sr != SR:
        sys.stderr.write(f"[vad] 16kHz 아님({sr}) — 호출측 ffmpeg 확인 필요\n"); sys.exit(3)
    total = len(audio)

    sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    segs = get_speech_timestamps(
        audio, sess, threshold=a.threshold, min_speech_ms=a.min_speech_ms,
        min_silence_ms=a.min_silence_ms, speech_pad_ms=a.speech_pad_ms)
    if not segs:
        sys.stderr.write("[vad] 발화 구간 없음 — 원본 폴백\n"); sys.exit(4)

    speech = np.concatenate([audio[s["start"]:s["end"]] for s in segs])
    sf.write(a.outfile, speech, SR, subtype="PCM_16")
    stats = {"ok": True, "n_segments": len(segs),
             "total_sec": round(total / SR, 1),
             "speech_sec": round(len(speech) / SR, 1),
             "kept_ratio": round(len(speech) / total, 3)}
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
