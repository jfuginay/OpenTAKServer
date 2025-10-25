import os
import socket
import ssl
import threading
import time
import traceback
from datetime import datetime
from typing import Dict, Optional

import pika
from flask import Flask
from sqlalchemy.orm import scoped_session

from opentakserver.extensions import logger, db
from opentakserver.models.Federation import Federation


class FederationConnection:
    """Manages a single connection to a federated TAK server"""

    def __init__(self, federation: Federation, app: Flask):
        self.federation_id = federation.id
        self.name = federation.name
        self.address = federation.address
        self.port = federation.port
        self.protocol = federation.protocol
        self.ca_cert_path = federation.ca_cert_path
        self.client_cert_path = federation.client_cert_path
        self.client_key_path = federation.client_key_path
        self.app = app

        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.last_error: Optional[str] = None
        self.reconnect_delay = 5  # seconds
        self.lock = threading.Lock()

    def connect(self):
        """Establish connection to federated TAK server"""
        try:
            with self.lock:
                if self.connected:
                    return True

                # Create socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(30)

                # SSL/TLS connection
                if self.protocol == 'ssl':
                    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE

                    # Load certificates if provided
                    if self.ca_cert_path and os.path.exists(self.ca_cert_path):
                        context.load_verify_locations(cafile=self.ca_cert_path)
                        context.verify_mode = ssl.CERT_REQUIRED

                    if self.client_cert_path and self.client_key_path:
                        if os.path.exists(self.client_cert_path) and os.path.exists(self.client_key_path):
                            context.load_cert_chain(
                                certfile=self.client_cert_path,
                                keyfile=self.client_key_path
                            )

                    # Wrap socket with SSL
                    self.socket = context.wrap_socket(sock, server_hostname=self.address)
                else:
                    # Plain TCP connection
                    self.socket = sock

                # Connect to remote server
                logger.info(f"Federation {self.name}: Connecting to {self.address}:{self.port} via {self.protocol.upper()}")
                self.socket.connect((self.address, self.port))

                self.connected = True
                self.last_error = None
                logger.info(f"Federation {self.name}: Connected successfully")

                # Update database
                self._update_status('connected', None)

                return True

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Federation {self.name}: Connection failed - {error_msg}")
            logger.error(traceback.format_exc())
            self.connected = False
            self.last_error = error_msg
            self._update_status('error', error_msg)

            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None

            return False

    def disconnect(self):
        """Close connection to federated server"""
        with self.lock:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None

            self.connected = False
            logger.info(f"Federation {self.name}: Disconnected")
            self._update_status('disconnected', None)

    def send_cot(self, cot_xml: str) -> bool:
        """Send CoT XML message to federated server"""
        if not self.connected:
            # Try to reconnect
            if not self.connect():
                return False

        try:
            with self.lock:
                if not self.socket:
                    return False

                # Send CoT message (needs to be properly formatted for TAK server)
                message = cot_xml.encode('utf-8')
                self.socket.sendall(message)

                # Update statistics
                self._increment_sent()
                return True

        except Exception as e:
            logger.error(f"Federation {self.name}: Failed to send CoT - {str(e)}")
            self.connected = False
            self.last_error = str(e)
            self._update_status('error', str(e))
            self._increment_failed()

            # Try to close socket
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None

            return False

    def _update_status(self, status: str, error: Optional[str]):
        """Update federation status in database"""
        try:
            with self.app.app_context():
                federation = db.session.get(Federation, self.federation_id)
                if federation:
                    federation.connection_status = status
                    federation.last_error = error
                    if status == 'connected':
                        federation.last_connected = datetime.utcnow()
                    db.session.commit()
        except Exception as e:
            logger.error(f"Failed to update federation status: {e}")

    def _increment_sent(self):
        """Increment sent message count"""
        try:
            with self.app.app_context():
                federation = db.session.get(Federation, self.federation_id)
                if federation:
                    federation.messages_sent += 1
                    db.session.commit()
        except Exception as e:
            logger.error(f"Failed to increment sent count: {e}")

    def _increment_failed(self):
        """Increment failed message count"""
        try:
            with self.app.app_context():
                federation = db.session.get(Federation, self.federation_id)
                if federation:
                    federation.messages_failed += 1
                    db.session.commit()
        except Exception as e:
            logger.error(f"Failed to increment failed count: {e}")


