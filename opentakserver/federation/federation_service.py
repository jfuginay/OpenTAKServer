#!/usr/bin/env python3
"""
Federation Service for OpenTAKServer
Connects to remote TAK servers and forwards CoT data
"""

import os
import platform
import sys
from logging.handlers import TimedRotatingFileHandler

import sqlalchemy
import yaml
from flask import Flask
from flask_security import SQLAlchemyUserDatastore, Security
from flask_security.models import fsqla
import flask_wtf
import colorlog
import logging

from opentakserver.EmailValidator import EmailValidator
from opentakserver.PasswordValidator import PasswordValidator
from opentakserver.extensions import db, logger
from opentakserver.defaultconfig import DefaultConfig
from opentakserver.federation.federation_manager import FederationManager

# Import all models to ensure they're registered
from opentakserver.models.Federation import Federation
from opentakserver.models.EUD import EUD
from opentakserver.models.CoT import CoT
from opentakserver.models.Point import Point
from opentakserver.models.Alert import Alert
from opentakserver.models.DataPackage import DataPackage
from opentakserver.models.Certificate import Certificate
from opentakserver.models.Marker import Marker
from opentakserver.models.RBLine import RBLine
from opentakserver.models.Team import Team
from opentakserver.models.GroupEud import GroupEud
from opentakserver.models.Group import Group
from opentakserver.models.EUDStats import EUDStats
from opentakserver.models.Mission import Mission
from opentakserver.models.MissionInvitation import MissionInvitation
from opentakserver.models.MissionContentMission import MissionContentMission
from opentakserver.models.MissionLogEntry import MissionLogEntry
from opentakserver.models.MissionChange import MissionChange
from opentakserver.models.MissionUID import MissionUID
from opentakserver.models.CasEvac import CasEvac
from opentakserver.models.ZMIST import ZMIST
from opentakserver.models.Chatrooms import Chatroom
from opentakserver.models.ChatroomsUids import ChatroomsUids
from opentakserver.models.VideoStream import VideoStream
from opentakserver.models.VideoRecording import VideoRecording
from opentakserver.models.WebAuthn import WebAuthn


def setup_logging(app):
    """Configure logging for federation service"""
    level = logging.INFO
    if app.config.get("DEBUG"):
        level = logging.DEBUG
    logger.setLevel(level)

    if sys.stdout.isatty():
        color_log_handler = colorlog.StreamHandler()
        color_log_formatter = colorlog.ColoredFormatter(
            '%(log_color)s[%(asctime)s] - federation[%(process)d] - %(module)s - %(funcName)s - %(lineno)d - %(levelname)s - %(message)s',
            datefmt="%Y-%m-%d %H:%M:%S")
        color_log_handler.setFormatter(color_log_formatter)
        logger.addHandler(color_log_handler)

    os.makedirs(os.path.join(app.config.get("OTS_DATA_FOLDER"), "logs"), exist_ok=True)
    fh = TimedRotatingFileHandler(
        os.path.join(app.config.get("OTS_DATA_FOLDER"), 'logs', 'federation.log'),
        when=app.config.get("OTS_LOG_ROTATE_WHEN"),
        interval=app.config.get("OTS_LOG_ROTATE_INTERVAL"),
        backupCount=app.config.get("OTS_BACKUP_COUNT")
    )
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] - federation[%(process)d] - %(module)s - %(funcName)s - %(lineno)d - %(levelname)s - %(message)s"))
    logger.addHandler(fh)


def create_app():
    """Create Flask application for federation service"""
    app = Flask(__name__)
    app.config.from_object(DefaultConfig)

    # Load config.yml if it exists
    if os.path.exists(os.path.join(app.config.get("OTS_DATA_FOLDER"), "config.yml")):
        app.config.from_file(os.path.join(app.config.get("OTS_DATA_FOLDER"), "config.yml"), load=yaml.safe_load)
    else:
        # First run, create config.yml based on default settings
        logger.info("Creating config.yml")
        with open(os.path.join(app.config.get("OTS_DATA_FOLDER"), "config.yml"), "w") as config:
            conf = {}
            for option in DefaultConfig.__dict__:
                # Fix the sqlite DB path on Windows
                if option == "SQLALCHEMY_DATABASE_URI" and platform.system() == "Windows" and DefaultConfig.__dict__[option].startswith("sqlite"):
                    conf[option] = DefaultConfig.__dict__[option].replace("////", "///").replace("\\", "/")
                elif option.isupper():
                    conf[option] = DefaultConfig.__dict__[option]
            config.write(yaml.safe_dump(conf))

    setup_logging(app)
    db.init_app(app)

    # Required by Flask Security
    try:
        fsqla.FsModels.set_db_info(db)
    except sqlalchemy.exc.InvalidRequestError:
        pass

    from opentakserver.models.user import User
    from opentakserver.models.role import Role

    flask_wtf.CSRFProtect(app)
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    app.security = Security(app, user_datastore, mail_util_cls=EmailValidator, password_util_cls=PasswordValidator)

    return app


def main():
    """Main entry point for federation service"""
    app = create_app()

    logger.info("=" * 60)
    logger.info("OpenTAKServer Federation Service Starting...")
    logger.info("=" * 60)

    # Create and start federation manager
    manager = FederationManager(app)

    try:
        manager.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        manager.stop()
        logger.info("Federation service stopped")
    except Exception as e:
        logger.error(f"Federation service error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        manager.stop()


if __name__ == "__main__":
    main()
