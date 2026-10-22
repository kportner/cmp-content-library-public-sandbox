from resourcehandlers.aws.models import AWSHandler
import time
from common.methods import set_progress

def get_boto3_service_resource(env, service_name="ec2"):
    """
    Return boto connection to the EC2 in the specified environment's region.
    """
    # get aws resource handler object
    rh: AWSHandler = env.resource_handler.cast()

    # get aws client object
    client = rh.get_boto3_resource(env.aws_region, service_name)
    
    return client

def run(job, resource, *args, **kwargs):
    env  = resource.group.get_available_environments()[0]
    handler = AWSHandler.objects.get(id=resource.aws_rh_id)
    volume_id = resource.attributes.get(field__name='ebs_volume_id').value
    region = resource.attributes.get(field__name='aws_region').value
    
    device = resource.device_name
    instance_id = resource.instance_id

    ec2 = get_boto3_service_resource(env)
    volume = ec2.Volume(volume_id)

    state = volume.state
    if state.lower() != 'in-use':
        return "FAILURE", f"Can not detach volume from instance since the volume is in '{state.upper()}' state", ""

    try:
        response = volume.detach_from_instance(
            Device=device,
            InstanceId=instance_id,
        )
        state = response.get('State')
        # wait until the detachment process is complete
        count = 0
        while state == 'detaching':
            set_progress(f"Detaching Instance...")
            count += 5
            time.sleep(5)
            volume.reload()
            attachments = volume.attachments
            instance_ids = [i["InstanceId"] for i in attachments]
            if instance_id not in instance_ids:
                state = 'detached'
            if count > 3600:
                # Detaching is taking too long
                return "FAILURE", "Failed to detach volume from instance", "Detachment taking too long."

        resource.instance_id = "N/A"
        resource.device_name = "N/A"
        resource.volume_state = volume.state
        resource.save()

    except Exception as e:
        return "FAILURE", "Failed to attach volume to instance", f"{e}"
    return "SUCCESS", "", ""