class FederationManager:
    """Manages all federation connections and message forwarding"""

    def __init__(self, app: Flask):
        self.app = app
        self.connections: Dict[int, FederationConnection] = {}
        self.running = False
        self.rabbit_connection: Optional[pika.BlockingConnection] = None
        self.rabbit_channel: Optional[pika.channel.Channel] = None
        self.refresh_thread: Optional[threading.Thread] = None

    def start(self):
        """Start the federation manager"""
        logger.info("Starting Federation Manager...")
        self.running = True

        # Load enabled federations
        self._load_federations()

        # Start connection monitoring thread
        self.refresh_thread = threading.Thread(target=self._monitor_connections, daemon=True)
        self.refresh_thread.start()

        # Connect to RabbitMQ and start consuming
        self._start_consuming()

    def stop(self):
        """Stop the federation manager"""
        logger.info("Stopping Federation Manager...")
        self.running = False

        # Disconnect all federations
        for conn in self.connections.values():
            conn.disconnect()

        # Close RabbitMQ connection
        if self.rabbit_channel:
            try:
                self.rabbit_channel.stop_consuming()
            except:
                pass

        if self.rabbit_connection:
            try:
                self.rabbit_connection.close()
            except:
                pass

    def _load_federations(self):
        """Load enabled federations from database and create connections"""
        try:
            with self.app.app_context():
                federations = db.session.query(Federation).filter_by(enabled=True).all()

                for federation in federations:
                    if federation.id not in self.connections:
                        conn = FederationConnection(federation, self.app)
                        self.connections[federation.id] = conn
                        # Attempt initial connection
                        conn.connect()
                        logger.info(f"Loaded federation: {federation.name}")
        except Exception as e:
            logger.error(f"Failed to load federations: {e}")
            logger.error(traceback.format_exc())

    def _monitor_connections(self):
        """Background thread to monitor and refresh connections"""
        while self.running:
            try:
                # Reload federations every 60 seconds
                time.sleep(60)

                with self.app.app_context():
                    # Get currently enabled federations
                    enabled_feds = db.session.query(Federation).filter_by(enabled=True).all()
                    enabled_ids = {f.id for f in enabled_feds}

                    # Remove disabled federations
                    for fed_id in list(self.connections.keys()):
                        if fed_id not in enabled_ids:
                            self.connections[fed_id].disconnect()
                            del self.connections[fed_id]
                            logger.info(f"Removed disabled federation {fed_id}")

                    # Add new federations
                    for federation in enabled_feds:
                        if federation.id not in self.connections:
                            conn = FederationConnection(federation, self.app)
                            self.connections[federation.id] = conn
                            conn.connect()
                            logger.info(f"Added new federation: {federation.name}")
                        else:
                            # Reconnect if disconnected
                            conn = self.connections[federation.id]
                            if not conn.connected:
                                conn.connect()

            except Exception as e:
                logger.error(f"Error in connection monitor: {e}")
                logger.error(traceback.format_exc())

    def _start_consuming(self):
        """Connect to RabbitMQ and consume CoT messages"""
        try:
            rabbit_credentials = pika.PlainCredentials(
                self.app.config.get("OTS_RABBITMQ_USERNAME"),
                self.app.config.get("OTS_RABBITMQ_PASSWORD")
            )
            rabbit_host = self.app.config.get("OTS_RABBITMQ_SERVER_ADDRESS")

            self.rabbit_connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=rabbit_host, credentials=rabbit_credentials)
            )
            self.rabbit_channel = self.rabbit_connection.channel()

            # Declare and bind to federation queue
            self.rabbit_channel.queue_declare(queue='federation')
            self.rabbit_channel.exchange_declare(exchange='cot_controller', exchange_type='fanout')
            self.rabbit_channel.queue_bind(exchange='cot_controller', queue='federation')

            self.rabbit_channel.basic_qos(prefetch_count=10)
            self.rabbit_channel.basic_consume(
                queue='federation',
                on_message_callback=self._on_message,
                auto_ack=False
            )

            logger.info("Federation Manager: Connected to RabbitMQ, consuming messages...")
            self.rabbit_channel.start_consuming()

        except Exception as e:
            logger.error(f"Failed to start RabbitMQ consumer: {e}")
            logger.error(traceback.format_exc())

    def _on_message(self, channel, method, properties, body):
        """Handle incoming CoT message from RabbitMQ"""
        try:
            # Decode CoT XML
            cot_xml = body.decode('utf-8')

            # Forward to all enabled federations
            for fed_id, conn in list(self.connections.items()):
                try:
                    # Check if this data type should be federated
                    with self.app.app_context():
                        federation = db.session.get(Federation, fed_id)
                        if federation and 'cot' in federation.get_push_data_types():
                            # Send CoT to this federation
                            conn.send_cot(cot_xml)
                except Exception as e:
                    logger.error(f"Failed to forward to federation {fed_id}: {e}")

            # Acknowledge message
            channel.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error(f"Error processing federation message: {e}")
            logger.error(traceback.format_exc())
            # Reject message
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
