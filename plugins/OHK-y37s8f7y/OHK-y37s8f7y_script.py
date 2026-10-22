from common.methods import set_progress


def run(job, logger=None, *args, **kwargs):
    """
    Resize the AWS VM  -- UPDATED
    """
    new_size = kwargs.get('new_size', None)
    if not new_size:
        new_size = "{{new_size}}"
    if new_size is None:
        return "FAILURE", "", "ERROR, did not receive a new size"

    server = kwargs.get("server", None)
    if server is None:
        return (
            "FAILURE",
            "",
            "This plugin only runs against a Server, no Server object given",
        )

    rh = server.resource_handler.cast()
    ec2 = rh.get_boto3_client(server.ec2serverinfo.ec2_region, "ec2")

    set_progress(f"Powering off server: {server}")
    ec2.stop_instances(InstanceIds=[server.resource_handler_svr_id])
    waiter = ec2.get_waiter("instance_stopped")
    waiter.wait(InstanceIds=[server.resource_handler_svr_id])

    set_progress(f"Changing Instance Size to {new_size}")
    ec2.modify_instance_attribute(
        InstanceId=server.resource_handler_svr_id, InstanceType={"Value": new_size}
    )

    set_progress(f"Powering on server: {server}")
    ec2.start_instances(InstanceIds=[server.resource_handler_svr_id])
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[server.resource_handler_svr_id])

    server.refresh_info()
    return "SUCCESS", "", ""


def generate_options_for_new_size(*args, **kwargs):
    """
    Get all AWS Sizes available for this environment
    """
    server = kwargs.get("server", None)
    results = []
    if server:
        environment = server.environment
        for cfv in environment.custom_field_options.filter(field__name="instance_type"):
            results.append(cfv.value)

        return results
    return None