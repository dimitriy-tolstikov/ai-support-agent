"""демонстрирует: эмулятор CRM-отправителя webhook'ов (HMAC-подпись, повторная доставка event_id).

Примеры:
    python scripts/webhook_sender.py                      # одно событие order.updated
    python scripts/webhook_sender.py --repeat             # то же событие дважды -> вторая отправка "duplicate"
    python scripts/webhook_sender.py --bad-sign           # невалидная подпись -> 401
    python scripts/webhook_sender.py --type unknown.event # неизвестный тип -> задача упадёт в DLQ
"""
import argparse
import hashlib
import hmac
import json
import os
import urllib.request
import uuid

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
SECRET = os.environ.get("WEBHOOK_SECRET", "dev_webhook_secret")


def send(event: dict, secret: str) -> tuple[int, str]:
    body = json.dumps(event).encode()
    sign = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"{BASE_URL}/api/v1/webhooks/crm", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "X-Signature": sign})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", action="store_true", help="отправить то же событие дважды")
    ap.add_argument("--bad-sign", action="store_true", help="подписать неверным секретом")
    ap.add_argument("--type", default="order.updated")
    ap.add_argument("--order", default="1001")
    ap.add_argument("--status", default="delivered")
    args = ap.parse_args()

    event = {
        "event_id": str(uuid.uuid4()),
        "type": args.type,
        "user_id": "00000000-0000-0000-0000-000000000001",
        "data": {"order_id": args.order, "status": args.status},
    }
    secret = "wrong_secret" if args.bad_sign else SECRET

    attempts = 2 if args.repeat else 1
    for i in range(attempts):
        code, resp = send(event, secret)
        print(f"[{i + 1}/{attempts}] event_id={event['event_id']} -> HTTP {code} {resp}")


if __name__ == "__main__":
    main()
