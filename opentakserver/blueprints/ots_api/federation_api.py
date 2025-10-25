import os
import traceback
from datetime import datetime

import bleach
from flask import current_app as app, request, Blueprint, jsonify
from flask_security import auth_required, roles_required
from werkzeug.utils import secure_filename

from opentakserver.blueprints.ots_api.api import search, paginate
from opentakserver.extensions import logger, db
from opentakserver.models.Federation import Federation

federation_api_blueprint = Blueprint('federation_api_blueprint', __name__)

ALLOWED_CERT_EXTENSIONS = {'pem', 'crt', 'key', 'cer', 'p12', 'pfx'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_CERT_EXTENSIONS


@federation_api_blueprint.route('/api/federations', methods=['GET'])
@auth_required()
def get_federations():
    """Get list of all federation connections"""
    try:
        query = db.session.query(Federation)
        query = search(query, Federation, 'name')
        query = search(query, Federation, 'address')
        query = search(query, Federation, 'protocol')
        query = search(query, Federation, 'connection_status')

        return paginate(query)
    except Exception as e:
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@federation_api_blueprint.route('/api/federations/<int:federation_id>', methods=['GET'])
@auth_required()
def get_federation(federation_id):
    """Get a specific federation connection"""
    try:
        federation = db.session.get(Federation, federation_id)
        if not federation:
            return jsonify({'success': False, 'error': 'Federation not found'}), 404

        return jsonify({'success': True, 'federation': federation.to_json()})
    except Exception as e:
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@federation_api_blueprint.route('/api/federations', methods=['POST'])
@auth_required()
@roles_required('administrator')
def create_federation():
    """Create a new federation connection"""
    try:
        data = request.get_json()

        # Validate required fields
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        if not data.get('address'):
            return jsonify({'success': False, 'error': 'Address is required'}), 400

        # Check if name already exists
        existing = db.session.query(Federation).filter_by(name=data['name']).first()
        if existing:
            return jsonify({'success': False, 'error': 'Federation name already exists'}), 400

        # Create new federation
        federation = Federation(
            name=bleach.clean(data['name']),
            address=bleach.clean(data['address']),
            port=int(data.get('port', 8089)),
            protocol=bleach.clean(data.get('protocol', 'ssl')),
            enabled=data.get('enabled', True),
            username=bleach.clean(data.get('username', '')),
            password=data.get('password', ''),  # Note: Should be encrypted in production
            notes=bleach.clean(data.get('notes', '')),
        )

        # Set push data types
        if 'push_data_types' in data:
            federation.set_push_data_types(data['push_data_types'])

        db.session.add(federation)
        db.session.commit()

        logger.info(f"Created federation: {federation.name}")
        return jsonify({'success': True, 'federation': federation.to_json()}), 201

    except Exception as e:
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@federation_api_blueprint.route('/api/federations/<int:federation_id>', methods=['PUT'])
@auth_required()
@roles_required('administrator')
def update_federation(federation_id):
    """Update an existing federation connection"""
    try:
        federation = db.session.get(Federation, federation_id)
        if not federation:
            return jsonify({'success': False, 'error': 'Federation not found'}), 404

        data = request.get_json()

        # Update fields
        if 'name' in data:
            # Check if new name conflicts
            if data['name'] != federation.name:
                existing = db.session.query(Federation).filter_by(name=data['name']).first()
                if existing:
                    return jsonify({'success': False, 'error': 'Federation name already exists'}), 400
            federation.name = bleach.clean(data['name'])

        if 'address' in data:
            federation.address = bleach.clean(data['address'])
        if 'port' in data:
            federation.port = int(data['port'])
        if 'protocol' in data:
            federation.protocol = bleach.clean(data['protocol'])
        if 'enabled' in data:
            federation.enabled = data['enabled']
        if 'username' in data:
            federation.username = bleach.clean(data.get('username', ''))
        if 'password' in data and data['password']:  # Only update if provided
            federation.password = data['password']
        if 'notes' in data:
            federation.notes = bleach.clean(data.get('notes', ''))
        if 'push_data_types' in data:
            federation.set_push_data_types(data['push_data_types'])

        federation.updated_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"Updated federation: {federation.name}")
        return jsonify({'success': True, 'federation': federation.to_json()})

    except Exception as e:
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@federation_api_blueprint.route('/api/federations/<int:federation_id>', methods=['DELETE'])
@auth_required()
@roles_required('administrator')
def delete_federation(federation_id):
    """Delete a federation connection"""
    try:
        federation = db.session.get(Federation, federation_id)
        if not federation:
            return jsonify({'success': False, 'error': 'Federation not found'}), 404

        # Clean up certificate files
        cert_dir = os.path.join(app.config.get("OTS_DATA_FOLDER"), "federation", "certs", str(federation_id))
        if os.path.exists(cert_dir):
            import shutil
            shutil.rmtree(cert_dir)

        name = federation.name
        db.session.delete(federation)
        db.session.commit()

        logger.info(f"Deleted federation: {name}")
        return jsonify({'success': True})

    except Exception as e:
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@federation_api_blueprint.route('/api/federations/<int:federation_id>/upload_cert', methods=['POST'])
@auth_required()
@roles_required('administrator')
def upload_certificate(federation_id):
    """Upload SSL certificates for a federation connection"""
    try:
        federation = db.session.get(Federation, federation_id)
        if not federation:
            return jsonify({'success': False, 'error': 'Federation not found'}), 404

        cert_type = request.form.get('cert_type')  # 'ca', 'client_cert', or 'client_key'
        if not cert_type or cert_type not in ['ca', 'client_cert', 'client_key']:
            return jsonify({'success': False, 'error': 'Invalid cert_type. Must be ca, client_cert, or client_key'}), 400

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Invalid file type. Allowed: pem, crt, key, cer, p12, pfx'}), 400

        # Create cert directory
        cert_dir = os.path.join(app.config.get("OTS_DATA_FOLDER"), "federation", "certs", str(federation_id))
        os.makedirs(cert_dir, exist_ok=True)

        # Save file
        filename = secure_filename(file.filename)
        file_path = os.path.join(cert_dir, filename)
        file.save(file_path)

        # Update federation record
        if cert_type == 'ca':
            federation.ca_cert_path = file_path
        elif cert_type == 'client_cert':
            federation.client_cert_path = file_path
        elif cert_type == 'client_key':
            federation.client_key_path = file_path

        federation.updated_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"Uploaded {cert_type} certificate for federation: {federation.name}")
        return jsonify({'success': True, 'file_path': filename, 'federation': federation.to_json()})

    except Exception as e:
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@federation_api_blueprint.route('/api/federations/<int:federation_id>/test', methods=['POST'])
@auth_required()
@roles_required('administrator')
def test_federation(federation_id):
    """Test connection to a federation server"""
    try:
        federation = db.session.get(Federation, federation_id)
        if not federation:
            return jsonify({'success': False, 'error': 'Federation not found'}), 404

        # TODO: Implement actual connection test
        # This would attempt to connect to the TAK server and verify authentication

        return jsonify({
            'success': True,
            'message': 'Connection test not yet implemented',
            'federation': federation.to_json()
        })

    except Exception as e:
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@federation_api_blueprint.route('/api/federations/<int:federation_id>/toggle', methods=['POST'])
@auth_required()
@roles_required('administrator')
def toggle_federation(federation_id):
    """Enable/disable a federation connection"""
    try:
        federation = db.session.get(Federation, federation_id)
        if not federation:
            return jsonify({'success': False, 'error': 'Federation not found'}), 404

        federation.enabled = not federation.enabled
        federation.updated_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"Toggled federation {federation.name}: enabled={federation.enabled}")
        return jsonify({'success': True, 'enabled': federation.enabled, 'federation': federation.to_json()})

    except Exception as e:
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
