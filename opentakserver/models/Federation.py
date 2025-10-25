import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from opentakserver.extensions import db
from sqlalchemy import Integer, String, Boolean, TEXT, DateTime
from sqlalchemy.orm import Mapped, mapped_column


@dataclass
class Federation(db.Model):
    __tablename__ = 'federations'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=8089)
    protocol: Mapped[str] = mapped_column(String(10), nullable=False, default='ssl')  # 'tcp' or 'ssl'
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # SSL Certificate paths (stored on server filesystem)
    ca_cert_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    client_cert_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    client_key_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Authentication
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Data filtering - JSON array of data types to push
    # Example: ["cot", "chat", "missions", "datapackages", "video"]
    push_data_types: Mapped[str] = mapped_column(TEXT, default='["cot"]')

    # Connection status tracking
    connection_status: Mapped[str] = mapped_column(String(50), default='disconnected')  # disconnected, connected, error
    last_connected: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)

    # Statistics
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    messages_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Additional configuration
    notes: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)

    def get_push_data_types(self):
        """Parse JSON array of data types"""
        try:
            return json.loads(self.push_data_types)
        except (json.JSONDecodeError, TypeError):
            return ["cot"]

    def set_push_data_types(self, data_types: list):
        """Set data types as JSON array"""
        self.push_data_types = json.dumps(data_types)

    def serialize(self):
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'port': self.port,
            'protocol': self.protocol,
            'enabled': self.enabled,
            'has_ca_cert': bool(self.ca_cert_path),
            'has_client_cert': bool(self.client_cert_path),
            'has_client_key': bool(self.client_key_path),
            'username': self.username,
            'push_data_types': self.get_push_data_types(),
            'connection_status': self.connection_status,
            'last_connected': self.last_connected.isoformat() if self.last_connected else None,
            'last_error': self.last_error,
            'messages_sent': self.messages_sent,
            'messages_failed': self.messages_failed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'notes': self.notes
        }

    def to_json(self):
        return self.serialize()
