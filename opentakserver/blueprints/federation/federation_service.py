"""
Federation Service

This service handles:
1. Outbound connections to federated TAK servers
2. Inbound connections from federated TAK servers
3. Mission change synchronization
4. CoT message federation
5. Connection health monitoring and retry logic
"""

import ssl
import socket
import threading
import time
import json
from xml.etree.ElementTree import tostring
from datetime import datetime
from typing import Optional

from opentakserver.extensions import db, logger
from opentakserver.models.FederationServer import FederationServer
from opentakserver.models.FederationOutbound import FederationOutbound
from opentakserver.models.MissionChange import MissionChange, generate_mission_change_cot
from opentakserver.models.Mission import Mission


class FederationConnection:
    """
    Represents an active connection to a federated server.

    Handles:
    - TLS socket connection
    - Message sending/receiving
    - Heartbeat/keepalive
    - Reconnection logic
    """

    def __init__(self, federation_server: FederationServer, app_config):
        self.federation_server = federation_server
        self.app_config = app_config
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self.send_thread: Optional[threading.Thread] = None
        self.receive_thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None

    def connect(self) -> bool:
        """
        Establish connection to the federated server.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to federation server: {self.federation_server.name} "
                       f"({self.federation_server.address}:{self.federation_server.port})")

            # Create socket
            raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_socket.settimeout(30)

            # Wrap with TLS if enabled
            if self.federation_server.use_tls:
                context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

                # Load CA certificate if provided
                if self.federation_server.ca_certificate:
                    # TODO: Write CA cert to temp file and load it
                    # context.load_verify_locations(ca_cert_file)
                    pass

                # Load client certificate and key for mutual TLS
                if self.federation_server.client_certificate and self.federation_server.client_key:
                    # TODO: Write cert/key to temp files and load them
                    # context.load_cert_chain(cert_file, key_file)
                    pass

                # Disable SSL verification if configured
                if not self.federation_server.verify_ssl:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE

                self.socket = context.wrap_socket(
                    raw_socket,
                    server_hostname=self.federation_server.address
                )
            else:
                self.socket = raw_socket

            # Connect
            self.socket.connect((self.federation_server.address, self.federation_server.port))
            self.connected = True
            self.running = True

            # Update database status
            with db.session.begin():
                server = db.session.query(FederationServer).get(self.federation_server.id)
                server.status = FederationServer.STATUS_CONNECTED
                server.last_connected = datetime.utcnow()
                server.last_error = None

            logger.info(f"Successfully connected to federation server: {self.federation_server.name}")

            # Start threads
            self.start_threads()

            return True

        except Exception as e:
            logger.error(f"Failed to connect to federation server {self.federation_server.name}: {e}",
                        exc_info=True)

            # Update database status
            try:
                with db.session.begin():
                    server = db.session.query(FederationServer).get(self.federation_server.id)
                    server.status = FederationServer.STATUS_ERROR
                    server.last_error = str(e)
            except Exception as db_error:
                logger.error(f"Failed to update federation server status: {db_error}", exc_info=True)

            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from the federated server"""
        logger.info(f"Disconnecting from federation server: {self.federation_server.name}")

        self.running = False
        self.connected = False

        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.error(f"Error closing socket: {e}")

        # Wait for threads to finish
        if self.send_thread and self.send_thread.is_alive():
            self.send_thread.join(timeout=5)
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=5)
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=5)

        # Update database status
        try:
            with db.session.begin():
                server = db.session.query(FederationServer).get(self.federation_server.id)
                server.status = FederationServer.STATUS_DISCONNECTED
        except Exception as e:
            logger.error(f"Failed to update federation server status: {e}", exc_info=True)

    def start_threads(self):
        """Start background threads for sending, receiving, and heartbeat"""
        self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)

        self.send_thread.start()
        self.receive_thread.start()
        self.heartbeat_thread.start()

    def _send_loop(self):
        """
        Background thread that sends pending mission changes to the federated server.

        Implements Mission Federation Disruption Tolerance by retrying failed sends.
        """
        logger.info(f"Starting send loop for federation server: {self.federation_server.name}")

        while self.running and self.connected:
            try:
                # Query for pending mission changes that need to be sent
                with db.session.begin():
                    pending = db.session.query(FederationOutbound).filter_by(
                        federation_server_id=self.federation_server.id,
                        sent=False
                    ).filter(
                        (FederationOutbound.retry_count < self.app_config.get('OTS_FEDERATION_MAX_RETRIES', 5))
                    ).limit(10).all()

                    for outbound in pending:
                        try:
                            # Get the mission change
                            mission_change = outbound.mission_change
                            mission = mission_change.mission

                            # Generate CoT for this change
                            cot_element = generate_mission_change_cot(
                                author_uid=mission_change.creator_uid,
                                mission=mission,
                                mission_change=mission_change,
                                content=mission_change.content_resource,
                                mission_uid=mission_change.uid
                            )

                            # Convert to XML string
                            cot_xml = tostring(cot_element, encoding='utf-8')

                            # Send to federated server
                            self.socket.sendall(cot_xml)

                            # Update outbound record
                            outbound.sent = True
                            outbound.sent_at = datetime.utcnow()
                            outbound.last_error = None

                            logger.debug(f"Sent mission change {mission_change.id} to {self.federation_server.name}")

                        except Exception as e:
                            logger.error(f"Error sending mission change {outbound.mission_change_id}: {e}",
                                       exc_info=True)
                            outbound.retry_count += 1
                            outbound.last_retry_at = datetime.utcnow()
                            outbound.last_error = str(e)[:1000]  # Truncate to fit in DB

                # Sleep before checking for more changes
                time.sleep(5)

            except Exception as e:
                logger.error(f"Error in send loop for {self.federation_server.name}: {e}", exc_info=True)
                time.sleep(10)

        logger.info(f"Send loop stopped for federation server: {self.federation_server.name}")

    def _receive_loop(self):
        """
        Background thread that receives mission changes from the federated server.

        Processes incoming CoT messages and creates mission changes marked as federated.
        """
        logger.info(f"Starting receive loop for federation server: {self.federation_server.name}")

        buffer = b""

        while self.running and self.connected:
            try:
                # Receive data
                data = self.socket.recv(8192)
                if not data:
                    logger.warning(f"Connection closed by {self.federation_server.name}")
                    self.connected = False
                    break

                buffer += data

                # Process complete CoT messages
                # TAK CoT messages are XML and end with </event>
                while b"</event>" in buffer:
                    end_idx = buffer.find(b"</event>") + len(b"</event>")
                    cot_message = buffer[:end_idx]
                    buffer = buffer[end_idx:]

                    # Process the CoT message
                    self._process_federated_cot(cot_message)

            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error in receive loop for {self.federation_server.name}: {e}", exc_info=True)
                self.connected = False
                break

        logger.info(f"Receive loop stopped for federation server: {self.federation_server.name}")

    def _heartbeat_loop(self):
        """
        Background thread that sends periodic heartbeat messages to keep the connection alive.
        """
        logger.info(f"Starting heartbeat loop for federation server: {self.federation_server.name}")

        interval = self.app_config.get('OTS_FEDERATION_HEARTBEAT_INTERVAL', 30)

        while self.running and self.connected:
            try:
                # Send a simple heartbeat CoT message
                # TODO: Implement proper TAK heartbeat/ping message
                time.sleep(interval)

            except Exception as e:
                logger.error(f"Error in heartbeat loop for {self.federation_server.name}: {e}", exc_info=True)

        logger.info(f"Heartbeat loop stopped for federation server: {self.federation_server.name}")

    def _process_federated_cot(self, cot_xml: bytes):
        """
        Process an incoming CoT message from a federated server.

        Args:
            cot_xml: Raw CoT XML message
        """
        try:
            # TODO: Parse CoT XML and process mission changes
            # This should:
            # 1. Parse the XML to extract mission change details
            # 2. Check if it's a mission-related CoT
            # 3. Create a MissionChange record with isFederatedChange=True
            # 4. Broadcast to local clients via RabbitMQ

            logger.debug(f"Received CoT from {self.federation_server.name}: {cot_xml[:200]}")

        except Exception as e:
            logger.error(f"Error processing federated CoT: {e}", exc_info=True)


