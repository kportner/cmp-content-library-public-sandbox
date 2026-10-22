"""
Powers a single server off. Used by the *multijob* version of the 
"Auto-power control servers" recurring job.
"""
from common.methods import set_progress


def run(job=None, server=None, **kwargs):
    set_progress('Powering off server {}'.format(server))
    if server.power_off():
        return 'SUCCESS', 'Successfully powered off server.', ''
    else:
        return 'FAILURE', '', 'Failed to power off server.'