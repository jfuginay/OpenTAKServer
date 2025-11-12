# OpenTAKServer Federation Setup Guide
## Connecting to TAK.gov or Any TAK Server

**Last Updated:** 2025-11-11
**Difficulty:** Intermediate
**Time Required:** 30-60 minutes

---

## What You'll Need

Before starting, gather these items:

- [ ] OpenTAKServer installed and running
- [ ] Access to your TAK server (TAK.gov account or self-hosted)
- [ ] TAK server's CA certificate file (usually called `ca.pem`, `ca.crt`, or `truststore-root.pem`)
- [ ] SSH access to your OpenTAKServer machine
- [ ] Administrator login for OpenTAKServer web UI

---

## Part 1: Get Your TAK Server's Certificate

### For TAK.gov Users

1. **Login to TAK.gov**
   - Go to https://tak.gov
   - Sign in with your credentials

2. **Download Federation Certificate**
   - Navigate to your organization's settings
   - Look for "Federation" or "Certificates" section
   - Download the **CA Certificate** (root certificate)
   - Save it as `takgov-ca.pem` on your computer

3. **Note Your Federation Details**
   - Federation Server Address: `tak.gov` (or specific subdomain)
   - Federation Port: Usually `9000` (v1) or `9001` (v2)
   - Protocol Version: Ask your TAK.gov admin (usually v1)

### For Self-Hosted TAK Server Users

**If you manage the TAK server yourself:**

```bash
# SSH into your TAK server
ssh user@your-tak-server.com

# Find the CA certificate (common locations)
sudo find /opt/tak -name "ca.pem" -o -name "ca.crt"
# OR
sudo ls /opt/tak/certs/files/

# Copy the certificate (adjust path as needed)
cat /opt/tak/certs/files/ca.pem
```

Copy the entire output (including `-----BEGIN CERTIFICATE-----` and `-----END CERTIFICATE-----`)

**If someone else manages it:**
- Ask your TAK server administrator for the **CA certificate**
- They should send you a `.pem` or `.crt` file

---

## Part 2: Generate OpenTAKServer Client Certificate

This certificate proves OpenTAKServer's identity to the TAK server.

### Step 1: SSH into Your OpenTAKServer

```bash
ssh user@your-opentakserver.com
```

### Step 2: Navigate to Certificate Directory

```bash
cd ~/ots/federation
```

If this directory doesn't exist, create it:

```bash
mkdir -p ~/ots/federation/truststore
cd ~/ots/federation
```

### Step 3: Generate Client Certificate

**Replace the values in ALL CAPS with your information:**

```bash
# Generate private key
openssl genrsa -out client.key 2048

# Create certificate signing request (CSR)
openssl req -new -key client.key -out client.csr \
  -subj "/C=US/ST=YOUR_STATE/L=YOUR_CITY/O=YOUR_ORGANIZATION/OU=TAK/CN=opentakserver"

# Generate self-signed certificate (valid for 10 years)
openssl x509 -req -days 3650 \
  -in client.csr \
  -signkey client.key \
  -out client.crt
```

**Example with real values:**
```bash
openssl req -new -key client.key -out client.csr \
  -subj "/C=US/ST=Virginia/L=Arlington/O=MyUnit/OU=TAK/CN=opentakserver"
```

### Step 4: Verify Files Were Created

```bash
ls -la ~/ots/federation/
```

You should see:
- `client.key` (private key)
- `client.crt` (certificate)
- `client.csr` (can delete this)

---

## Part 3: Upload TAK Server CA Certificate

### Option A: Upload via SCP (If you have the file on your computer)

```bash
# From your LOCAL computer (not the server), run:
scp /path/to/takgov-ca.pem user@your-opentakserver.com:~/ots/federation/truststore/tak-ca.crt
```

**Example:**
```bash
scp ~/Downloads/takgov-ca.pem admin@opentakserver.example.com:~/ots/federation/truststore/tak-ca.crt
```

### Option B: Create File via SSH (If you have the certificate text)

```bash
# On your OpenTAKServer via SSH
nano ~/ots/federation/truststore/tak-ca.crt
```