class FederationService:
    """
    Main federation service that manages all federation connections.

    This service:
    - Maintains connections to all enabled outbound federation servers
    - Monitors connection health
    - Handles reconnection logic
    - Manages inbound federation server listeners
    """

    def __init__(self, app_config):
        self.app_config = app_config
        self.connections: dict[int, FederationConnection] = {}
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None

    def start(self):
        """Start the federation service"""
        if not self.app_config.get('OTS_ENABLE_FEDERATION', False):
            logger.info("Federation is disabled")
            return

        logger.info("Starting Federation Service")
        self.running = True

        # Start connection monitor thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        logger.info("Federation Service started")

    def stop(self):
        """Stop the federation service"""
        logger.info("Stopping Federation Service")
        self.running = False

        # Disconnect all connections
        for connection in list(self.connections.values()):
            connection.disconnect()

        self.connections.clear()

        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=10)

        logger.info("Federation Service stopped")

    def _monitor_loop(self):
        """
        Background thread that monitors federation connections and handles reconnection.
        """
        logger.info("Starting federation monitor loop")

        while self.running:
            try:
                # Query for enabled outbound federation servers
                with db.session.begin():
                    servers = db.session.query(FederationServer).filter_by(
                        enabled=True,
                        connection_type=FederationServer.OUTBOUND
                    ).all()

                    for server in servers:
                        # Check if we have an active connection
                        if server.id not in self.connections or not self.connections[server.id].connected:
                            # Try to establish connection
                            logger.info(f"Attempting to connect to federation server: {server.name}")
                            connection = FederationConnection(server, self.app_config)

                            if connection.connect():
                                self.connections[server.id] = connection
                            else:
                                # Connection failed, will retry on next loop
                                logger.warning(f"Failed to connect to {server.name}, will retry")

                # Remove disconnected connections
                for server_id in list(self.connections.keys()):
                    if not self.connections[server_id].connected:
                        del self.connections[server_id]

                # Sleep before next check
                time.sleep(self.app_config.get('OTS_FEDERATION_RETRY_INTERVAL', 60))

            except Exception as e:
                logger.error(f"Error in federation monitor loop: {e}", exc_info=True)
                time.sleep(30)

        logger.info("Federation monitor loop stopped")

    def queue_mission_change(self, mission_change_id: int):
        """
        Queue a mission change to be sent to all federated servers.

        Args:
            mission_change_id: ID of the mission change to send
        """
        try:
            with db.session.begin():
                # Get all enabled federation servers that sync missions
                servers = db.session.query(FederationServer).filter_by(
                    enabled=True,
                    sync_missions=True
                ).all()

                for server in servers:
                    # Check if this mission change should be sent to this server
                    # (based on mission_filter if configured)

                    # Create outbound record
                    outbound = FederationOutbound(
                        federation_server_id=server.id,
                        mission_change_id=mission_change_id,
                        sent=False
                    )
                    db.session.add(outbound)

                logger.debug(f"Queued mission change {mission_change_id} for {len(servers)} federation servers")

        except Exception as e:
            logger.error(f"Error queuing mission change for federation: {e}", exc_info=True)
