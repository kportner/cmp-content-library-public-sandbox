"""
Plugin creates an Amazon Machine Image from an EC2 instance. Server must be
powered off.  This action is intended to be a Server Action and the name of the
new AMI is specified at run time.
"""
from common.methods import set_progress

def run(job, logger=None):
    server = job.server_set.first()

    if not server:
        return "FAILURE", "", "No server found."

    if server.power_status != "POWEROFF":
        return "FAILURE", "", "Server must be powered off first."

    aws = server.resource_handler.cast()
    client = aws.get_boto3_client(server.ec2serverinfo.ec2_region,"ec2")

    if client is None:
        return "FAILURE", "", "Unable to create EC2 client."

    set_progress(
        f"Creating AMI from instance {server.resource_handler_svr_id}",
        logger,
        job,
    )

    response = client.create_image(
        InstanceId=server.resource_handler_svr_id,
        Name="{{ name_of_new_ami }}",
        Description="Created via CloudBolt",
        NoReboot=True,
    )

    image_id = response["ImageId"]
    
    set_progress(f"AMI creation started: {image_id}", logger, job)

    return "SUCCESS", f"AMI {image_id} creation started.", ""