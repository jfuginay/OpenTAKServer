"""
Federation Helper Functions

Utility functions for integrating federation with other parts of OpenTAKServer.
"""

from opentakserver.extensions import logger, db
from opentakserver.models.FederationServer import FederationServer
from opentakserver.models.FederationOutbound import FederationOutbound


def queue_mission_change_for_federation(mission_change_id: int) -> None:
    """
    Queue a mission change to be sent to all enabled federated servers.

    This function should be called after a mission change has been committed to the database.
    It creates FederationOutbound records for each enabled federation server that syncs missions.

    Args:
        mission_change_id: The ID of the mission change to queue

    Note:
        This function commits changes to the database.
    """
    try:
        # Get all enabled federation servers that sync missions
        servers = FederationServer.query.filter_by(
            enabled=True,
            sync_missions=True
        ).all()

        if not servers:
            logger.debug(f"No enabled federation servers to queue mission change {mission_change_id}")
            return

        # Create outbound records for each server
        for server in servers:
            # Check if this mission change has already been queued for this server
            existing = FederationOutbound.query.filter_by(
                federation_server_id=server.id,
                mission_change_id=mission_change_id
            ).first()

            if existing:
                logger.debug(f"Mission change {mission_change_id} already queued for server {server.name}")
                continue

            # TODO: Check mission_filter if configured to see if this mission should be sent

            # Create outbound record
            outbound = FederationOutbound(
                federation_server_id=server.id,
                mission_change_id=mission_change_id,
                sent=False,
                acknowledged=False,
                retry_count=0
            )
            db.session.add(outbound)

        db.session.commit()
        logger.debug(f"Queued mission change {mission_change_id} for {len(servers)} federation servers")

    except Exception as e:
        logger.error(f"Error queuing mission change {mission_change_id} for federation: {e}", exc_info=True)
        db.session.rollback()


def should_federate_mission_change(mission_change) -> bool:
    """
    Determine if a mission change should be federated.

    Args:
        mission_change: The MissionChange object to check

    Returns:
        True if the change should be federated, False otherwise

    Rules:
        - Don't federate changes that are already marked as federated (to avoid loops)
        - Don't federate if federation is disabled
    """
    # Don't federate changes that came from another federation server
    if mission_change.isFederatedChange:
        return False

    return True
