"""Envío de correo por SMTP (Gmail u otro)."""
import smtplib
import ssl
from email.message import EmailMessage


def send(email_cfg, subject, text_body, html_body=None):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_cfg.get("from_addr", email_cfg["username"])
    msg["To"] = ", ".join(email_cfg["to_addrs"])
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    port = int(email_cfg.get("smtp_port", 465))
    host = email_cfg["smtp_host"]
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as s:
            s.login(email_cfg["username"], email_cfg["app_password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(email_cfg["username"], email_cfg["app_password"])
            s.send_message(msg)