**Paste the certificate (it should look like this):**
```
-----BEGIN CERTIFICATE-----
MIIDvDCCAqSgAwIBAgIUEJfmTS6jeHVrlwSnIyxWldXdBP0wDQYJKoZIhvcNAQEL
... (many lines of random characters) ...
-----END CERTIFICATE-----
```

**Save and exit:**
- Press `CTRL + O` (save)
- Press `ENTER` (confirm)
- Press `CTRL + X` (exit)

---

## Part 4: Add Federation Server to OpenTAKServer

### Method 1: Using Web UI (Recommended)

1. **Open OpenTAKServer Web UI**
   - Go to `http://your-opentakserver:8081`
   - Login as administrator

2. **Navigate to Federation**
   - Click **Admin** in left sidebar
   - Click **Federation**

3. **Add New Federation Server**
   - Click **"Add Federation Server"** button

4. **Fill Out Form**

   **Basic Information:**
   ```
   Name: TAK.gov Production
   Description: TAK.gov federation connection
   Address: tak.gov
   Port: 9000
   ```

   **Connection Settings:**
   ```
   Connection Type: Outbound
   Protocol Version: v1
   Transport Protocol: tcp
   Use TLS: ✓ (checked)
   Verify SSL: ✓ (checked)
   ```

   **Synchronization:**
   ```
   Sync Missions: ✓ (checked)
   Sync CoT: ✓ (checked)
   ```

5. **Add Certificates**

   You need to paste the certificate contents as text.

   **Get TAK Server CA Certificate:**
   ```bash
   # On your server via SSH:
   cat ~/ots/federation/truststore/tak-ca.crt
   ```
   Copy entire output, paste into **"CA Certificate"** field

   **Get Your Client Certificate:**
   ```bash
   cat ~/ots/federation/client.crt
   ```
   Copy entire output, paste into **"Client Certificate"** field

   **Get Your Client Key:**
   ```bash
   cat ~/ots/federation/client.key
   ```
   Copy entire output, paste into **"Client Key"** field

6. **Save**
   - Click **"Create"** or **"Save"** button
   - Check for success message

### Method 2: Using Command Line (If Web UI is broken)

**Create a file with your federation details:**

```bash
nano ~/add-federation.py
```

**Paste this script (UPDATE THE VALUES IN ALL CAPS):**

```python
#!/usr/bin/env python3
import psycopg
from datetime import datetime

# Database connection - UPDATE IF DIFFERENT
conn_string = "postgresql://ots:YOUR_DB_PASSWORD@127.0.0.1/ots"

# Read certificates
with open('/home/YOUR_USERNAME/ots/federation/truststore/tak-ca.crt', 'r') as f:
    tak_ca = f.read()

with open('/home/YOUR_USERNAME/ots/federation/client.crt', 'r') as f:
    client_cert = f.read()

with open('/home/YOUR_USERNAME/ots/federation/client.key', 'r') as f:
    client_key = f.read()

# Federation server details - UPDATE THESE
server_config = {
    'name': 'TAK.gov Production',
    'description': 'TAK.gov federation connection',
    'address': 'tak.gov',  # UPDATE THIS
    'port': 9000,           # UPDATE IF NEEDED (9000 for v1, 9001 for v2)
    'protocol_version': 'v1',  # v1 or v2
}

# Insert federation server
with psycopg.connect(conn_string) as conn:
    with conn.cursor() as cur:
        now = datetime.now()

        # Check if already exists
        cur.execute("SELECT id FROM federation_servers WHERE name = %s", (server_config['name'],))
        if cur.fetchone():
            print(f"ERROR: Server '{server_config['name']}' already exists!")
            exit(1)

        cur.execute("""
            INSERT INTO federation_servers (
                name, description, address, port,
                connection_type, protocol_version, transport_protocol,
                use_tls, verify_ssl, ca_certificate, client_certificate, client_key,
                enabled, status, sync_missions, sync_cot,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s
            ) RETURNING id
        """, (
            server_config['name'],
            server_config['description'],
            server_config['address'],
            server_config['port'],
            'outbound',
            server_config['protocol_version'],
            'tcp',
            True,  # use_tls
            True,  # verify_ssl
            tak_ca,
            client_cert,
            client_key,
            True,  # enabled
            'disconnected',
            True,  # sync_missions
            True,  # sync_cot
            now,
            now
        ))

        server_id = cur.fetchone()[0]
        conn.commit()
        print(f"SUCCESS: Added federation server with ID: {server_id}")
        print(f"Server: {server_config['name']} ({server_config['address']}:{server_config['port']})")
```

