# Backend Implementation Complete: Transport Protocol Support

## Summary for UI Team

The backend now fully supports the `transport_protocol` field that the UI has implemented. Here's what was added:

## Changes Made to Backend

### 1. Database Model (`FederationServer`)
**File**: `opentakserver/models/FederationServer.py`

Added transport protocol constants:
```python
# Transport protocols
TRANSPORT_TCP = "tcp"        # TCP transport (default)
TRANSPORT_UDP = "udp"        # UDP transport
TRANSPORT_MULTICAST = "multicast"  # Multicast transport
```

Added field to model:
```python
transport_protocol: Mapped[str] = mapped_column(String(20), nullable=False, default=TRANSPORT_TCP)
```

### 2. Database Migration
**File**: `opentakserver/migrations/versions/b1c2d3e4f5a6_add_transport_protocol_to_federation.py`

Created migration that adds `transport_protocol` column to `federation_servers` table with:
- Type: `String(20)`
- Nullable: `False`
- Default: `'tcp'`

### 3. API Updates
**File**: `opentakserver/blueprints/federation/federation_api.py`

#### POST `/api/federation/servers` (Create)
- Added `transport_protocol` to optional parameters in docstring
- Added validation:
  ```python
  transport_protocol = data.get('transport_protocol', FederationServer.TRANSPORT_TCP)
  if transport_protocol not in [FederationServer.TRANSPORT_TCP, FederationServer.TRANSPORT_UDP, FederationServer.TRANSPORT_MULTICAST]:
      return jsonify({'success': False, 'error': 'Invalid transport_protocol. Must be "tcp", "udp", or "multicast"'}), 400
  ```
- Added field to server creation

#### PUT `/api/federation/servers/<id>` (Update)
- Added `'transport_protocol'` to `updateable_fields` list
- Field can now be updated via API

#### GET Endpoints
- `transport_protocol` is automatically included in `to_json()` serialization
- All GET endpoints now return this field

### 4. Documentation Updates
**File**: `FEDERATION.md`

Added transport protocol table:
```markdown
### Transport Protocols

| Transport | Status | Encryption | Description |
|-----------|--------|------------|-------------|
| TCP | ✅ Supported | TLS/SSL | Default transport (recommended) |
| UDP | ⚠️ Planned | DTLS | Datagram transport (configuration available) |
| Multicast | ⚠️ Planned | DTLS | Multicast group transport (configuration available) |
```

## API Contract for UI

### Expected Values
The backend accepts and returns these values for `transport_protocol`:
- `"tcp"` (default)
- `"udp"`
- `"multicast"`

### Response Format
GET requests return:
```json
{
  "id": 1,
  "name": "Remote Server",
  "transport_protocol": "tcp",
  ...
}
```

### Validation
The API will return a 400 error if an invalid transport_protocol is provided:
```json
{
  "success": false,
  "error": "Invalid transport_protocol. Must be \"tcp\", \"udp\", or \"multicast\""
}
```

## Implementation Status

### ✅ Fully Implemented
- Database schema with `transport_protocol` field
- Database migration for adding the field
- API validation (create and update)
- Field serialization in JSON responses
- Documentation

### ⚠️ Configuration Only (Not Functional Yet)
- **UDP transport**: You can configure it, but the connection logic doesn't implement UDP yet
- **Multicast transport**: You can configure it, but the connection logic doesn't implement multicast yet

### 🔄 Currently Functional
- **TCP transport**: Fully functional (with TLS/SSL once cert loading is fixed)

## UI Implementation Compatibility

Your UI implementation should be 100% compatible with the backend now. The field:
- ✅ Exists in the database
- ✅ Has proper validation in the API
- ✅ Returns in all GET requests
- ✅ Can be set via POST (create)
- ✅ Can be updated via PUT (update)
- ✅ Has a sensible default (`"tcp"`)

## Important Notes for UI

1. **TLS vs DTLS Label**: Your UI correctly shows "TLS" for TCP and "DTLS" for UDP/multicast. This is correct:
   - TCP uses TLS (Transport Layer Security)
   - UDP/Multicast use DTLS (Datagram TLS)

2. **Functional Warning**: You may want to show a warning in the UI when users select UDP or multicast:
   ```
   ⚠️ Note: UDP and multicast transports are not yet implemented in the backend.
   You can configure them now, but connections will not work until the feature is complete.
   ```

3. **Default Behavior**: If the field is omitted from the request, the backend defaults to `"tcp"`, which is safe and functional.

## Testing the Integration

### Test 1: Create with TCP (should work)
```bash
curl -X POST http://localhost:8080/api/federation/servers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "Test Server",
    "address": "192.168.1.100",
    "port": 9001,
    "transport_protocol": "tcp"
  }'
```

Expected: Success, server created with `transport_protocol: "tcp"`

### Test 2: Create with UDP (config only)
```bash
curl -X POST http://localhost:8080/api/federation/servers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "Test UDP Server",
    "address": "192.168.1.101",
    "port": 9001,
    "transport_protocol": "udp"
  }'
```

Expected: Success, server created with `transport_protocol: "udp"` (but won't connect yet)

### Test 3: Invalid transport
```bash
curl -X POST http://localhost:8080/api/federation/servers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "Test Invalid",
    "address": "192.168.1.102",
    "port": 9001,
    "transport_protocol": "invalid"
  }'
```

Expected: 400 error with message about invalid transport_protocol

### Test 4: Omit transport_protocol (default)
```bash
curl -X POST http://localhost:8080/api/federation/servers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "Test Default",
    "address": "192.168.1.103",
    "port": 9001
  }'
```

Expected: Success, server created with default `transport_protocol: "tcp"`

## Database Schema

For reference, the `federation_servers` table now includes:
```sql
transport_protocol VARCHAR(20) NOT NULL DEFAULT 'tcp'
```

## Migration Instructions

When deploying this backend update:
1. The migration will automatically add the `transport_protocol` column
2. Existing federation servers will get `transport_protocol = 'tcp'` (default)
3. No data loss or corruption
4. UI can immediately start using the field

## Summary

✅ **Backend is ready** for the UI's transport protocol selector.
✅ **Field is fully supported** in the API.
✅ **Validation is in place** to prevent invalid values.
⚠️ **UDP and multicast** are config-only (not yet functional).

The UI team can proceed with confidence that the backend will properly handle the `transport_protocol` field!

---

**Files Modified**:
- `opentakserver/models/FederationServer.py`
- `opentakserver/blueprints/federation/federation_api.py`
- `FEDERATION.md`

**Files Created**:
- `opentakserver/migrations/versions/b1c2d3e4f5a6_add_transport_protocol_to_federation.py`
