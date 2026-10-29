"""
Apply the relevant Ansible Automation Configurations to the Server being provisioned,
based on the values for any Ansible Automation Configuration type Parameters.
"""

from connectors import connector_for


def run(job, **kwargs):
    """
    Apply the relevant Ansible Automation Configurations to the provisioning server.

    Reads the AAP-type CustomFieldValues set on the job's server to determine
    which Ansible Automation Configurations to apply. Only configurations whose
    AAP matches the server environment's ``install_application`` connector are
    applied; those are submitted to AAP and this waits for their completion.

    Args:
        job (Job): The provision job. It is expected to have exactly one server.
        **kwargs: Unused; present for the standard hook signature.

    Returns:
        tuple: A ``(result, "", "")`` tuple. When applicable configurations are
        submitted successfully, the result reflects their completion status;
        otherwise ``result`` defaults to "SUCCESS".
    """
    # There should only ever be 1 Server per Provision Job that this is running against
    server = job.server_set.first()
    # Note we unfortunately can't use something like values_list with CFV's "value"
    aap_apps = [
        cfv.value for cfv in server.custom_field_values.filter(field__type="AAP")
    ]
    aap_apps = set(aap_apps)
    config_mgr = connector_for(server.environment, "install_application")
    applicable_aap_apps = [a for a in aap_apps if a.aap == config_mgr]

    result = "SUCCESS"
    if config_mgr and applicable_aap_apps:
        result, aap_job_ids = config_mgr.apply_configurations_in_aap(
            server, applicable_aap_apps, job
        )
        if result == "SUCCESS" and aap_job_ids:
            return config_mgr.wait_for_completion_in_aap(job, aap_job_ids)

    return result, "", ""