**Save and exit:**
- Press `CTRL + O`, `ENTER`, `CTRL + X`

**Run the script:**

```bash
# Make sure you're in the OpenTAKServer virtualenv
cd ~/OpenTAKServer
export PATH="/Users/iesouskurios/Library/Python/3.10/bin:$PATH"  # Adjust for your system
poetry run python ~/add-federation.py
```

If successful, you'll see:
```
SUCCESS: Added federation server with ID: 1
Server: TAK.gov Production (tak.gov:9000)
```

---

## Part 5: Share Your Certificate with TAK Server Admin

Your TAK server administrator needs YOUR OpenTAKServer certificate to trust connections.

### Step 1: Get Your Certificate

```bash
cat ~/ots/federation/client.crt
```

### Step 2: Send to TAK Server Admin

**Email or secure message them:**

```
Subject: OpenTAKServer Federation Certificate

Hi,

I need to federate my OpenTAKServer with your TAK server.
Please add this certificate to your truststore:

-----BEGIN CERTIFICATE-----
[Paste your certificate here]
-----END CERTIFICATE-----

Federation Details:
- My Server IP: [YOUR_OPENTAKSERVER_IP]
- Protocol: v1 (or v2)
- Port I'll connect to: 9000 (or 9001)

Thanks!
```

### Step 3: Wait for Confirmation

They need to:
1. Add your certificate to their TAK server's truststore
2. Restart their TAK server (usually)
3. Confirm it's ready

---

## Part 6: Test the Connection

### Check OpenTAKServer Logs

```bash
# Watch logs in real-time
tail -f ~/ots/logs/opentakserver.log | grep -i federation
```

**Look for these messages:**

✅ **Good (connecting):**
```
INFO - Attempting to connect to federation server: TAK.gov Production
INFO - Connecting to federation server: TAK.gov Production (tak.gov:9000) via TCP
```

✅ **Success:**
```
INFO - Successfully connected to TAK.gov Production
INFO - Federation connection established
```

❌ **Problems:**
```
ERROR - Failed to connect to federation server: [SSL: CERTIFICATE_VERIFY_FAILED]
ERROR - Connection refused
ERROR - Timeout connecting to TAK server
```

### Check Web UI

1. Go to **Admin → Federation**
2. Look at the **Status** column for your server
3. **Green "Connected"** = Success! 🎉
4. **Gray "Disconnected"** = Still trying or failed
5. **Red "Error"** = Problem (check logs)

---

## Common Problems and Solutions

### Problem 1: "Certificate verify failed"

**Error message:**
```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed
```

**Causes:**
- TAK server doesn't trust your certificate yet
- You don't have their correct CA certificate

**Solution:**
```bash
# 1. Verify you have the right TAK server CA certificate
cat ~/ots/federation/truststore/tak-ca.crt

# 2. Make sure the TAK server admin added YOUR certificate
# 3. Wait 5-10 minutes for connection retry
```

### Problem 2: "Connection refused"

**Error message:**
```
Connection refused
```

**Causes:**
- Wrong IP address or hostname
- Wrong port number
- Firewall blocking connection

**Solution:**
```bash
# Test if you can reach the server
ping tak.gov

# Test if the port is open
telnet tak.gov 9000
# OR
nc -zv tak.gov 9000

# If these fail, check:
# 1. Firewall rules on your OpenTAKServer
# 2. Firewall rules on TAK server
# 3. Network connectivity
```

### Problem 3: "Timeout"

**Error message:**
```
Timeout connecting to TAK server
```

**Causes:**
- Network connectivity issue
- Firewall blocking outbound connections
- TAK server is down

