# OpenTAKServer Federation

OpenTAKServer supports federation with other TAK servers, allowing multiple servers to synchronize mission data and CoT messages across networks.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Setup Guide](#setup-guide)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)

## Overview

Federation enables multiple TAK servers to connect and share tactical information in real-time. OpenTAKServer implements both Federation v1 (legacy) and v2 (current) protocols, providing compatibility with official TAK Server and other implementations.

### Use Cases

- **Multi-Site Operations**: Connect TAK servers across different geographical locations
- **Network Bridging**: Share data between separate networks (e.g., classified and unclassified)
- **High Availability**: Distribute load across multiple servers
- **Hybrid Deployments**: Connect cloud-hosted and on-premise TAK servers

## Features

- ✅ **Federation v1 & v2 Support**: Compatible with both legacy (port 9000) and current (port 9001) protocols
- ✅ **TLS Mutual Authentication**: Secure server-to-server connections using X.509 certificates
- ✅ **Mission Synchronization**: Automatic propagation of mission changes across federated servers
- ✅ **Disruption Tolerance**: Automatic retry logic for failed transmissions
- ✅ **Selective Synchronization**: Filter which missions are federated to each server
- ✅ **Bidirectional Federation**: Support for both outbound and inbound connections
- ✅ **Federation Health Monitoring**: Track connection status and synchronization statistics

## Architecture

### Components

1. **Federation Server Model**: Database representation of federated server configurations
2. **Federation Service**: Background service managing active connections
3. **Federation Outbound Tracker**: Tracks which mission changes have been sent to each server
4. **Federation API**: REST endpoints for managing federation configurations

### Connection Types

- **Outbound**: OpenTAKServer initiates connection to remote TAK server
- **Inbound**: Remote TAK server connects to OpenTAKServer

### Protocol Versions

| Version | Port | Status | Description |
|---------|------|--------|-------------|
| v1 | 9000 | Legacy | Original federation protocol |
| v2 | 9001 | Current | Enhanced federation protocol with improved features |

### Transport Protocols

| Transport | Status | Encryption | Description |
|-----------|--------|------------|-------------|
| TCP | ✅ Supported | TLS/SSL | Default transport (recommended) |
| UDP | ⚠️ Planned | DTLS | Datagram transport (configuration available) |
| Multicast | ⚠️ Planned | DTLS | Multicast group transport (configuration available) |

**Note**: UDP and multicast transports are configured in the database and API but implementation is pending. Currently only TCP with TLS/SSL is functional.

## Configuration

### Environment Variables

Add these to your environment or configuration file:

```bash
# Enable federation
OTS_ENABLE_FEDERATION=true

# Federation ports
OTS_FEDERATION_V1_PORT=9000
OTS_FEDERATION_V2_PORT=9001

# Bind address (0.0.0.0 for all interfaces)
OTS_FEDERATION_BIND_ADDRESS=0.0.0.0

# Certificate paths
OTS_FEDERATION_CERT_FILE=/path/to/ots/federation/server.crt
OTS_FEDERATION_KEY_FILE=/path/to/ots/federation/server.key
OTS_FEDERATION_CA_FILE=/path/to/ots/federation/ca.crt
OTS_FEDERATION_TRUSTSTORE_DIR=/path/to/ots/federation/truststore

# Retry and health monitoring
OTS_FEDERATION_RETRY_INTERVAL=60        # Seconds between retry attempts
OTS_FEDERATION_MAX_RETRIES=5            # Maximum retry attempts
OTS_FEDERATION_HEARTBEAT_INTERVAL=30    # Seconds between heartbeats
```

### Node ID

Each OpenTAKServer instance has a unique Node ID for federation identification:

```bash
# Set a persistent node ID (recommended for production)
OTS_NODE_ID=myserver-node-001

# If not set, a random ID will be generated on startup
```

## Setup Guide

### Prerequisites

1. OpenTAKServer installed and running
2. TLS certificates configured
3. Network connectivity between federated servers
4. Ports 9000 and/or 9001 open in firewall

### Step 1: Enable Federation

Edit your environment configuration:

```bash
OTS_ENABLE_FEDERATION=true
```

Restart OpenTAKServer to apply changes.

### Step 2: Prepare Certificates

Federation requires TLS mutual authentication. Each server needs:

- **Server Certificate**: Your server's identity certificate
- **Server Key**: Private key for your server certificate
- **CA Certificate**: Your Certificate Authority certificate
- **Truststore**: Directory containing CA certificates of federated servers

#### Certificate Exchange Process

1. **Export your CA certificate**:
   ```bash
   cp /path/to/ots/ca/ca.crt /path/to/ots/federation/ca.crt
   ```

2. **Share CA certificates**:
   - Send your `ca.crt` to the administrator of the remote TAK server
   - Receive the remote server's CA certificate
   - Place remote CA certificate in your truststore directory:
     ```bash
     cp remote-server-ca.crt /path/to/ots/federation/truststore/
     ```

### Step 3: Create Federation Server Configuration

Use the API or WebUI to create a federation server configuration.

#### Example: Outbound Connection (via API)

```bash
curl -X POST https://your-ots-server:8443/api/federation/servers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "Remote TAK Server",
    "description": "Federation to Site B",
    "address": "remote-tak-server.example.com",
    "port": 9001,
    "connection_type": "outbound",
    "protocol_version": "v2",
    "use_tls": true,
    "verify_ssl": true,
    "ca_certificate": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
    "client_certificate": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
    "client_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
    "sync_missions": true,
    "sync_cot": true,
    "enabled": true
  }'
```

#### Example: Inbound Connection

For inbound connections, remote servers initiate the connection to your OpenTAKServer:

```json
{
  "name": "Site C Inbound",
  "description": "Accept connections from Site C",
  "address": "0.0.0.0",
  "port": 9001,
  "connection_type": "inbound",
  "protocol_version": "v2",
  "use_tls": true,
  "verify_ssl": true,
  "ca_certificate": "...",
  "sync_missions": true,
  "enabled": true
}
```

### Step 4: Verify Connection

Check federation health status:

```bash
curl https://your-ots-server:8443/api/federation/health \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "success": true,
  "health": {
    "federation_enabled": true,
    "total_servers": 2,
    "enabled_servers": 2,
    "connected_servers": 2,
    "node_id": "myserver-node-001"
  }
}
```

### Step 5: Monitor Synchronization

Get synchronization statistics for a specific federation server:

```bash
curl https://your-ots-server:8443/api/federation/servers/1/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "success": true,
  "status": {
    "server": {
      "id": 1,
      "name": "Remote TAK Server",
      "status": "connected",
      "last_connected": "2025-10-28T12:00:00Z"
    },
    "stats": {
      "total_changes": 150,
      "sent_changes": 145,
      "pending_changes": 5
    }
  }
}
```

## API Reference

### List Federation Servers

```
GET /api/federation/servers
```

**Authorization**: Required (Administrator)

**Response**:
```json
{
  "success": true,
  "servers": [...]
}
```

### Create Federation Server

```
POST /api/federation/servers
```

**Authorization**: Required (Administrator)

**Required Fields**:
- `name`: Unique server name
- `address`: IP address or hostname
- `port`: Port number (9000 or 9001)

**Optional Fields**:
- `description`: Server description
- `connection_type`: "outbound" or "inbound" (default: "outbound")
- `protocol_version`: "v1" or "v2" (default: "v2")
- `transport_protocol`: "tcp", "udp", or "multicast" (default: "tcp")
- `use_tls`: Boolean (default: true, use_dtls for UDP)
- `verify_ssl`: Boolean (default: true)
- `ca_certificate`: Remote CA certificate (PEM format)
- `client_certificate`: Client certificate for outbound (PEM format)
- `client_key`: Client private key for outbound (PEM format)
- `sync_missions`: Boolean (default: true)
- `sync_cot`: Boolean (default: true)
- `mission_filter`: JSON array of mission names to sync
- `enabled`: Boolean (default: true)

### Get Federation Server

```
GET /api/federation/servers/{server_id}
```

**Authorization**: Required (Administrator)

### Update Federation Server

```
PUT /api/federation/servers/{server_id}
```

**Authorization**: Required (Administrator)

### Delete Federation Server

```
DELETE /api/federation/servers/{server_id}
```

**Authorization**: Required (Administrator)

### Get Server Status

```
GET /api/federation/servers/{server_id}/status
```

**Authorization**: Required (Administrator)

Returns connection status and synchronization statistics.

### Test Connection

```
POST /api/federation/servers/{server_id}/test
```

**Authorization**: Required (Administrator)

Tests connectivity to the federated server.

### Federation Health

```
GET /api/federation/health
```

**Authorization**: Required

Returns overall federation system health.

## Troubleshooting

### Connection Issues

**Problem**: Federation server shows "error" status

**Solutions**:
1. Verify network connectivity:
   ```bash
   telnet remote-server.example.com 9001
   ```

2. Check firewall rules - ensure ports 9000/9001 are open

3. Verify certificate configuration:
   - Ensure CA certificates are properly exchanged
   - Check certificate expiration dates
   - Verify certificate Subject/CN matches server hostname

4. Check logs for detailed error messages:
   ```bash
   tail -f /path/to/ots/logs/opentakserver.log | grep -i federation
   ```

### Mission Changes Not Syncing

**Problem**: Mission changes created locally but not appearing on federated server

**Solutions**:
1. Check server is enabled and connected:
   ```
   GET /api/federation/servers/{id}/status
   ```

2. Verify `sync_missions` is set to `true`

3. Check for mission filters that might exclude the mission

4. Review synchronization statistics for pending changes

5. Check federation service is running (look for Federation Service log entries)

### Certificate Errors

**Problem**: SSL/TLS handshake failures

**Solutions**:
1. Verify certificate format (PEM)

2. Ensure certificates include both Server and Client Authentication in Extended Key Usage

3. Check certificate chain is complete

4. Temporarily disable SSL verification for testing (not recommended for production):
   ```json
   {
     "verify_ssl": false
   }
   ```

### Performance Issues

**Problem**: High latency in mission synchronization

**Solutions**:
1. Reduce `OTS_FEDERATION_HEARTBEAT_INTERVAL` for more frequent checks

2. Increase `OTS_RABBITMQ_PREFETCH` for batch processing

3. Use mission filters to reduce synchronization load

4. Check network bandwidth and latency between servers

### Retry Exhaustion

**Problem**: Changes showing max retries reached

**Solutions**:
1. Increase `OTS_FEDERATION_MAX_RETRIES`

2. Increase `OTS_FEDERATION_RETRY_INTERVAL`

3. Investigate root cause of transmission failures

4. Check if remote server is accepting connections

## Advanced Configuration

### Mission Filtering

Limit which missions are synchronized to specific servers:

```json
{
  "mission_filter": ["Operation-Alpha", "Training-*", "Emergency-*"]
}
```

Supports exact names and wildcards.

### Hub and Spoke Topology

For multi-hop federation, configure a central hub server:

1. Hub server: Configure inbound connections from all spokes
2. Spoke servers: Configure outbound connections to hub only
3. Hub propagates changes between all spokes

### Custom Ports

To use non-standard ports:

```bash
OTS_FEDERATION_V2_PORT=19001
```

Then configure federation servers to use the custom port.

## Security Best Practices

1. **Always use TLS**: Enable `use_tls` for all connections
2. **Verify Certificates**: Keep `verify_ssl: true` in production
3. **Restrict Access**: Use firewall rules to limit who can connect
4. **Regular Certificate Rotation**: Update certificates before expiration
5. **Monitor Connections**: Review federation health regularly
6. **Use Unique Node IDs**: Set persistent node IDs for each server
7. **Secure Certificate Storage**: Protect private keys with appropriate file permissions

## Future Enhancements

The following features are planned for future releases:

- [ ] CoT message federation (currently only mission changes)
- [ ] Federation group mapping and permissions
- [ ] Web UI for federation management
- [ ] Advanced conflict resolution
- [ ] Federation performance metrics and dashboards
- [ ] Federation audit logging
- [ ] Dynamic discovery of federated servers

## Support

For federation-related issues:
1. Check the troubleshooting section above
2. Review logs for error messages
3. Join the [OpenTAKServer Discord](https://discord.gg/6uaVHjtfXN)
4. Report issues on [GitHub](https://github.com/brian7704/OpenTAKServer/issues)
