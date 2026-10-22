"""
This CloudBolt plug-in creates Regional AWS Elastic File System in a provided region.
"""
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler
from resources.models import Resource
from infrastructure.models import CustomField
import ast,time,boto3

def get_or_create_custom_fields():
    CustomField.objects.get_or_create(
        name='efs_id',
        defaults={
            "label": 'File System ID',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the HA Architecture parent blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='file_system_id',
        defaults={
            "label": 'File System ID',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the AWS Regional Elastic File System blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='file_system_arn',
        defaults={
            "label": 'File System ARN',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the AWS Regional Elastic File System blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='zone_mount_target_pair',
        defaults={
            "label": 'Zonewise Mount Target ID',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the AWS Regional Elastic File System blueprint'
        }
    )
    
def get_boto3_efs_client(**kwargs):
    rh = kwargs.get('resource_handler')
    region = kwargs.get('region')
    wrapper = rh.get_api_wrapper()
    return wrapper.get_boto3_client('efs', rh.serviceaccount, rh.servicepasswd , region)
    
def run(job, *args, **kwargs):
    resource = kwargs.get('resource')
    get_or_create_custom_fields()

    if resource.parent_resource_id:
        parent_resource = Resource.objects.get(id = resource.parent_resource_id)
        base_name = parent_resource.base_name
        rh = AWSHandler.objects.get(id = parent_resource.aws_rh_id)
        vpc_subnet_sg_dict = ast.literal_eval(parent_resource.vpc_subnet_structure[-1])     
        #e.g. vpc_subnet_sg_dict = {'ap-south-1': {'VPC': ['vpc-01fe7eda1114e7e03', '172.66.0.0/16', 'sg-024a3593c9c646404'], 'Subnet': [('subnet-0e1dc928a46ea6508', '172.66.0.0/18', 'ap-south-1a'), ('subnet-015290f2051562c4e', '172.66.64.0/18', 'ap-south-1b')]}}
        region = parent_resource.aws_region_ha
        set_progress('VPC details are retrieved as {}'.format(vpc_subnet_sg_dict))
        vpc_id = vpc_subnet_sg_dict[region]['VPC'][0]
        security_group_id = vpc_subnet_sg_dict[region]['VPC'][-1]
        az_subnet_list = []
        for subnet in vpc_subnet_sg_dict[region]['Subnet']:
            az_subnet_list.append((subnet[-1],subnet[0]))      # for example [('ap-south-1a','subnet-0e1dc928a46ea6508'),('ap-south-1b','subnet-015290f2051562c4e')]
            
        efs_client  = get_boto3_efs_client(resource_handler=rh,region=region)
        
        set_progress(f"Creating regional file system in region {region}")
        efs_resp = efs_client.create_file_system(
            CreationToken=f"HA_EFS_{base_name}",
            Encrypted=True,
            PerformanceMode='generalPurpose',
            Tags=[
                {
                    'Key': 'Name',
                    'Value': f"FS-{base_name}",
                },
            ],
            )
        elastic_file_system_id = efs_resp['FileSystemId']
        elastic_file_system_arn = efs_resp['FileSystemArn']
        set_progress(f"Created regional file system {elastic_file_system_id} in region {region}")
        
        parent_resource.efs_id = elastic_file_system_id
        parent_resource.save()
        flag  = True
        while flag:
            set_progress(f"Waiting for regional file system {elastic_file_system_id} in region {region} to become available")
            time.sleep(3)
            fs_resp = efs_client.describe_file_systems(FileSystemId=elastic_file_system_id)
            if fs_resp['FileSystems'][0]['LifeCycleState'] == 'available':
                set_progress(f"Regional file system {elastic_file_system_id} in region {region} is now available")
                flag = False
        zone_mount_target_list = []
        for az_subnet in az_subnet_list:
            set_progress(f"Creating Mount Target in zone {az_subnet[0]}")
            mt_resp = efs_client.create_mount_target(
                FileSystemId=elastic_file_system_id,
                SubnetId=az_subnet[-1],
                SecurityGroups=[security_group_id,]
            )
            mount_target_id = mt_resp['MountTargetId']
            zone_mount_target_list.append(f"{az_subnet[0]}:{mount_target_id}")
    set_progress(f"Waiting for 90 Seconds...This wait lets the DNS records propagate fully in the AWS Region {region} where the file system is.")    #recommended by Amazon
    time.sleep(90)
    resource.file_system_id = elastic_file_system_id
    resource.file_system_arn = elastic_file_system_arn
    resource.zone_mount_target_pair = ",".join(zone_mount_target_list)
    resource.save()
    return "SUCCESS", "AWS Regional file system and mount targets are created successfully", ""