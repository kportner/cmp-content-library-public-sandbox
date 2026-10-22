from common.methods import set_progress
import time
from botocore.client import ClientError
from infrastructure.models import Environment
from resources.models import Resource
from resourcehandlers.aws.models import AWSHandler



def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="ec2"):
    """
    Return boto connection to the EC2 in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client

def generate_options_for_instances(resource, **kwargs):
    instances = []
    if resource:
        env  = resource.group.get_available_environments()[0]
        if resource.volume_state == "in-use":
            attached = "Volume is already attached to an instance, detach it from the instance and try again."
            raise AttributeError(f"{attached}")
        if resource:
            rh = AWSHandler.objects.get(id=resource.aws_rh_id)
    
            region = resource.aws_region
    
            ec2 = get_boto3_service_client(rh, region)
            response = ec2.describe_instances()['Reservations']
            for instance in response:
                res = instance['Instances'][0]
                instances.append(res.get('InstanceId'))
        if not len(instances):
            instances = "No instance found in this region, try creating an instance from AWS EC2 first."
            raise AttributeError(f"{instances}")
    return instances

def get_boto3_service_resource(rh, aws_region, service_name="ec2"):
    """
    Return boto connection to the EC2 in the specified environment's region.
    """
    # get aws wrapper object
    wrapper = rh.get_api_wrapper()

    # get aws client object
    client = wrapper.get_boto3_resource(rh.serviceaccount, rh.servicepasswd, aws_region, service_name)
    
    return client

def run(job, *args, **kwargs):
    resource = kwargs.get('resources').first()
    instance_id = "{{ instances }}"
    device = "{{ device }}"
    
    if device == "/dev/sda1":
        reserved = f"{device} is reserved for root device only. You cannot use the location {device} of an instance to attach volume. kindly check https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/device_naming.html#available-ec2-device-names for available device names"
        return "FAILURE", "Failed to attach volume to instance", reserved


    volume_id = resource.attributes.get(field__name='ebs_volume_id').value
    rh_id = resource.attributes.get(field__name='aws_rh_id').value
    region = resource.attributes.get(field__name='aws_region').value
    handler = AWSHandler.objects.get(id=rh_id)

    ec2 = get_boto3_service_resource(handler, region)

    volume = ec2.Volume(volume_id)

    state = volume.state
    if state != 'available':
        return "FAILURE", f"Can not attach volume to instance since the volume is in '{state.upper()}' state", ""

    set_progress("Connecting to Amazon EC2...")

    try:
        response = volume.attach_to_instance(
            Device=device,
            InstanceId=instance_id
        )
        # wait until the attachment process is complete
        state = response.get('State')
        count = 0
        while state == 'attaching':
            set_progress("Attaching Instance")
            count += 5
            time.sleep(5)
            volume.reload()
            attachments = volume.attachments
            for i in attachments:
                if i["InstanceId"] == instance_id:
                    state = i["State"]
            if count > 3600:
                # Attaching is taking too long
                return "FAILURE", "Failed to attach volume to instance", "Attachment taking too long."
        resource.instance_id = instance_id
        resource.device_name = device
        resource.volume_state = volume.state
        resource.save()

    except ClientError as e:
        return "FAILURE", "Failed to attach volume to instance", f"{e}"

    return "SUCCESS", f"Volume {volume_id} has been successfully attached", ""