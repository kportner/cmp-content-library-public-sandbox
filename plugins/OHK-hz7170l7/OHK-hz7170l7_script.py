from infrastructure.models import Environment
from resourcehandlers.aws.models import AWSHandler


def _boto3_ecs_client(env_obj, service_name="ecs"):
    """
    Return boto connection to the ecs in the specified environment's region.
    """
    rh: AWSHandler = env_obj.resource_handler.cast()

    client = rh.get_boto3_client(env_obj.aws_region, service_name)
    return client

def run(resource, *args, **kwargs):
    # fetch enviroment model object
    env_obj = Environment.objects.get(id=resource.env_id)
    
    # get boto3 ecs client
    client = _boto3_ecs_client(env_obj)
    
    container_services = client.list_services(cluster=resource.cluster_name)['serviceArns']
    
    if container_services:
        return "FAILURE", "", f"Cluster {resource.cluster_name} have active container services: {container_services}, please delete it first"

    
    tasks = client.list_tasks(cluster=resource.cluster_name)['taskArns']
    
    if tasks:
        return "FAILURE", "", f"Cluster {resource.cluster_name} have active tasks: {tasks}, please delete it first"

    try:
        client.delete_cluster(
            cluster=resource.cluster_name
        )
    except Exception as error:
        return "FAILURE", "", f"{ error }"

    return "SUCCESS", "AWS ECS cluster deleted successfully", ""