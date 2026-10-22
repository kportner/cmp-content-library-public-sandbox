from django.template.defaultfilters import pluralize

from common.methods import set_progress


def run(job=None, resource=None, **kwargs):
    set_progress("Powering on resource '{}'".format(resource))

    hostnames = (
        resource.server_set.order_by('service_item__deploy_seq')
        .values_list('hostname', flat=True))
    set_progress(
        "Powering on {} server{} in the following sequence:\n{}"
        .format(
            len(hostnames),
            pluralize(len(hostnames)),
            ", ".join(hostnames)
        )
    )

    hostnames_tierless = (
        resource.server_set.filter(service_item=None)
        .values_list('hostname', flat=True))
    if hostnames_tierless:
        set_progress(
            "{} server{} have no server tier:\n"
            "{}\n"
            "The blueprint manager has likely deleted a server tier from the blueprint "
            "after this resource was deployed. These will be powered on first."
            .format(
                len(hostnames_tierless),
                pluralize(len(hostnames_tierless)),
                ", ".join(hostnames_tierless),
            )
        )

    if resource.power_on_servers():
        return 'SUCCESS', 'Successfully powered on servers from resource.', ''
    else:
        return 'FAILURE', '', 'Failed to power on servers from resource.'
