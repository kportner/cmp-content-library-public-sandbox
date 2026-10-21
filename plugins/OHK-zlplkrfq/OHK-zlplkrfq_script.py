from extensions.models import UIExtension


def should_display(server, request=None):
    """The 'Create Snapshot' button should be displayed for all servers, except where the UI extension for scheduled snapshots is disabled."""

    can_manage_snapshots = False
    if server and server.resource_handler:
        rh = server.resource_handler.cast()
        can_manage_snapshots = rh.can_manage_snapshots

    if (
        UIExtension.objects.filter(name="scheduled_snapshots", enabled=True).exists()
        and can_manage_snapshots
    ):
        return False

    return True
