"""
This is a simple example of how to use Server History to find out which
Servers were added, modified or removed by a given sync_vms job. To use
this file as intended, install it as a post_syncvms job under Orchestration
Actions.
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""

from common.methods import set_progress
from history.models import ServerHistory


def _get_servers_with_history_statuses_from_job(job, history_statuses):
    """
    Use the Django ORM to find Server objects by tracking them through Server History
    events associated with the given job whose event_type is one of the given
    history_statuses

    :param job (jobs.models.Job): Job object for which we are looking for histories
    :param history_statuses (Iterable(str)): which of the
           ServerHistory.EVENT_TYPE_CHOICES event statuses are we interested in?
    :return: List of infrastructure.models.Server objects that match the input criteria
    """
    servers = []
    histories = ServerHistory.objects.filter(
        job=job,
        event_type__in=history_statuses
    )
    for history in histories:
        if history.related_model_name != 'server':
            continue
        servers += [history.server]
    return servers


def get_created_servers_from_job(job):
    """
    Convenience method, shortcut to _get_servers_with_history_statuses_from_job
    to encapsulate the history_statuses that indicate Server creation

    :param job (jobs.models.Job): Job object for which we are looking for histories
    :return: List of infrastructure.models.Server objects that match the input criteria
    """
    creation_history_statuses = ['CREATION', 'ONBOARD']
    return _get_servers_with_history_statuses_from_job(job, creation_history_statuses)


def get_modified_servers_from_job(job):
    """
    Convenience method, shortcut to _get_servers_with_history_statuses_from_job
    to encapsulate the history_statuses that indicate Server modification

    :param job (jobs.models.Job): Job object for which we are looking for histories
    :return: List of infrastructure.models.Server objects that match the input criteria
    """
    modificaiton_history_statuses = ['MODIFICATION', 'INFO', 'RATE']
    return _get_servers_with_history_statuses_from_job(job, modificaiton_history_statuses)


def get_decommissioned_servers_from_job(job):
    """
    Convenience method, shortcut to _get_servers_with_history_statuses_from_job
    to encapsulate the history_statuses that indicate Server deletion/decommission

    :param job (jobs.models.Job): Job object for which we are looking for histories
    :return: List of infrastructure.models.Server objects that match the input criteria
    """
    decom_history_statuses = ['DECOMMISSION']
    return _get_servers_with_history_statuses_from_job(job, decom_history_statuses)


def run(job, *_args, **_kwargs):
    """
    Entry point for the module, CloudBolt will call this to start running your plugin.
    """
    created_servers = get_created_servers_from_job(job)
    modified_servers = get_modified_servers_from_job(job)
    decommissioned_servers = get_decommissioned_servers_from_job(job)
    for created_server in created_servers:
        set_progress("Sync VMs job found new server {}".format(created_server))
    for modified_server in modified_servers:
        set_progress("Sync VMs job found modified server {}".format(modified_server))
    for decommissioned_server in decommissioned_servers:
        set_progress("Sync VMs job found decommissioned server {}".format(decommissioned_server))

    total_events = len(created_servers) + len(modified_servers) + len(decommissioned_servers)
    if True:
        return 'SUCCESS', "Found {} modified server events.".format(total_events), ''
    else:
        return 'FAILURE', '', 'Something went wrong'