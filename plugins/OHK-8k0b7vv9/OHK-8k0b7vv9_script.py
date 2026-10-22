"""
Teardown service item action for HA ARCHITECTURE.
"""
import boto3,time,ast,os
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler
from infrastructure.models import Environment
from utilities.logger import ThreadLogger
from django.conf import settings

logger = ThreadLogger(__name__)

def run(job, logger=None, **kwargs):
    resource = kwargs.pop('resources').first()
    proserv_path = getattr(settings, "PROSERV_DIR", None)

    set_progress(f"HA_Architecture Delete plugin running for resource: {resource}")
    logger.info(f"HA_Architecture Delete plugin running for resource: {resource}")

    cluster_identifier = resource.get_cf_values_as_dict().get('ha_dbcluster_identifier')
    region = resource.get_cf_values_as_dict().get('aws_region_ha') 
    rh_id = resource.get_cf_values_as_dict().get('aws_rh_id')   
    if rh_id:
        rh = AWSHandler.objects.get(id=rh_id)
    
        set_progress('Connecting to Amazon RDS')
    
        rds = boto3.client('rds',region_name=region,aws_access_key_id=rh.serviceaccount,aws_secret_access_key=rh.servicepasswd)

    # Find the cluster and it's instances
    if cluster_identifier:
        try:
            response = rds.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
        except rds.exceptions.DBClusterNotFoundFault:
            set_progress(f'RDS DB cluster {cluster_identifier} is already deleted or not found...')
            logger.info(f'RDS DB cluster {cluster_identifier} is already deleted or not found...')
        else:    
            clust = response['DBClusters'][0]
            if clust['Status'] != 'available':
                set_progress(f"RDS Aurora Db Cluster {cluster_identifier} is in-process state of '{clust['Status']}', try after process state get available.")
                logger.info(f"RDS Aurora Db Cluster {cluster_identifier} is in-process state of '{clust['Status']}', try after process state get available.")
                
            instances_to_delete = [inst['DBInstanceIdentifier'] for inst in clust['DBClusterMembers']]
        
            set_progress("Instance(s) to be deleted: %s" % instances_to_delete)
        
            for inst_id in instances_to_delete:
                set_progress('Deleting AWS database instance "{}"'.format(inst_id))
                response = rds.delete_db_instance(
                    DBInstanceIdentifier=inst_id,
                    SkipFinalSnapshot=True,
                )
        
            set_progress('Deleting AWS Aurora database cluster "{}"'.format(cluster_identifier))
            response = rds.delete_db_cluster(
                DBClusterIdentifier=cluster_identifier,
                SkipFinalSnapshot=True,
            )
        
            set_progress('Waiting for deletions to finalize...')
        
            while instances_to_delete:
                time.sleep(5)
                for inst_id in instances_to_delete:
                    try:
                        response = rds.describe_db_instances(DBInstanceIdentifier=inst_id)
                    except rds.exceptions.DBInstanceNotFoundFault:
                        # Database instance is finally deleted
                        set_progress('Database instance %s is now deleted' % inst_id)
                        instances_to_delete.remove(inst_id)
                    else:
                        db_instance = response['DBInstances'][0]
                        status = db_instance['DBInstanceStatus']
                        set_progress('Status of the database instance %s is: %s' % (inst_id, status))
        
            is_db_cluster_active = True
            while is_db_cluster_active:
                time.sleep(5)
                try:
                    response = rds.describe_db_clusters(DBClusterIdentifier=cluster_identifier)    
                except rds.exceptions.DBClusterNotFoundFault:
                    is_db_cluster_active = False
                    set_progress(f'Deletion of RDS DB cluster {cluster_identifier} is completed...')    
                else:
                    set_progress(f'Deletion of RDS DB cluster {cluster_identifier} is in progress, waiting...')    
                
    # Deleting DB Subnet Group
    time.sleep(5)  #For precaution
    db_subnet_group_name = resource.get_cf_values_as_dict().get('ha_db_subnet_group')
    if db_subnet_group_name:
        try:
            response = rds.delete_db_subnet_group(DBSubnetGroupName=db_subnet_group_name)
        except rds.exceptions.DBSubnetGroupNotFoundFault:
            set_progress(f"DB Subnet group '{db_subnet_group_name}' is already deleted or not found...")
            logger.info(f"DB Subnet group '{db_subnet_group_name}' is already deleted or not found...")
        else:
            set_progress(f"DB Subnet group '{db_subnet_group_name} is deleted successfully...")
            logger.info(f"DB Subnet group '{db_subnet_group_name} is deleted successfully...")
    
    # Deleting Application load balancer
    elbv = boto3.client('elbv2',region_name=region,aws_access_key_id=rh.serviceaccount,aws_secret_access_key=rh.servicepasswd)   
    load_balancer_arn = resource.get_cf_values_as_dict().get('ha_load_balancer_arn')
    load_balancer_Name = resource.get_cf_values_as_dict().get('ha_load_balancer_name')
    if load_balancer_arn:
        try:
            response = elbv.delete_load_balancer(LoadBalancerArn=load_balancer_arn)
        except:    #elbv.exceptions.LoadBalancerNotFoundException:
            set_progress(f'Application Load Balancer {load_balancer_Name} is already deleted or not found...')
            logger.info(f'Application Load Balancer {load_balancer_Name} is already deleted or not found...')
        else:
            set_progress(f'Application Load Balancer {load_balancer_Name} is deleted successfully...')
            logger.info(f'Application Load Balancer {load_balancer_Name} is deleted successfully...')
        time.sleep(5)
        is_load_balancer_active = True
        while is_load_balancer_active:
            time.sleep(5)
            try:
                response = elbv.describe_load_balancers(LoadBalancerArns=[load_balancer_arn])    
            except elbv.exceptions.LoadBalancerNotFoundException:
                is_load_balancer_active = False
                set_progress(f'Deletion of load balancer {load_balancer_Name} is completed...')    
            else:
                set_progress(f'Deletion of load balancer {load_balancer_Name} is in progress, waiting...')   

    
        
    # Deleting Elastic File System
    efs = boto3.client('efs',region_name=region,aws_access_key_id=rh.serviceaccount,aws_secret_access_key=rh.servicepasswd)
    efs_id = resource.get_cf_values_as_dict().get('efs_id')
    if efs_id:
        try:
            response = efs.describe_mount_targets(FileSystemId=efs_id)
        except:
            set_progress(f'Elastic File System with ID {efs_id} is already deleted or does not exist...')
            logger.info(f'Elastic File System with ID {efs_id} is already deleted or does not exist...')
        else:
            for mount_target in response['MountTargets']:
                try:
                    efs.delete_mount_target(MountTargetId=mount_target['MountTargetId'])
                except efs.exceptions.MountTargetNotFound:
                    set_progress(f"Mount Target {mount_target['MountTargetId']} is already deleted or not found...")
                    logger.info(f"Mount Target {mount_target['MountTargetId']} is already deleted or not found...")
                else:
                    set_progress(f"Mount Target {mount_target['MountTargetId']} is deleted successfully...")
                    logger.info(f"Mount Target {mount_target['MountTargetId']} is deleted successfully...")
            
            # Deletion of Mount Target takes time, Make sure they all are completely deleted before deleting EFS File System
            
            All_mount_targets_not_deleted = True
            while All_mount_targets_not_deleted:
                time.sleep(5)
                mt_resp = efs.describe_mount_targets(FileSystemId=efs_id)   # Not putting this in "try" block as we are already in "else" block
                if len(mt_resp['MountTargets']) == 0:
                    set_progress(f"Deletion of all Mount Targets of EFS '{efs_id}' is completed successfully...")
                    All_mount_targets_not_deleted = False
        
        try:
            response = efs.delete_file_system(FileSystemId=efs_id)
        except efs.exceptions.FileSystemNotFound:
            set_progress(f'Elastic File System with ID {efs_id} is already deleted or not found...')
            logger.info(f'Elastic File System with ID {efs_id} is already deleted or not found...')
        else:
            set_progress(f'Elastic File System with ID {efs_id} is deleted successfully...')
            logger.info(f'Elastic File System with ID {efs_id} is deleted successfully...')
    
    # Deleting Autoscaling Group
    
    autoscaling_group_name = resource.get_cf_values_as_dict().get('auto_scaling_group_name')
    autoscaling = boto3.client('autoscaling',region_name=region,aws_access_key_id=rh.serviceaccount,aws_secret_access_key=rh.servicepasswd)
    if autoscaling_group_name:
        try:
            response = autoscaling.delete_auto_scaling_group(AutoScalingGroupName=autoscaling_group_name,ForceDelete=True)
        except:
            set_progress(f"Auto scaling group '{autoscaling_group_name}' is already deleted or not found...")
            logger.info(f"Auto scaling group '{autoscaling_group_name}' is already deleted or not found...")
        else:
            set_progress(f"Auto scaling group '{autoscaling_group_name}' is being deleted...")
            logger.info(f"Auto scaling group '{autoscaling_group_name}' is being deleted...")
        
        # Making sure all instances under auto scaling group are TERMINATED
        
        response = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[autoscaling_group_name])
        if response['AutoScalingGroups']:
            status = response['AutoScalingGroups'][0]['Status'] 
        else:
            set_progress(f"Auto scaling group '{autoscaling_group_name}' is deleted successfully...")
            status = "deleted"
            
        while status == 'Delete in progress':
            time.sleep(5)
            response = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[autoscaling_group_name])
            if response['AutoScalingGroups']:
                status = response['AutoScalingGroups'][0]['Status']
                set_progress(f"Auto scaling group '{autoscaling_group_name}' is being deleted...")
            else:
                set_progress(f"All instances in Auto scaling group '{autoscaling_group_name}' are terminated...")
                status = "deleted"
        
    # Delete Launch Template
    
    launch_template_id = resource.get_cf_values_as_dict().get('launch_template_id') 
    ec2_client = boto3.client('ec2',region_name=region,aws_access_key_id=rh.serviceaccount,aws_secret_access_key=rh.servicepasswd)
    if launch_template_id:
        try:
            response = ec2_client.delete_launch_template(LaunchTemplateId=launch_template_id)
        except:
            set_progress(f"Launch Template '{launch_template_id}' is already deleted or not found...")
            logger.info(f"Launch Template '{launch_template_id}' is already deleted or not found...")
        else:
            set_progress(f"Launch Template '{launch_template_id}' is deleted successfully...")
            logger.info(f"Launch Template '{launch_template_id}' is deleted successfully...")
    
    #Delete Target Group
    target_group_arn = resource.get_cf_values_as_dict().get('target_group_arn')
    if target_group_arn:
        try:
            elbv.delete_target_group(TargetGroupArn=target_group_arn)
        except elbv.exceptions.ResourceInUseException:
            set_progress(f"Target Group Arn:'{target_group_arn}' is being used by some other resource thus can not be deleted...")
            logger.info(f"Target Group Arn:'{target_group_arn}' is being used by some other resource thus can not be deleted...")
        else:
            set_progress(f"Target Group Arn:'{target_group_arn}' is deleted successfully...")
            logger.info(f"Target Group Arn:'{target_group_arn}' is deleted successfully...")
        time.sleep(5)
        
    # Delete Key-Pair   
    
    ec2_key_name = resource.get_cf_values_as_dict().get('ec2_key_name')
    if ec2_key_name:
        try:
            response = ec2_client.delete_key_pair(KeyName=ec2_key_name)
        except:
            set_progress(f"EC2 key pair '{ec2_key_name}' is already deleted or not found...")
            logger.info(f"EC2 key pair '{ec2_key_name}' is already deleted or not found...")
        else:
            set_progress(f"EC2 key pair '{ec2_key_name}' is deleted successfully...")
            logger.info(f"EC2 key pair '{ec2_key_name}' is deleted successfully...")
    
        # Delete PEM file stored in Proserv directory
        pem_file_path = f"{proserv_path}{ec2_key_name}.pem"
        if os.path.exists(pem_file_path):
            try:
                os.remove(pem_file_path)
                set_progress(f"'{pem_file_path}' file deleted successfully...!")
                logger.info(f"'{pem_file_path}' file deleted successfully...!")
            except OSError:
                set_progress(f"'{pem_file_path}' file can't be deleted...!")
                logger.info(f"'{pem_file_path}' file can't be deleted...!")            
    
    # Delete Security Group
    
    vpc_subnet_sg_dict = ast.literal_eval(resource.vpc_subnet_structure[-1])
    security_group_id = vpc_subnet_sg_dict[region]['VPC'][-1]
    if security_group_id:
        try:
            response = ec2_client.delete_security_group(GroupId=security_group_id)
        except:
            set_progress(f"Security Group '{security_group_id}' is already deleted or not found...")
            logger.info(f"Security Group '{security_group_id}' is already    deleted or not found...")
        else:
            set_progress(f"Security Group '{security_group_id}' is deleted successfully...")
            logger.info(f"Security Group '{security_group_id}' is deleted successfully...")
    
    # Delete VPC Subnets
        
    vpc_id = vpc_subnet_sg_dict[region]['VPC'][0]
    subnet_id_list = [subnet[0] for subnet in vpc_subnet_sg_dict[region]['Subnet']]
    is_new_vpc_created = True if resource.get_cf_values_as_dict().get('vpc_selection')[-1]=='Not Selected Any' else False
    # is_new_vpc_created = True means separate new VPC is created for HA and False means existing VPC is used for HA
    ec2_resource = boto3.resource('ec2',region_name=region,aws_access_key_id=rh.serviceaccount,aws_secret_access_key=rh.servicepasswd)
    vpc_resource = ec2_resource.Vpc(vpc_id)
    
    for subnet_id in subnet_id_list:
        try:
            ec2_client.delete_subnet(SubnetId=subnet_id)
        except:
            set_progress(f"Subnet '{subnet_id}' is already deleted or not found...")
            logger.info(f"Subnet '{subnet_id}' is already deleted or not found...")
        else:
            set_progress(f"Subnet '{subnet_id}' is deleted successfully...")
            logger.info(f"Subnet '{subnet_id}' is deleted successfully...")
        
    # Delete VPC
    if is_new_vpc_created:  # Delete VPC only if it is created
        try:
            response = ec2_client.describe_vpcs(VpcIds=[vpc_id])
        except:
            set_progress(f"VPC '{vpc_id}' is already deleted or not found...")
            logger.info(f"VPC '{vpc_id}' is already deleted or not found...")  
        else:
            if response['Vpcs'][0]['IsDefault']:  # Avoid deletion of VPC if it is set to Default
                set_progress(f"VPC '{vpc_id}' is default VPC so skipping delete operation...")
                logger.info(f"VPC '{vpc_id}' is default VPC so skipping delete operation...")
            else:
                all_vpc = ec2_client.describe_vpcs()
                if len(all_vpc['Vpcs']) <= 1:  # Avoid deletion of VPC if it is the only VPC available in the region
                    set_progress(f"VPC '{vpc_id}' is the only VPC available in region {region} so skipping delete operation...")
                    logger.info(f"VPC '{vpc_id}' is the only VPC available in region {region} so skipping delete operation...")
                else: 
                    try:
                        # Delete internet gateway if attached #####################################
                        
                        igws = vpc_resource.internet_gateways.all()
                        if igws:
                            for igw in igws:
                                try:
                                    igw.detach_from_vpc(VpcId=vpc_id)
                                    igw.delete()
                                except:
                                    set_progress(f"Internet Gateway '{igw.id}' is already deleted or not found...")
                                    logger.info(f"Internet Gateway '{igw.id}' is already deleted or not found...")
                                else:
                                    set_progress(f"Internet Gateway '{igw.id}' is deleted successfully...")
                                    logger.info(f"Internet Gateway '{igw.id}' is deleted successfully...")
                        
                        # Delete associated route table #####################################
                        
                        rtbs = vpc_resource.route_tables.all()
                        if rtbs:
                            for rtb in rtbs:
                                route_table = ec2_resource.RouteTable(rtb.id)
                                try:
                                    route_table.delete()
                                except:
                                    set_progress(f"Route table '{rtb.id}' is already deleted or not found or it is a main route table...")
                                    logger.info(f"Route table '{rtb.id}' is already deleted or not found or it is a main route table...")
                                else:
                                    set_progress(f"Route table '{rtb.id}' is deleted successfully...")
                                    logger.info(f"Route table '{rtb.id}' is deleted successfully...")
                                    
                        # Delete Network ACLs associated with VPC #####################################
                        
                        acls = vpc_resource.network_acls.all()
                        if acls:
                            for acl in acls:
                                if acl.is_default:
                                    continue
                                else:
                                    try:
                                        acl.delete()
                                    except:
                                        set_progress(f"Network ACL '{acl.id}' is already deleted or not found...")
                                        logger.info(f"Network ACL '{acl.id}' is already deleted or not found...")
                                    else:
                                        set_progress(f"Network ACL '{acl.id}' is deleted successfully...")
                                        logger.info(f"Network ACL '{acl.id}' is deleted successfully...")
    
                        # Finally we can delete VPC
                        
                        #####################################
                        ec2_client.delete_vpc(VpcId=vpc_id)
                        #####################################
                    except:
                        set_progress(f"VPC '{vpc_id}' has dependencies and cannot be deleted, first delete all associated resources which are using this VPC....")
                        logger.info(f"VPC '{vpc_id}' has dependencies and cannot be deleted, first delete all associated resources which are using this VPC...")
                    else:
                        set_progress(f"VPC '{vpc_id}' is deleted successfully...")
                        logger.info(f"VPC '{vpc_id}' is deleted successfully...")
                        # delete environment created after successfully deleteing VPC
                        try:
                            env_associated_with_vpc = Environment.objects.get(vpc_id = vpc_id)
                        except:
                            set_progress(f"Environment associated with VPC '{vpc_id}' is already deleted...")
                        else:
                            env_associated_with_vpc.delete()
                            set_progress(f"Environment associated with VPC '{vpc_id}' is deleted successfully...")
    
    else:
        set_progress(f"VPC '{vpc_id}' is not created but it was existing VPC , so skipping deletion of VPC....")
        logger.info(f"VPC '{vpc_id}' is not created but it was existing VPC , so skipping deletion of VPC....")
        
    
    # Delete ACM certificate if it is in "PENDING VALIDATION" status
    # Not deleting ACM certificate with status "ISSUED" as they can be reused
    
    acm_certificate_arn = resource.get_cf_values_as_dict().get('ha_acm_certificate_arn')
    if acm_certificate_arn:
        acm_client = boto3.client('acm',region_name=region,aws_access_key_id=rh.serviceaccount,aws_secret_access_key=rh.servicepasswd)
        try:
            acm_cert_details = acm_client.describe_certificate(CertificateArn=acm_certificate_arn)
        except:
            set_progress(f"ACM Certificate is already deleted or not found...")
        else:
            if acm_cert_details['Certificate']['Status'] == "PENDING_VALIDATION":
                try:
                    acm_client.delete_certificate(CertificateArn=acm_certificate_arn)
                except:
                    set_progress(f"ACM Certificate is already deleted or not found...")
                else:
                    set_progress(f"ACM Certificate is deleted successfully...")
    
    # Finally deleting route53 record entry of Load Balancer DNS
    
    route53_rh_id = resource.get_cf_values_as_dict().get('aws_rh_id_for_hosted_zone')
    if route53_rh_id:
        route53_rh = AWSHandler.objects.get(id=route53_rh_id)
        route53 = boto3.client('route53',region_name=region,aws_access_key_id=route53_rh.serviceaccount,aws_secret_access_key=route53_rh.servicepasswd)
        hosted_zone_id = resource.get_cf_values_as_dict().get('hosted_zone_id')
        base_name = resource.get_cf_values_as_dict().get('base_name').lower()
        try:
            response = route53.list_resource_record_sets(HostedZoneId=hosted_zone_id)
        except:
            set_progress(f"Hosted Zone '{hosted_zone_id}' is already deleted or not found...")
            logger.info(f"Hosted Zone '{hosted_zone_id}' is already deleted or not found...")
        else:
            a_record_already_deleted = True
            for record in response['ResourceRecordSets']:
                if base_name in record['Name'] and record['Type'] not in ["NS","SOA","CNAME"]:
                    a_record_already_deleted = False
                    batch = {
                        'Comment': 'deleted by CloudBolt',
                        'Changes': [
                            {
                                'Action': "DELETE",
                                'ResourceRecordSet': {
                                    'Name': record['Name'],
                                    'Type': record['Type'],
                                    'AliasTarget':record['AliasTarget']
                                }
                            },
                        ]
                    }
            if a_record_already_deleted:
                set_progress(f"Load balancer DNS Record in Route53 is already deleted...")
            else:
                try:
                    route53.change_resource_record_sets(HostedZoneId=hosted_zone_id,ChangeBatch=batch)
                except:
                    set_progress(f"Load balancer DNS Record in Route53 is already deleted or not found...")
                    logger.info(f"Load balancer DNS Record in Route53 is already deleted or not found...")
                else:
                    set_progress(f"Load balancer DNS Record in Route53 is deleted successfully...")
                    logger.info(f"Load balancer DNS Record in Route53 is deleted successfully...")
    
    return 'SUCCESS', f"All the resources created for HA Architecture with base name '{resource.base_name}' are deleted successfully", ''