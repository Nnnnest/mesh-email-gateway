import os
import time
import random
import imaplib
from dotenv import load_dotenv
import pyzmail
import re
import meshtastic.serial_interface
from meshtastic.ble_interface import BLEInterface
import smtplib
from email.mime.text import MIMEText
from pubsub import pub

# Load settings
load_dotenv()

EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")

SERVER = os.getenv("IMAP_SERVER")
PORT = int(os.getenv("IMAP_PORT", 143))

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

DEST = os.getenv("DEST_NODE")
BLE_ADDRESS = os.getenv("BLE_ADDRESS")

ALLOWED_NODE = os.getenv("ALLOWED_NODE")

CHECK_INTERVAL = 30
MAX_PACKET = 170

UID_FILE = "seen_uids.txt"

recent_messages = []
MAX_RECENT = 50

def generate_msg_id():
    return f"{random.randint(0, 0xFFFF):04X}"

def load_seen():
    if not os.path.exists(UID_FILE):
        return set()
    with open(UID_FILE, "r") as f:
        return set(line.strip() for line in f)

def save_seen(uid):
    with open(UID_FILE, "a") as f:
        f.write(uid + "\n")

def choose_connection():
    print("\nSelect connection type:")
    print("1) USB")
    print("2) Bluetooth")

    choice = input("Enter choice (1 or 2): ").strip()

    if choice == "1":
        print("Connecting via USB...")
        return meshtastic.serial_interface.SerialInterface(), "usb"

    elif choice == "2":
        if not BLE_ADDRESS:
            raise Exception("BLE_ADDRESS not set in .env")

        print("Connecting via Bluetooth...")
        return BLEInterface(address=BLE_ADDRESS), "ble"

    else:
        print("Invalid choice, defaulting to USB.")
        return meshtastic.serial_interface.SerialInterface(), "usb"


def connect_mesh(mode):
    if mode == "usb":
        print("Reconnecting USB node...")
        return meshtastic.serial_interface.SerialInterface()

    if mode == "ble":
        print("Reconnecting Bluetooth node...")
        return BLEInterface(address=BLE_ADDRESS)


def connect_mail():
    """Connect to IMAP server."""
    if PORT == 993:
        # SSL
        mail = imaplib.IMAP4_SSL(SERVER, PORT, timeout=10)
    else:
        # non-SSL port use STARTTLS
        mail = imaplib.IMAP4(SERVER, PORT, timeout=10)
        mail.starttls()


    mail.login(EMAIL, PASSWORD)
    mail.select("INBOX")
    return mail

def send_email(to_addr, subject, body):
    msg = MIMEText(body)

    msg["From"] = EMAIL
    msg["To"] = to_addr
    msg["Subject"] = subject

    if SMTP_PORT == 465:
        # SSL
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=10)
    else:
        # non-SSL port use STARTTLS
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.ehlo()
        server.starttls()

    server.login(EMAIL, PASSWORD)
    server.send_message(msg)
    server.quit()

    print("Email sent to", to_addr)

def split_message(text, size):
    msg_id = generate_msg_id()
    total = (len(text) + size - 1) // size

    return [
        f"MAIL {msg_id} {i//size+1}/{total}\n{text[i:i+size]}"
        for i in range(0, len(text), size)
    ]

def check_mail(interface):
    """Check inbox and forward messages to mesh."""
    mail = connect_mail()

    status, data = mail.search(None, "UNSEEN")
    if status != "OK":
        print("Search failed")
        mail.logout()
        return

    for uid_bytes in data[0].split():
        uid = uid_bytes.decode()
        if uid in seen_messages:
            continue

        print("Reading mail...")

        status, msg_data = mail.fetch(uid, "(RFC822)")
        if status != "OK":
            continue

        msg = pyzmail.PyzMessage.factory(msg_data[0][1])

        sender = msg.get_addresses("from")[0][1]
        subject = msg.get_subject()
        body = ""

        if msg.text_part:
            body = msg.text_part.get_payload().decode(msg.text_part.charset or "utf-8")
        elif msg.html_part:
            html = msg.html_part.get_payload().decode(msg.html_part.charset or "utf-8")
            body = re.sub('<[^<]+?>','',html)
        else:
            body = "(No readable message body)"

        text = f"From:{sender}\nSub:{subject}\n{body}"

        packets = split_message(text, MAX_PACKET)

        for p in packets:
            interface.sendText(p, destinationId=DEST)
            time.sleep(3)

        print("Message sent")

        seen_messages.add(uid)
        save_seen(uid)

    mail.logout()

def parse_mesh_email(text):
    if not text.startswith("EML|"):
        return None

    parts = text.split("|", 3)

    if len(parts) < 4:
        return None

    to_addr = parts[1].strip()
    subject = parts[2].strip()
    body = parts[3].strip()

    return to_addr, subject, body

def on_receive(packet, interface):
    if "decoded" not in packet:
        return

    sender = packet.get("from")

    if ALLOWED_NODE and sender != ALLOWED_NODE:
        print("Ignoring message from", sender)
        return

    decoded = packet["decoded"]

    if "text" not in decoded:
        return

    text = decoded["text"]

    # duplicate protection
    msg_key = sender + "|" + text

    if msg_key in recent_messages:
        print("Duplicate message ignored")
        return

    recent_messages.append(msg_key)

    if len(recent_messages) > MAX_RECENT:
        recent_messages.pop(0)

    parsed = parse_mesh_email(text)

    if not parsed:
        return

    to_addr, subject, body = parsed

    print("Email request received from", sender)

    try:

        send_email(to_addr, subject, body)

        interface.sendText(
            "MAIL SENT",
            destinationId=sender
        )

    except Exception as e:

        print("Email send failed:", e)

        interface.sendText(
            "MAIL ERROR",
            destinationId=sender
        )


def gateway_loop(interface, mode):
    """Main loop with reconnection."""
    while True:
        try:
            check_mail(interface)
            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print("Connection error:", e)
            print("Reconnecting in 5 seconds...")
            time.sleep(5)

            try:
                interface.close()
            except:
                pass

            interface = connect_mesh(mode)

            pub.unsubscribe(on_receive, "meshtastic.receive")
            pub.subscribe(on_receive, "meshtastic.receive")


if __name__ == "__main__":
    seen_messages = load_seen()

    print("Mesh email gateway starting...")

    interface, mode = choose_connection()

    print("Mesh email gateway running...")

    pub.subscribe(on_receive, "meshtastic.receive")

    gateway_loop(interface, mode)
