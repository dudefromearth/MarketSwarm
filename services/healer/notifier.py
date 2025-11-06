# services/healer/notifier.py
from __future__ import annotations
import json, logging, os, time, ssl, smtplib
from email.message import EmailMessage
from urllib import request, error as urlerror
from typing import Dict, Any

class Notifier:
    """
    Very basic notifier:
      - log (always)
      - webhook (Slack/Discord compatible) if WEBHOOK_URL is set
      - optional SMTP email if SMTP_* vars provided
    Throttles repeated identical alerts for the same svc/type within RATE_LIMIT_SEC.
    """
    def __init__(self, log: logging.Logger, alert_channel: str):
        self.log = log
        self.alert_channel = alert_channel

        # sinks
        self.webhook_url = os.getenv("WEBHOOK_URL", "").strip()          # Slack/Discord
        self.webhook_timeout = float(os.getenv("WEBHOOK_TIMEOUT_SEC", "4"))
        self.smtp_host  = os.getenv("SMTP_HOST", "").strip()
        self.smtp_port  = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user  = os.getenv("SMTP_USER", "").strip()
        self.smtp_pass  = os.getenv("SMTP_PASS", "").strip()
        self.smtp_from  = os.getenv("SMTP_FROM", "").strip()
        self.smtp_to    = [s.strip() for s in os.getenv("SMTP_TO", "").split(",") if s.strip()]

        # throttle
        self.rate_limit = float(os.getenv("RATE_LIMIT_SEC", "60"))
        self._last: Dict[str, float] = {}  # key = f"{type}:{svc}"

    def _should_send(self, ev: Dict[str, Any]) -> bool:
        key = f"{ev.get('type')}:{ev.get('svc')}"
        now = time.time()
        last = self._last.get(key, 0.0)
        if (now - last) >= self.rate_limit:
            self._last[key] = now
            return True
        return False

    def _fmt_text(self, ev: Dict[str, Any]) -> str:
        t = ev.get("type", "")
        svc = ev.get("svc", "?")
        if t == "heartbeat_miss":
            late = ev.get("late_sec", "?")
            timeout = ev.get("timeout_sec", "?")
            return f"🚨 {svc} missed heartbeat: late {late}s (> {timeout}s)  → {self.alert_channel}"
        elif t == "heartbeat_ok":
            age = ev.get("age_sec", "?")
            return f"✅ {svc} heartbeat recovered (age {age}s)"
        else:
            return f"ℹ️ {svc} event: {json.dumps(ev)}"

    def _send_webhook(self, text: str, ev: Dict[str, Any]) -> None:
        if not self.webhook_url:
            return
        payload = {"text": text}
        data = json.dumps(payload).encode()
        req = request.Request(self.webhook_url, data=data, headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=self.webhook_timeout) as r:
                if r.status >= 300:
                    self.log.warning("notify webhook non-2xx: %s", r.status)
        except urlerror.URLError as e:
            self.log.warning("notify webhook error: %s", e)

    def _send_email(self, subject: str, text: str) -> None:
        if not (self.smtp_host and self.smtp_from and self.smtp_to):
            return
        msg = EmailMessage()
        msg["From"] = self.smtp_from
        msg["To"]   = ", ".join(self.smtp_to)
        msg["Subject"] = subject
        msg.set_content(text)

        ctx = ssl.create_default_context()
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=6) as s:
                s.starttls(context=ctx)
                if self.smtp_user:
                    s.login(self.smtp_user, self.smtp_pass)
                s.send_message(msg)
        except Exception as e:
            self.log.warning("notify email error: %s", e)

    def notify(self, ev: Dict[str, Any]) -> None:
        """
        Send notifications for a given event.
        Throttles repeating alerts; recovery events are not throttled.
        """
        t = ev.get("type")
        text = self._fmt_text(ev)

        # Always log
        if t == "heartbeat_miss":
            self.log.warning(text)
        else:
            self.log.info(text)

        # Throttle only on 'miss' (spam control)
        if t == "heartbeat_miss" and not self._should_send(ev):
            return

        # Webhook (Slack/Discord)
        self._send_webhook(text, ev)

        # Email (optional)
        subj = f"[healer] {text}"
        self._send_email(subj, text)