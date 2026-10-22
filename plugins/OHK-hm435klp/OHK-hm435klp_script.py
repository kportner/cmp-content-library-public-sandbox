from infrastructure.models import Environment
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler


def connect_to_elasticache(env):
    """
    Return boto connection to the elasticache in the specified environment's region.
    """
    rh: AWSHandler = env.resource_handler.cast()
    return rh.get_boto3_client(env.aws_region, 'elasticache')

def run(resource, *args, **kwargs):
    if resource.env_id:
        env = Environment.objects.get(id=resource.env_id)
    else:
        env = Environment.objects.filter(aws_region=resource.aws_region)[0]
    client = connect_to_elasticache(env)

    try:
        client.delete_cache_cluster(
            CacheClusterId=resource.name)

        response = client.describe_cache_clusters(
            CacheClusterId=resource.name)
        set_progress(f"{response}")
    
    except Exception as error:
        return "FAILURE", "", f"{ error }"

    return "SUCCESS", "The cache is being deleted", ""