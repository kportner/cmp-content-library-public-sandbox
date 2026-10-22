from common.methods import is_version_newer
from django.conf import settings


def run(job, server, **kwargs):
    job.set_progress("Resetting the password for server: '{}'".format(server))

    current_user = job.owner.user
    rh = server.environment.resource_handler
    try:
        success = rh.cast().set_windows_credentials(server.id, current_user)
    except AttributeError:
        current_version = settings.VERSION_INFO['VERSION']
        if is_version_newer('7.3', current_version):
            msg = ("This feature is supported on CloudBolt v7.3 or newer; your version is {}."
                   .format(current_version))
        else:
            msg = "This resource handler does not know how to set windows credentials."
        return ("FAILURE", msg, "")

    if success is False:
        return ("FAILURE", "No password was retrieved for server: '{}'".format(server), "")

    return "", "", ""