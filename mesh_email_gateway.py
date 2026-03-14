import os
import time
import random
import imaplib
import smtplib
import re
import subprocess
from dotenv import load_dotenv
import pyzmail
import meshtastic.serial_interface
from meshtastic.ble_interface import BLEInterface
from email.mime.text import MIMEText
from pubsub import pub


# -------------------------
# Global state
# -------------------------

iface = None
settings = {}
recent_packets = set()


# -------------------------
# Environment management
# -------------------------

def ensure_env():

    if os.path.exists(".env"):
        return

    print("No .env file found. Initial setup.\n")

    email = input("Email address: ")
    password = input("Email password: ")
    imap_server = input("IMAP server: ")
    imap_port = input("IMAP port (usually 993): ")
    smtp_server = input("SMTP server: ")
    smtp_port = input("SMTP port (usually 587): ")
    dest = input("Destination mesh node ID (!xxxx): ")
    ble = input("Bluetooth node name (BLE_NAME): ")
    allowed = input("Allowed sending node (!xxxx): ")

    with open(".env","w") as f:
        f.write(f"EMAIL={email}\n")
        f.write(f"PASSWORD={password}\n")
        f.write(f"IMAP_SERVER={imap_server}\n")
        f.write(f"IMAP_PORT={imap_port}\n")
        f.write(f"SMTP_SERVER={smtp_server}\n")
        f.write(f"SMTP_PORT={smtp_port}\n")
        f.write(f"DEST_NODE={dest}\n")
        f.write(f"BLE_NAME={ble}\n")
        f.write(f"ALLOWED_NODE={allowed}\n")

    print(".env created\n")


def load_settings():

    load_dotenv(override=True)

    return {
        "EMAIL": os.getenv("EMAIL"),
        "PASSWORD": os.getenv("PASSWORD"),
        "IMAP_SERVER": os.getenv("IMAP_SERVER"),
        "IMAP_PORT": int(os.getenv("IMAP_PORT",143)),
        "SMTP_SERVER": os.getenv("SMTP_SERVER"),
        "SMTP_PORT": int(os.getenv("SMTP_PORT",587)),
        "DEST_NODE": os.getenv("DEST_NODE"),
        "BLE_NAME": os.getenv("BLE_NAME"),
        "ALLOWED_NODE": os.getenv("ALLOWED_NODE")
    }

def edit_settings():

    print("\nModify settings (leave empty to keep current value):\n")

    keys = [
        "EMAIL","PASSWORD","IMAP_SERVER","IMAP_PORT",
        "SMTP_SERVER","SMTP_PORT","DEST_NODE","BLE_NAME","ALLOWED_NODE"
    ]

    for key in keys:
        if key in settings:
            old = settings[key]
        else:
            old = ""

        new = input(f"{key} [{old}]: ").strip()

        settings[key] = new or old

    settings["IMAP_PORT"] = int(settings["IMAP_PORT"])
    settings["SMTP_PORT"] = int(settings["SMTP_PORT"])

    with open(".env","w") as f:
        for k,v in settings.items():
            f.write(f"{k}={v}\n")

    print("Settings updated.\n")


# -------------------------
# Utilities
# -------------------------

def generate_msg_id():
    return f"{random.randint(0,0xFFFF):04X}"


def split_message(text,size):

    msg_id = generate_msg_id()
    total = (len(text)+size-1)//size

    return [
        f"MAIL {msg_id} {i//size+1}/{total}\n{text[i:i+size]}"
        for i in range(0,len(text),size)
    ]


# -------------------------
# Mesh connection
# -------------------------

def find_ble_address():

    print("Scanning for BLE nodes...")

    try:
        result = subprocess.run(
            ["meshtastic","--ble-scan"],
            capture_output=True,
            text=True,
            timeout=15
        )
    except Exception as e:
        print("BLE scan failed:", e)
        return None

    for line in result.stdout.splitlines():

        match = re.search(r"name='([^']+)'.*address='([^']+)'", line)

        if not match:
            continue

        name,address = match.groups()

        if name == settings["BLE_NAME"]:
            print("Found node:",name,address)
            return address

    print("Node not found")
    return None


def connect_mesh(mode):

    if mode=="usb":
        print("Connecting USB")
        return meshtastic.serial_interface.SerialInterface()

    if mode=="ble":

        addr = find_ble_address()

        if not addr:
            return None

        print("Connecting BLE")
        return BLEInterface(address=addr)

def reconnect_mesh(mode):

    global iface

    print("Reconnecting mesh interface...")

    try:
        if iface:
            iface.close()
    except Exception as e:
        print("Close error:", e)
        print("Trying to reconnect")

    time.sleep(2)

    iface = connect_mesh(mode)

    if iface:
        pub.subscribe(on_receive, "meshtastic.receive")
        print("Mesh reconnected")
        return True
    else:
        print("Reconnect failed")
        return False

# -------------------------
# Email functions
# -------------------------

