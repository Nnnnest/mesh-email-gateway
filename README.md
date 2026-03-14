# Mesh Email Gateway

Email normally requires internet connectivity. In remote or disaster environments,
however, internet and cellular networks may be unavailable while long-range
radio networks remain operational.

This project implements a gateway that bridges standard email infrastructure
(IMAP/SMTP) with a Meshtastic LoRa mesh network, allowing email messages to be
transmitted across the mesh and delivered once a gateway with internet access
is available.

The gateway can:

- Read incoming emails from an IMAP mailbox and transmit them over the mesh network
- Receive mesh messages and send them as emails via SMTP

It supports both **USB** and **Bluetooth (BLE)** connections to a Meshtastic node.

---

# Architecture

- The gateway periodically checks an email inbox via IMAP.
- New messages are parsed and converted to Meshtastic text messages.
- Messages are fragmented to fit LoRa payload limits.
- The Meshtastic node broadcasts the message into the mesh network.
- Replies from mesh users are received and forwarded via SMTP as normal email.

---

# Features

- Works with any **IMAP/SMTP email provider**
- Connects to a Meshtastic node via **USB or Bluetooth**
- Automatically splits long emails into **mesh-sized packets**
- Sends mesh messages as **standard emails**
- Simple configuration using a `.env` file
- Prevents duplicate packet processing

---

# Requirements

- Python
- A Meshtastic node connected via **USB or Bluetooth**
- An email account with **IMAP and SMTP enabled**

---

# Compiled Version

A compiled executable for macOS can be found in releases.

If you download the precompiled macOS binary, make it executable:

`chmod +x mail_gateway_v1.0_macos`

Then run:

`./mail_gateway_v1.0_macos`

This allows running the gateway without installing Python.

Python is still required if you want to modify or run the source code.

---

# Installation

## 1. Clone the repository

```bash
git clone https://github.com/Nnnnest/mesh-email-gateway.git
cd mesh-email-gateway
```

---

## 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs the required libraries:

- `meshtastic` – communication with the radio
- `pyzmail36` – parsing incoming emails
- `python-dotenv` – loading configuration
- `pypubsub` – event system used by Meshtastic
- `requests` – required dependency for Meshtastic
- `bleak` – Bluetooth support

---

# Configuration

The gateway uses a `.env` file for configuration.

If the file does not exist, the script will **automatically create it and prompt you for the required settings** during the first run.

Example configuration:

```
EMAIL=your_email@example.com
PASSWORD=your_email_password

IMAP_SERVER=imap.example.com
IMAP_PORT=993

SMTP_SERVER=smtp.example.com
SMTP_PORT=587

DEST_NODE=!abcd
BLE_NAME=MyMeshtasticNode
ALLOWED_NODE=!abcd
```

### Configuration options

| Variable | Description |
|--------|--------|
| EMAIL | Email address used by the gateway |
| PASSWORD | Email account password or app password |
| IMAP_SERVER | IMAP server address |
| IMAP_PORT | Usually `993` |
| SMTP_SERVER | SMTP server address |
| SMTP_PORT | Usually `587` or `465` |
| DEST_NODE | Meshtastic node ID that receives email messages |
| BLE_NAME | Bluetooth name of the Meshtastic node |
| ALLOWED_NODE | Only this node is allowed to send email requests |

---

# Running the Gateway

Run the script:

```bash
python mail_gateway.py
```

At startup the program will ask which connection type to use:

```
1) USB
2) Bluetooth
```

Select the connection method for your node.

Once started the gateway will:

1. Check the email inbox periodically
2. Send new emails to the mesh network
3. Listen for mesh messages requesting emails

---

# Sending Emails from the Mesh Network

To send an email from the mesh network, send a message to the gateway node in the following format:

```
EML|recipient_email|subject|body
```

Example:

```
EML|recipient@example.com|Test Subject|Hello from the mesh network.
```

### Format explanation

| Field | Meaning |
|------|------|
| EML | Required prefix indicating an email request |
| recipient_email | Email address to send to |
| subject | Email subject |
| body | Email body text |

Only messages from the configured **`ALLOWED_NODE`** will be processed.

---

# Receiving Emails on the Mesh

When the gateway receives new emails in the configured inbox:

1. The email is converted to plain text
2. The message is split into multiple packets if necessary
3. Packets are transmitted to the configured `DEST_NODE`

Each packet contains a message identifier and sequence number so receiving devices can reconstruct the full message.

---

# Bluetooth Setup

If pairing for the first time:

1. Pair your computer with the Meshtastic node using the **Meshtastic mobile app** or your system Bluetooth settings. This will make sure that device remembers your node. You only have to do this once.
2. Disconnect the mobile app afterward

Only one device can control the node at a time, so the script will fail to connect if another device is still connected.

To check if computer sees your node you can use Meshtastic CLI command `meshtastic --ble-scan`, it will output name and bluetooth address of your node. In the settings you should put you node name, script will automatically match it with the address.
