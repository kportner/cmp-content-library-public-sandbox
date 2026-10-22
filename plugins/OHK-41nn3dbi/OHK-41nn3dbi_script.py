"""
Powers a single server on. Used by the *multijob* version of the 
"Auto-power control servers" recurring job.
"""
from common.methods import set_progress


def run(job=None, server=None, **kwargs):
    set_progress('Powering off server {}'.format(server))
    if server.power_on():
        return 'SUCCESS', 'Successfully powered on server.', ''
    else:
        return 'FAILURE', '', 'Failed to power on server.'