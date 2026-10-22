from infrastructure.models import Environment, CustomField
from common.methods import set_progress
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)

def _get_or_create_custom_fields():
    """
    get or create cf as needed
    """
    
    CustomField.objects.get_or_create(
        name=f"mern_stack_server_endpoint",
        defaults={'label': "MERN Stack Server Endpoint", 'type': 'URL',
            'description': 'Used by the AWS EKS blueprint',
            'required': True, 'show_as_attribute': True,'show_on_servers': True }
    )
    
    CustomField.objects.get_or_create(
        name=f"mongodb_connection_string",
        defaults={'label': "MongoDB Connection String", 'type': 'STR',
            'description': 'Used by the AWS EKS blueprint',
            'required': True, 'show_as_attribute': True,'show_on_servers': True }
    )
    
    CustomField.objects.get_or_create(
        name=f"mongodb_server_endpoint",
        defaults={'label': "MongoDB Server Endpoint", 'type': 'URL',
            'description': 'Used by the AWS EKS blueprint',
            'required': True, 'show_as_attribute': True,'show_on_servers': True }
    )
    
def _get_boto_resource_client(env_obj, service_name="ec2"):
    """
    Create boto3 resource client using key and password
    """
	# get aws resource handler object
    rh = env_obj.resource_handler.cast()
    
    # get aws wrapper object
    wrapper = rh.get_api_wrapper()

    # get aws client object
    client = wrapper.get_boto3_resource(rh.serviceaccount, rh.servicepasswd, env_obj.aws_region, service_name)
    
    return client

def get_boto_client(env_obj, service_name="sts"):
    """
    Create boto3 client using key and password
    """
	# get aws resource handler object
    rh = env_obj.resource_handler.cast()

    # get aws wrapper object
    wrapper = rh.get_api_wrapper()

    # get aws client object
    client = wrapper.get_boto3_client(service_name, rh.serviceaccount, rh.servicepasswd, env_obj.aws_region)
    
    return client
    
def _add_security_rule(sg_group_ids, env_obj):
    """
    Add eks port security rule
    """
    ec2_client = _get_boto_resource_client(env_obj, service_name="ec2")
    
    all_http_perm =[
        {
            'FromPort': 80,
            'IpProtocol': 'all',
            'IpRanges': [
                {
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'Allow all trafic'
                },
            ],
            'ToPort': 80,
        }
    ]
    
    http_perm = [{
            'FromPort': 80,
            'IpProtocol': 'tcp',
            'IpRanges': [
                {
                    'CidrIp': '0.0.0.0/0',
                    'Description': 'Enable TCP port'
                },
            ],
            'ToPort': 80,
        }]
        
    for sg_group_id in sg_group_ids:
        security_group = ec2_client.SecurityGroup(sg_group_id)
        
        try:
            # Enable 22 ssh port for InBounds
            security_group.authorize_ingress(IpProtocol="tcp",CidrIp="0.0.0.0/0",FromPort=22,ToPort=22)
        except Exception as err:
            pass
        
        try:
            # enable 80 http port for IP4 for InBounds
            security_group.authorize_ingress(IpProtocol="tcp",CidrIp="0.0.0.0/0",FromPort=80,ToPort=80)
        except Exception as err:
            pass
        
        try:
            # enable all http port for IP4 for InBounds
            security_group.authorize_ingress(IpProtocol="all",CidrIp="0.0.0.0/0",FromPort=80,ToPort=80)
        except Exception as err:
            pass

        try:
            # enable 8004 tcp trafic for InBounds
            security_group.authorize_ingress(IpProtocol="tcp",CidrIp="0.0.0.0/0",FromPort=8004,ToPort=8004)
        except Exception as err:
            pass
        
        try:
            # enable 27017 tcp trafic for InBounds
            security_group.authorize_ingress(IpProtocol="tcp",CidrIp="0.0.0.0/0",FromPort=27017,ToPort=27017)
        except Exception as err:
            pass
        
        try:
            # enable 8081 tcp trafic for InBounds
            security_group.authorize_ingress(IpProtocol="tcp",CidrIp="0.0.0.0/0",FromPort=8081,ToPort=8081)
        except Exception as err:
            pass
        
        try:
            # enable all tcp trafic for OutBounds
            security_group.authorize_egress(IpPermissions=all_http_perm)
        except Exception as err:
            pass

        try:
            # enable 80 http trafic for OutBounds
            security_group.authorize_egress(IpPermissions=http_perm)
        except Exception as err:
            pass

def _get_ec2_instance_security_group_ids(ec2_instance_ids, env_obj):
    # get ec2 boto3 client
    client = get_boto_client(env_obj, service_name="ec2")
    
    # get ec2 instance details
    ec2_rsp = client.describe_instances(InstanceIds=ec2_instance_ids)
    
    sg_group_ids = [xx['GroupId'] for item_obj in  ec2_rsp['Reservations'] for ec2_inst in item_obj['Instances'] for xx in ec2_inst['SecurityGroups']]
    
    return sg_group_ids
    
def run(job, *args, **kwargs):
    set_progress("Starting Provision of EC2 Security Group Rules...")

    # get resource object
    resource = job.resource_set.first()
    
    # get or create custom fields
    _get_or_create_custom_fields()
    
    server_obj = resource.server_set.all()[0]
    
    # environment model object
    env_obj = Environment.objects.get(id=server_obj.environment_id)
    
    try:
        # get ec2 instance security group id
        sg_group_ids = _get_ec2_instance_security_group_ids([server_obj.resource_handler_svr_id], env_obj)
        
        # add esk port security group
        _add_security_rule(sg_group_ids, env_obj)
    except Exception as err:
        logger.error(err)
        return "FAILURE", f"{err}", ""
    
    resource.mern_stack_server_endpoint = f"http://{server_obj.ip}"
    resource.mongodb_connection_string = f"mongodb://{server_obj.ip}:27017/cloudbolt"
    resource.mongodb_server_endpoint = f"http://{server_obj.ip}:8081/db/cloudbolt/"
    resource.save()
    
    server_obj.mern_stack_server_endpoint = f"http://{server_obj.ip}"
    server_obj.mongodb_connection_string = f"mongodb://{server_obj.ip}:27017/cloudbolt"
    server_obj.mongodb_server_endpoint = f"http://{server_obj.ip}:8081/db/cloudbolt/"
    server_obj.save()
    
    return "SUCCESS", "Security Group Inbound Rules added successfully.", ""