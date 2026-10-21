"""
CloudBolt Plug-in that creates snapshot for a server.
"""

from infrastructure.models import ServerSnapshot
from utilities.exceptions import LogAndAlertException
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def run(job, *args, **kwargs):
    """
    Create a snapshot of the job's server via its resource handler.

    Because CloudBolt supports only one snapshot per server, any existing
    CB-initiated snapshots are queued for deletion once the new snapshot is
    created (except for vCloud Director, which already enforces one snapshot per
    server).

    Args:
        job (Job): The job whose first server is snapshotted.
        **kwargs: May include ``snapshot_name``; defaults to the action input
            template value when absent.

    Returns:
        Tuple[str, str, str]: A ``(status, output, errors)`` tuple.
        ``("SUCCESS", "Snapshot created", "")`` on success, otherwise a
        ``"FAILURE"`` tuple carrying the error message.
    """
    server = job.server_set.first()
    profile = job.owner
    rh = server.resource_handler.cast()
    # Fetch snapshot name from kwargs; but default it to action input.
    name = kwargs.get("snapshot_name", "{{snapshot_name}}")
    description = "{{ description }}"
    job.set_progress(f"Checking server {server} for snapshot...")
    snapshots_to_delete = list(ServerSnapshot.objects.filter(server=server))
    try:
        job.set_progress(f"Creating a new snapshot {name}...")
        new_snapshot = rh.create_snapshot(server, name, description)
        if new_snapshot:
            job.set_progress(f"Successfully created a new snapshot {name}.")
        else:
            LogAndAlertException(f"Error occurred while creating a snapshot {name}.")
        if new_snapshot and snapshots_to_delete and rh.type_slug != "vcloud_director":
            # currently we support only one snapshot per server. vcloud director
            # already supports only one snapshot per server.
            job.set_progress(
                f"Found CB-initiated snapshot {snapshots_to_delete[0].name}. "
                "Noting for deletion..."
            )
            server.create_delete_snapshots_job(profile, snapshots_to_delete)
            job.set_progress(f"Created a job to delete {snapshots_to_delete[0].name}.")

    except LogAndAlertException as e:
        logger.exception(e.log_message)
        return ("FAILURE", "", e.user_message)
    except Exception as err:
        return ("FAILURE", "", err)
    return ("SUCCESS", "Snapshot created", "")
