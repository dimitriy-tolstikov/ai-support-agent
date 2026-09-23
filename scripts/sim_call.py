"""демонстрирует: sim-звонок без SIP — подаёт WAV в RTP-обработчик вместо реального транка,
принимает ответное аудио и проверяет barge-in.

Запуск внутри compose-сети:
    docker compose --profile sim run --rm sim python /scripts/sim_call.py --wav /scripts/audio/utt1.wav
    # сценарий barge-in:
    docker compose --profile sim run --rm sim python /scripts/sim_call.py --wav /scripts/audio/utt1.wav --barge /scripts/audio/utt2.wav
"""
import argparse
import audioop
import socket
import struct
import time
import wave

FRAME = 160  # ulaw байт = 20 мс


def wav_to_ulaw(path: str) -> bytes:
    with wave.open(path, "rb") as w:
        pcm = w.readframes(w.getnframes())
        rate, width, ch = w.getframerate(), w.getsampwidth(), w.getnchannels()
    if ch == 2:
        pcm = audioop.tomono(pcm, width, 0.5, 0.5)
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
    if rate != 8000:
        pcm = audioop.ratecv(pcm, 2, 1, rate, 8000, None)[0]
    return audioop.lin2ulaw(pcm, 2)


def send_rtp(sock: socket.socket, target, ulaw: bytes, seq_start: int = 0,
             tail_silence_s: float = 1.5) -> int:
    # tail_silence: после конца WAV продолжаем слать «тишину», как делал бы RTP-источник —
    # иначе VAD на той стороне не увидит паузу и не зафиксирует конец реплики
    payload = ulaw + b"\xff" * int(FRAME * tail_silence_s / 0.02)
    seq, ts = seq_start, 0
    for i in range(0, len(payload) - FRAME + 1, FRAME):
        header = struct.pack("!BBHII", 0x80, 0, seq & 0xFFFF, ts, 0x777)
        sock.sendto(header + payload[i : i + FRAME], target)
        seq += 1
        ts += FRAME
        time.sleep(0.02)
    return seq


def collect(sock: socket.socket, idle_s: float = 1.5, max_s: float = 30) -> bytes:
    """Собирает RTP-ответ, пока не наступит тишина idle_s."""
    sock.settimeout(0.5)
    out = bytearray()
    last = time.monotonic()
    start = last
    while time.monotonic() - last < idle_s and time.monotonic() - start < max_s:
        try:
            data, _ = sock.recvfrom(2048)
            out += data[12:]
            last = time.monotonic()
        except TimeoutError:
            pass
    return bytes(out)


def save_wav(path: str, ulaw: bytes) -> None:
    pcm = audioop.ulaw2lin(ulaw, 2)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(pcm)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--barge", help="второй WAV — перебивание во время ответа")
    ap.add_argument("--target", default="telephony:10000")
    ap.add_argument("--out", default="/tmp/reply.wav")
    args = ap.parse_args()
    host, port = args.target.rsplit(":", 1)
    target = (socket.gethostbyname(host), int(port))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))

    print(f"-> отправляю {args.wav}")
    seq = send_rtp(sock, target, wav_to_ulaw(args.wav))

    if not args.barge:
        reply = collect(sock)
        print(f"<- ответ: {len(reply) / FRAME * 0.02:.1f} с аудио -> {args.out}")
        save_wav(args.out, reply)
        return

    # barge-in: ждём начала ответа, затем перебиваем второй репликой
    sock.settimeout(15)
    data, _ = sock.recvfrom(2048)
    print("<- ответ начался, через 0.25с перебиваю…")
    time.sleep(0.25)
    t0 = time.monotonic()
    send_rtp(sock, target, wav_to_ulaw(args.barge), seq_start=seq)
    reply = data[12:] + collect(sock, idle_s=2.0, max_s=40)
    print(f"<- аудио после barge-in: {len(reply) / FRAME * 0.02:.1f} с -> {args.out}")
    print("(в логах telephony должны быть строки 'barge-in' и 'playback cancelled')")
    save_wav(args.out, reply)


if __name__ == "__main__":
    main()