**Solution:**
```bash
# Check if you can reach the internet
ping 8.8.8.8

# Check if you can reach TAK server
ping tak.gov

# Check firewall
sudo iptables -L -n | grep 9000
```

### Problem 4: "No such file or directory" for certificates

**Error message:**
```
FileNotFoundError: [Errno 2] No such file or directory: '/path/to/cert'
```

**Solution:**
```bash
# Verify certificate files exist
ls -la ~/ots/federation/
ls -la ~/ots/federation/truststore/

# Check file permissions
chmod 644 ~/ots/federation/client.crt
chmod 600 ~/ots/federation/client.key
chmod 644 ~/ots/federation/truststore/tak-ca.crt
```

### Problem 5: Can't find database password

**For Method 2 (command line), you need the database password.**

```bash
# Find it in your config
cat ~/ots/config.yml | grep SQLALCHEMY_DATABASE_URI

# Example output:
# SQLALCHEMY_DATABASE_URI: postgresql://ots:MY_PASSWORD@127.0.0.1/ots
#                                         ^^^^^^^^^^ This is the password
```

---

## Verify Federation is Working

### Test 1: Check Connection Status

```bash
# Run this on your OpenTAKServer
cd ~/OpenTAKServer
export PATH="/Users/iesouskurios/Library/Python/3.10/bin:$PATH"
poetry run python -c "
from opentakserver.extensions import db
from opentakserver.models.FederationServer import FederationServer
from opentakserver.app import create_app

app = create_app(cli=False)
with app.app_context():
    servers = FederationServer.query.all()
    for s in servers:
        print(f'{s.name}: {s.status} (enabled={s.enabled})')
"
```

**Expected output:**
```
TAK.gov Production: connected (enabled=True)
```

### Test 2: Send Test CoT Message

Once connected, any CoT messages sent to OpenTAKServer should forward to the federated TAK server.

Test from your ATAK device:
1. Send a marker or message
2. Check if it appears on TAK server
3. Check OpenTAKServer logs for "Forwarding CoT to federation"

---

## Quick Reference

### File Locations

```
~/ots/federation/
├── client.crt         # Your client certificate
├── client.key         # Your private key (keep secret!)
├── ca.crt            # Your CA certificate
└── truststore/
    └── tak-ca.crt    # TAK server's CA certificate
```

### Important Commands

```bash
# View logs
tail -f ~/ots/logs/opentakserver.log

# Restart OpenTAKServer
# (Method depends on how you're running it - systemd, docker, manual)
sudo systemctl restart opentakserver

# Check federation status via database
psql -U ots -d ots -c "SELECT name, address, port, status, enabled FROM federation_servers;"
```

### Default Ports

- **Federation v1:** 9000
- **Federation v2:** 9001
- **OpenTAKServer UI:** 8081
- **OpenTAKServer API:** 8081

---

## Getting Help

If you're stuck:

1. **Check logs** first:
   ```bash
   tail -100 ~/ots/logs/opentakserver.log | grep -i "error\|federation"
   ```

2. **Check GitHub Issues:**
   - https://github.com/brian7704/OpenTAKServer/issues

3. **Discord Community:**
   - Join the OpenTAKServer Discord (link in repo)

4. **Include this info when asking for help:**
   - OpenTAKServer version
   - TAK server type (TAK.gov, self-hosted, etc.)
   - Error message from logs
   - Federation protocol version (v1 or v2)

---

## Summary Checklist

Before you start:
- [ ] OpenTAKServer installed and running
- [ ] TAK server CA certificate obtained
- [ ] Client certificate generated
- [ ] Certificates in correct locations

Configuration steps:
- [ ] TAK server CA uploaded to `~/ots/federation/truststore/`
- [ ] Federation server added via Web UI or CLI
- [ ] Your client certificate shared with TAK server admin
- [ ] TAK server admin confirmed certificate added

Testing:
- [ ] Connection status shows "connected" in Web UI
- [ ] No errors in OpenTAKServer logs
- [ ] CoT messages forwarding successfully

---

**Good luck! You've got this. 🎖️**