def connect_mail():

    if settings["IMAP_PORT"] == 993:
        mail = imaplib.IMAP4_SSL(settings["IMAP_SERVER"],settings["IMAP_PORT"],timeout=10)
    else:
        mail = imaplib.IMAP4(settings["IMAP_SERVER"],settings["IMAP_PORT"],timeout=10)
        mail.starttls()

    mail.login(settings["EMAIL"],settings["PASSWORD"])
    mail.select("INBOX")

    return mail


def send_email(to_addr,subject,body):

    msg = MIMEText(body)

    msg["From"] = settings["EMAIL"]
    msg["To"] = to_addr
    msg["Subject"] = subject

    if settings["SMTP_PORT"] == 465:
        server = smtplib.SMTP_SSL(settings["SMTP_SERVER"],settings["SMTP_PORT"],timeout=10)
    else:
        server = smtplib.SMTP(settings["SMTP_SERVER"],settings["SMTP_PORT"],timeout=10)
        server.ehlo()
        server.starttls()

    server.login(settings["EMAIL"],settings["PASSWORD"])
    server.send_message(msg)
    server.quit()

    print("Email sent to",to_addr)


# -------------------------
# Mail checking
# -------------------------

def check_mail(max_packet=170):

    if not iface:
        print("Mesh not connected")
        return

    mail = connect_mail()

    status,data = mail.search(None,"UNSEEN")

    if status != "OK":
        print("Search failed")
        mail.logout()
        return

    for uid_bytes in data[0].split():

        uid = uid_bytes.decode()

        status,msg_data = mail.fetch(uid,"(RFC822)")

        if status != "OK":
            continue

        msg = pyzmail.PyzMessage.factory(msg_data[0][1])

        sender = msg.get_addresses("from")[0][1]
        subject = msg.get_subject()

        if msg.text_part:
            body = msg.text_part.get_payload().decode(msg.text_part.charset or "utf-8",errors="replace")

        elif msg.html_part:
            html = msg.html_part.get_payload().decode(msg.html_part.charset or "utf-8",errors="replace")
            body = re.sub('<[^<]+?>','',html)

        else:
            body = "(No readable body)"

        text = f"From:{sender}\nSub:{subject}\n{body}"

        packets = split_message(text,max_packet)

        for p in packets:

            print("Sending mesh packet")

            iface.sendText(
                p,
                destinationId=settings["DEST_NODE"]
            )

            time.sleep(3)

        mail.store(uid,'+FLAGS','\\Seen')

    mail.logout()


# -------------------------
# Mesh message handler
# -------------------------

def parse_mesh_email(text):

    if not text.startswith("EML|"):
        return None

    parts = text.split("|",3)

    if len(parts) < 4:
        return None

    return parts[1].strip(),parts[2].strip(),parts[3].strip()


def on_receive(packet, interface=None):

    try:

        if "decoded" not in packet:
            return

        sender = str(packet.get("from"))

        if sender != str(int(settings["ALLOWED_NODE"][1:],16)):
            return

        packet_id = packet.get("id")

        if packet_id in recent_packets:
            print("Duplicate packet ignored")
            return
        
        recent_packets.add(packet_id)

        if len(recent_packets)>30:
            recent_packets.clear()


        decoded = packet["decoded"]

        if "text" not in decoded:
            return

        text = decoded["text"]

        parsed = parse_mesh_email(text)

        if not parsed:
            return

        to_addr,subject,body = parsed

        print("Email request received")

        send_email(to_addr,subject,body)

        confirm = f"EMAIL SENT: {to_addr}"

        iface.sendText(
                confirm,
                destinationId=settings["DEST_NODE"]
        )

    except Exception as e:

        print("Email send failed:",e)

        fail = f"EMAIL FAILED"
        
        try:

            iface.sendText(
                    fail,
                    destinationId=settings["DEST_NODE"]
                )
        except:

            print("Failed to send fail message to mesh")


# -------------------------
# Main loop
# -------------------------

def gateway_loop(mode):

    global iface

    while True:

        if not iface:
            reconnect_mesh(mode)
            time.sleep(3)
            continue

        try:
            check_mail()

        except Exception as e:

            print("Gateway error:", e)

            reconnect_mesh(mode)

        time.sleep(30)

# -------------------------
# Startup / Main
# -------------------------

def main():

    global settings
    global iface

    ensure_env()
    settings = load_settings()

    print("Do you want to modify settings? (y/N)")
    if input("> ").strip().lower() == "y":
        edit_settings()
        settings = load_settings()

    print("Mesh Email Gateway Starting...\n")

    # Connection selection
    print("\nSelect connection type:")
    print("1) USB")
    print("2) Bluetooth")
    choice = input("> ").strip()
    mode = "usb" if choice == "1" else "ble"

    # Initial mesh connection
    iface = connect_mesh(mode)

    if not iface:
        print("Mesh connection failed")
        return

    pub.subscribe(on_receive, "meshtastic.receive")

    print("Gateway running")

    gateway_loop(mode)

if __name__ == "__main__":
    main()
