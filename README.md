# Mesh Email Gateway

A Python gateway that forwards emails from a PC mailbox to a Meshtastic LoRa mesh network via USB or Bluetooth.

---

## Features

- Connects via USB or BLE (Bluetooth Low Energy)
- Fetches emails from any IMAP-compatible server
- Sends emails in packets over mesh with unique message IDs
- Automatically reconnects on failure
- Avoids duplicate messages using persistent UID tracking

---

## Setup

1. **Clone the repository:**

```bash
git clone https://github.com/YourUsername/mesh-email-gateway.git
cd mesh-email-gateway
```

2. **Setup your credentials:**
In the folder with the script you should have a `.env` file. The file structure is as follows:

```
EMAIL=your_email@example.com
PASSWORD=your_email_password
IMAP_SERVER=imap.example.com
IMAP_PORT=993
IMAP_TLS=True
DEST_NODE=<Node ID of the receiving Meshtastic node>
BLE_ADDRESS=<Optional BLE MAC address if using Bluetooth>
```

3. **Usage**
You can either run the 'mail_gateway.py' if you have python installed or just use the compiled file in 'dist/mail_gateway'
