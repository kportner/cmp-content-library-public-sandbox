"""
This is a CloudBolt plug-in creates VPC, one subnet under each available zone selected, 
and one security group with all inbound rules required for HA deployment.
"""
from common.methods import set_progress
from resources.models import Resource
from servicecatalog.models import BlueprintServiceItem
from resourcehandlers.aws.models import AWSHandler
from infrastructure.models import Environment,CustomField
from accounts.models import Group
import boto3,time,itertools

def get_or_create_custom_fields():
    CustomField.objects.get_or_create(
        name='vpc',
        defaults={
            "label": 'VPC Details',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the VPC blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='subnet_list',
        defaults={
            "label": 'Subnet id in VPC',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the VPC blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='tenancy',
        defaults={
            "label": 'Tenancy',
            "type": 'STR',
            'show_as_attribute': True,
            "description": 'Used by the VPC blueprint'
        }
    )
    CustomField.objects.get_or_create(
        name='vpc_subnet_structure',
        defaults={
            "label": 'VPC Subnet Structure dict',
            "type": 'TUP',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture blueprint'
        }
    )

def create_boto3_client(service_name="ec2",**kwargs):
    rh_id = kwargs.get("rh_id")
    aws_region = kwargs.get("aws_region")
    rh = AWSHandler.objects.get(id=rh_id)
    wrapper = rh.get_api_wrapper()
    # return boto3.client('ec2',aws_access_key_id=rh.serviceaccount,aws_secret_access_key=rh.servicepasswd,region_name=aws_region)
    return wrapper.get_boto3_client(service_name, rh.serviceaccount, rh.servicepasswd , aws_region)
    
def get_available_zones(**kwargs):
    """ This function will return all the zones available in region passed in 
        kwargs as 'region' with the help of boto3 client created with resource handler
        provided in kwargs as 'resource_handler_id'
    """
    region = kwargs.get('region')
    rh_id = kwargs.get('resource_handler_id')
    rh = AWSHandler.objects.get(id = rh_id)
    client = create_boto3_client(rh_id = rh.id,aws_region = region)
    try:
        response = client.describe_availability_zones(
            Filters=[
                {
                    'Name': 'region-name',
                    'Values': [region,]
                }])
    except:
        return []
    zone_list = [ zone['ZoneName'] for zone in response['AvailabilityZones']]
    return zone_list
    
def add_name_to_resource(**kwargs):
    """
        This function adds tag 'name' with provided value to resource
    """
    client = kwargs.get('client')
    res_id = str(kwargs.get('resource_id'))
    res_name = kwargs.get('resource_name')
    response = client.create_tags(
    Resources=[res_id,],
    Tags=[ 
        {
            'Key': 'Name',
            'Value': res_name
        },
    ]
    )
    return response
    
def create_vpc_subnet(**kwargs):
    """
        This function creates subnet in a provided zone
    """
    client = kwargs.get("client")
    zone = kwargs.get("zone")
    cidr_block = kwargs.get("subnet_cidr")
    vpc_id = kwargs.get("VPD_ID")
    try:
        response = client.create_subnet(
            AvailabilityZone=zone,
            CidrBlock=cidr_block,
            VpcId=vpc_id
        )
    except:
        return "NA"
    else:
        subnet_dict = response['Subnet']
        subnet_id = subnet_dict['SubnetId']
        response_modify_subnet_attribute = client.modify_subnet_attribute(MapPublicIpOnLaunch={'Value': True },SubnetId=subnet_id)  #to get instances launched in this subnet a public IP
        set_progress('"{}" subnet is created in zone "{}"'.format(subnet_id,zone))
        return subnet_id

def create_new_VPC(**kwargs):
    """ 
        This function creates new VPC in a provided region for which user have not
        selected any existing VPC
    """
    region = kwargs.get('region')
    vpc_cidr_block = kwargs.get('vpc_cidr')
    tenancy = kwargs.get('Tenancy')
    client = kwargs.get('Client')
    response = client.create_vpc(
        CidrBlock=vpc_cidr_block,
        AmazonProvidedIpv6CidrBlock=False,
        InstanceTenancy=tenancy,
    )
    vpc_dict = response['Vpc']
    vpc_id = vpc_dict['VpcId']
    vpc_cidr = vpc_dict['CidrBlock']
    set_progress('"{}" VPC is created in region "{}"'.format(vpc_id,region))
    vpc_mod_resp = client.modify_vpc_attribute( EnableDnsHostnames={'Value': True},VpcId=vpc_id,)

    return [vpc_cidr,vpc_id]

def create_subnet_ip_list(**kwargs):
    """ 
        This function produces number of subnet CIDR for respective VPC equals 
        number of zones selected for that particular region
    """
    vpc_cidr = kwargs.get("vpc_cidr")
    number_of_zones_selected_in_region = kwargs.get("Number_of_zones_selected_in_region")
    no_of_subnets_in_vpc = kwargs.get("no_of_subnets_in_vpc")
    existing_subnet_cidr_list = kwargs.get("existing_subnet_cidr_list")
    bit_to_subnet_count = {1:2,2:4,3:8,4:16,5:32,6:64,7:128,8:256}  # key:value here "key" is number of subnet bit and "value" refers to how many subnets can be created 
    subnetbits_list = [k for k in bit_to_subnet_count.keys() if bit_to_subnet_count[k]>=number_of_zones_selected_in_region+no_of_subnets_in_vpc]
    net_mask = int(vpc_cidr.split("/")[-1])   # Between 16 to 28
    subnet_bit = subnetbits_list[1] if len(subnetbits_list)>1 else subnetbits_list[0]
    subnet_bit = subnet_bit+1 if (net_mask+subnet_bit)<24 and (net_mask+subnet_bit)%2!=0 else subnet_bit   # Just to make it even e.g. if net_mask+subnet_bit=19 will make it 20
    subnet_bit = 28-net_mask if (net_mask+subnet_bit) > 28 else subnet_bit   #Block can not exceed 28
    #bit_combination = {1:['0','1'],2:['00','01','10','11'],3:['001','010','100','011','101','110','111']}  #static way limited to subnet_bit<=3
    bit_combination_list = ["".join(item) for item in list(map(list,itertools.product(['0','1'], repeat=subnet_bit))) if int("".join(item)) != 0]  #dynamic way
    #subnet_byte_list = []
    vpc_ip_list = vpc_cidr.split("/")[0].split('.')   #e.g. ['172', '64', '0', '0']
    vpc_binary_ip_32_bit = ""    # It will become '10101100010000000000000000000000' like this
    for vpc_byte in vpc_ip_list:
        byte_bin = ""
        byte_bin = bin(int(vpc_byte)).split("b")[-1]
        byte_bin = "0"*(8-len(byte_bin))+byte_bin
        vpc_binary_ip_32_bit += byte_bin
    subnet_cidr_list = []
    for combination in bit_combination_list:
        sub_ip = ""
        sub_ip = vpc_binary_ip_32_bit[:net_mask]+combination+"0"*(32-(net_mask+subnet_bit))
        sub_cidr = f"{int(sub_ip[:8],2)}.{int(sub_ip[8:16],2)}.{int(sub_ip[16:24],2)}.{int(sub_ip[24:],2)}/{net_mask+subnet_bit}"
        subnet_cidr_list.append(sub_cidr)
    
    final_subnet_cidr_list = [subnet_cidr for subnet_cidr in subnet_cidr_list if subnet_cidr.split("/")[0] not in existing_subnet_cidr_list]
    #set_progress('eligible subnet CIDR list created :- "{}"'.format(subnet_cidr_list))  # For testing only
    #set_progress('final subnet CIDR list created after skipping invalid subnet IP :- "{}"'.format(final_subnet_cidr_list))  # For testing only
    
    return final_subnet_cidr_list
    

def create_instance_location_dict(instance_locations=None,parent_resource=None,**kwargs):
    instance_locations_dict = {}
    instance_locations_list = []
    if parent_resource:
        instance_locations_list = parent_resource.aws_zone_region_list_ha[1].split(",")
    if instance_locations:
        instance_locations_list = instance_locations
    for ele in instance_locations_list:
     temp = []
     temp = ele.split(")")[0].split("(")  
     if temp[1] in instance_locations_dict.keys():
         instance_locations_dict[temp[1]].append(temp[0])
     else:
         instance_locations_dict[temp[1]] = [temp[0]]
    return instance_locations_dict

def check_vpc_cidr_in_region(**kwargs):
    """ This function checks if selected VPC CIDR for new VPC already exist in given region or not
        If not then it will return True maens we can use it or else False
    """
    vpc_cidr = kwargs.get("vpc_cidr")
    existing_vpc_cidr_list = kwargs.get("existing_vpc_cidr_list")
    existing_vpc_cidr_list = [vpc.split("/")[0] for vpc in existing_vpc_cidr_list]
    if vpc_cidr.split("/")[0] not in existing_vpc_cidr_list:
        return True
    return False
        
def generate_regionwise_vpc_cidr_dict(**kwargs):
    """ 
        This function generates required VPC CIDR from reference VPC CIDR provided by user
        This function also checks if any existing VPC in region using same CIDR then generate another VPC CIDR
        If reference VPC CIDR is '172.73.0.0/16'
        It will generate dictionary of region and  VPC CIDR like {'ap-south-1': "172.73.0.0/16", 'us-east-1': "172.74.0.0/16"}
    """
    regionwise_vpc_cidr_dict = {}
    reference_vpc_cidr = kwargs.get("vpc_cidr")
    instance_locations = kwargs.get("instance_locations")
    rh_id = kwargs.get("rh_id")
    vpc_list = reference_vpc_cidr.split("/")[0].split(".")
    vpc_cidr_list = [int(i) for i in vpc_list]
    net_mask = int(reference_vpc_cidr.split("/")[-1])
    #AWS VPC block rule :- The allowed block size is between a /28 netmask and /16 netmask.
    if net_mask < 16: net_mask = 16
    if net_mask >28: net_mask = 28
    byte_n_bit = [int(net_mask/8)-1 if net_mask%8==0 else int(net_mask/8),int(net_mask%8)] # If net_mask is 16 then byte_n_bit=[1,0], If net_mask is 18 then byte_n_bit=[2,2]
    # AWS automatically converts trailing bits (32-net_mask) to '0' before creating VPC
    if byte_n_bit[-1] == 0:
        set_byte = byte_n_bit[0]
        # vpc_cidr_list[byte_n_bit[0]+1:]=[0]*(3-byte_n_bit[0])   # Truncate all trailing bytes e.g. if net_mask is 16 then make last 2 bytes 0 if not
        if vpc_cidr_list[byte_n_bit[0]] <= 127:
            range_list = [i for i in range(vpc_cidr_list[byte_n_bit[0]],255)]
        else:
            range_list = [i for i in range(10,vpc_cidr_list[byte_n_bit[0]])]
    else:   #e.g. 172.64.128.1/18
        set_byte = byte_n_bit[0]-1
        
        vpc_cidr_list[byte_n_bit[0]+1:]=[0]*(3-byte_n_bit[0])   #[172, 64, 128, 0] truncated last byte
        # Note :- Next 5 lines checks and also makes correction if byte and netmask do not match. E.g. If 3rd byte is 160 then will convert it to 128 by masking
        vpc_byte_bin = bin(int(vpc_cidr_list[byte_n_bit[0]])).split("b")[-1]   # 128 becomes '10000000'
        vpc_byte_bin = "0"*(8-len(vpc_byte_bin))+vpc_byte_bin   # Add if any leading '0' required
        vpc_bits_in_byte = vpc_byte_bin[:byte_n_bit[1]]   #'10'
        vpc_bits_of_byte = vpc_byte_bin[:byte_n_bit[1]]+"0"*(8-byte_n_bit[1])   # Add remining '0' to '10' to make it 8 bit
        vpc_cidr_list[byte_n_bit[0]]=int(vpc_bits_of_byte,2)  # Convert binary to decimal and add it to vpc cidr

        previous_byte = vpc_cidr_list[byte_n_bit[0]-1]
        if previous_byte <= 127:
            range_list = [i for i in range(previous_byte,255)]
        elif previous_byte > 127:
            range_list = [i for i in range(10,previous_byte)]
    # set_progress('vpc_cidr_list"{}"'.format(vpc_cidr_list))
    for region in instance_locations.keys():
        client = create_boto3_client(rh_id=rh_id,aws_region=region) #changed kwarg
        response = client.describe_vpcs()
        resp = response['Vpcs']
        vpc_existing_cidr = []
        for vpc in resp:
            vpc_existing_cidr.append(vpc['CidrBlock'])
        for byte in range_list:
            vpc_cidr_list[set_byte] = byte
            vpc_ip = ".".join([str(i) for i in vpc_cidr_list])
            vpc_cidr = f"{vpc_ip}/{net_mask}"
            if check_vpc_cidr_in_region(vpc_cidr=vpc_cidr,existing_vpc_cidr_list=vpc_existing_cidr):
                range_list.remove(byte)
                regionwise_vpc_cidr_dict[region]=vpc_cidr
                break
    return regionwise_vpc_cidr_dict    # For example {'ap-south-1': '172.75.0.0/18', 'us-east-1': '172.76.0.0/18'}
        
def create_all_new_VPC(**kwargs):  #Case2
    """
        This function creates new VPC in all provided regions
    """
    regionwise_vpcid_dict = {}
    reference_vpc_cidr = kwargs.get("vpc_cidr")
    Tenancy = kwargs.get("tenancy")
    instance_locations = kwargs.get("instance_locations") # It is dictionary like {'ap-south-1': ['ap-south-1a ', ' ap-south-1c '], 'us-east-1': [' us-east-1a ', ' us-east-1d ']}
    rh_id = kwargs.get("rh_id")
    base_name = kwargs.get("base_name")
    region_vpc_cidr_dict = generate_regionwise_vpc_cidr_dict(instance_locations=instance_locations,rh_id=rh_id,vpc_cidr=reference_vpc_cidr)  # Get available VPC CIDR for each required region
    for region in instance_locations.keys():
        client = create_boto3_client(rh_id=rh_id,aws_region=region) 
        vpc_cidr_id_list = create_new_VPC(vpc_cidr=region_vpc_cidr_dict[region],region=region,Client=client,Tenancy=Tenancy)
        resp = add_name_to_resource(client=client,resource_id=vpc_cidr_id_list[-1],resource_name=f"VPC-{base_name}-{region}")
        # regionwise_vpcid_dict[region] = [region_vpc_cidr_dict[region],vpc_id]    #{'ap-south-1': ['172.75.0.0/18','vpc-029991485a8857b43'], 'us-east-1': ['172.76.0.0/18','vpc-0752f2f2fcf2013e1']}
        regionwise_vpcid_dict[region] = vpc_cidr_id_list
    return regionwise_vpcid_dict

def create_all_subnets(**kwargs):
    """
        This function creates subnets in all selected zones in a region
        It returns a dictionary with all details of VPC and Subnets created
    """
    region = kwargs.get("region")
    region_vpc_dict = kwargs.get("region_vpc_id_dict")
    rh_id = kwargs.get("rh_id")
    instance_locations_dict = kwargs.get("instance_locations_dict")
    base_name = kwargs.get("base_name")
    region_vpc_subnet_nested_dict = {}
    client = create_boto3_client(rh_id=rh_id,aws_region=region) 
    vpc_subnet_dict = {}
    subnet_id_cidr_zone_list = []
    subnet_index = -1
    vpc_cidr = region_vpc_dict[region][0]
    vpc_id = region_vpc_dict[region][1]
    
    resp = client.describe_subnets(Filters=[ {
             'Name': 'vpc-id',
             'Values': [vpc_id ,] }, ], )
    no_of_subnets_in_vpc = len(resp['Subnets'])
    
    response = client.describe_subnets()
    existing_subnet_cidr_list = [subnet['CidrBlock'].split("/")[0] for subnet in response['Subnets']]
    #set_progress('Existing subnet cidr list"{}"'.format(existing_subnet_cidr_list))   # For testing only
    subnet_cidr_list = create_subnet_ip_list(vpc_cidr=vpc_cidr,Number_of_zones_selected_in_region=len(instance_locations_dict[region]),existing_subnet_cidr_list=existing_subnet_cidr_list,no_of_subnets_in_vpc=no_of_subnets_in_vpc)
    #set_progress('final subnet cidr list"{}"'.format(subnet_cidr_list))   # For testing only
    vpc_subnet_dict['VPC']=[vpc_id,vpc_cidr]
    
    for zone in instance_locations_dict[region]:
        zone = zone.replace(" ","")
        subnet_not_created =  True
        while subnet_not_created:
            subnet_index+=1
            subnet_id = create_vpc_subnet(client=client,zone=zone,subnet_cidr=subnet_cidr_list[subnet_index],VPD_ID=vpc_id)
            if subnet_id != "NA":
                subnet_not_created = False
            #else:    # For testing only
            #   set_progress(f"skipping subnet CIDR '{subnet_cidr_list[subnet_index]}' due to conflict...")
        time.sleep(5)
        resp = add_name_to_resource(client=client,resource_id=subnet_id,resource_name=f"Subnet-{base_name}-{zone}")
        subnet_id_cidr_zone_list.append((subnet_id,subnet_cidr_list[subnet_index],zone))   #For example ('subnet-02d362d5a35cbd39e','172.31.0.0/19','ap-south-1a')
        
    vpc_subnet_dict['Subnet'] = subnet_id_cidr_zone_list 
    # vpc_subnet_dict  looks as follows
    # {'VPC':['vpc-029991485a8857b43','172.75.0.0/18'],'Subnet':[('subnet-02d362d5a35cbd39e','172.31.0.0/19','ap-south-1a'),('subnet-02d362d5a35cbd39e','172.31.75.0/19','ap-south-1b'),...]
    region_vpc_subnet_nested_dict[region]=vpc_subnet_dict
    return region_vpc_subnet_nested_dict
   
def get_region_vpc_dict_from_existing_vpc_selection(**kwargs):
    """
        This function generated a dictionary of VPC details from existing VPC 
    """
    existing_vpc_selection = kwargs.get("existing_vpc")
    rh_id = kwargs.get("rh_id")
    region_vpc_id_dict = {}
    vpc_id = existing_vpc_selection.split(" @")[0]
    region = existing_vpc_selection.split("@ ")[1] 
    client = create_boto3_client(rh_id=rh_id,aws_region=region)
    response = client.describe_vpcs(VpcIds=[vpc_id,])
    vpc_cidr = response['Vpcs'][0]['CidrBlock']
    region_vpc_id_dict[region]=[vpc_cidr,vpc_id]
    return region_vpc_id_dict # For example, {'ap-south-1': ['172.75.0.0/18','vpc-029991485a8857b43'], 'us-east-1': ['172.76.0.0/18','vpc-0752f2f2fcf2013e1']}
    
def add_inbound_rules(**kwargs):
    """
        This function adds all inbound rules to security group required for HA deployment
    """
    region_security_group_vpc_dict = kwargs.get("region_security_group_vpc_dict")
    rh_id = kwargs.get("rh_id")
    ports = [22,80,443,2049,5432]   # SSH:22, HTTP:80, HTTPS:443, NFS:2049, PostgresSQL:5432
    for region in region_security_group_vpc_dict.keys():
        client = create_boto3_client(rh_id=rh_id,aws_region=region)
        for port in ports:
            data = client.authorize_security_group_ingress(
                    GroupId=region_security_group_vpc_dict[region][0],
                    IpPermissions=[
                        {'IpProtocol': 'tcp',
                         'FromPort': port,
                         'ToPort': port,
                         'IpRanges': [{'CidrIp': "0.0.0.0/0"}]}
                    ])
    return True
    
def run(job, *args, **kwargs):
    resource = kwargs.get('resource')
    get_or_create_custom_fields()
    vpc_cidr = '{{vpc_cidr}}'
    tenancy = 'default'
    
    inst_loc_dict_vdout_xsting_vpc = {}
    region_vpc_subnet_nested_dict = {}  # This dictionary will contain all the details of VPC in region and Subnets in zones in that region
    region_vpc_id_dict = {}   # For example, {'ap-south-1': ['172.75.0.0/18','vpc-029991485a8857b43'], 'us-east-1': ['172.76.0.0/18','vpc-0752f2f2fcf2013e1']}
    base_name = "HA"
    if resource.parent_resource_id:
        parent_resource = Resource.objects.get(id = resource.parent_resource_id)
        group_id = parent_resource.group_id
        rh = AWSHandler.objects.get(id = parent_resource.aws_rh_id)
        instance_locations_dict = create_instance_location_dict(parent_resource=parent_resource)
        existing_vpc_selection = parent_resource.vpc_selection[-1]
        aws_ha_region = parent_resource.aws_region_ha
        base_name = parent_resource.base_name
        set_progress('AWS HA region detected is "{}"'.format(aws_ha_region))
        # set_progress('instance locations dictionary retrieved as  "{}"'.format(instance_locations_dict))
        
    if existing_vpc_selection == "Not Selected Any": #Case 1 :- User have not selected any existing VPCs, Create VPC for selected region
        set_progress("Case 1 :- User have not selected any existing VPCs, Create VPC for selected region")
        inst_loc_dict_vdout_xsting_vpc = {k:v for k,v in instance_locations_dict.items()}   # Because all VPCs are New
        region_vpc_id_dict = create_all_new_VPC(vpc_cidr=vpc_cidr,tenancy=tenancy,instance_locations=instance_locations_dict,rh_id=rh.id,base_name=base_name) #,Resource=resource)
        # set_progress('regionwise vpc details :- "{}"'.format(region_vpc_id_dict))
        region_vpc_subnet_nested_dict = create_all_subnets(region=aws_ha_region,region_vpc_id_dict=region_vpc_id_dict,rh_id=rh.id,instance_locations_dict=instance_locations_dict,base_name=base_name)
        set_progress('VPC detail dictionary :- "{}"'.format(region_vpc_subnet_nested_dict))
        vpc_id = region_vpc_subnet_nested_dict[aws_ha_region]['VPC'][0]
        
            # region_vpc_subnet_nested_dict looks as follows
            # {'ap-south-1': {'VPC':['vpc-029991485a8857b43','172.75.0.0/18'],'Subnet':[('subnet-02d362d5a35cbd39e','172.31.0.0/19','ap-south-1a'),('subnet-02d362d5a35cbd39e','172.31.75.0/19','ap-south-1b'),...]
            # To access VPC details of particular region say 'ap-south-1' use region_vpc_subnet_nested_dict['ap-south-1']['VPC'] --- gives list of [ID,CIDR]
            # To access Subnet details of particular region say 'ap-south-1' use region_vpc_subnet_nested_dict['ap-south-1']['Subnet'] ---gives list of tuple as [(ID,CIDR,Zone),(ID,CIDR,Zone),...]
    else:     # Case 2  : VPC is selected by user
        set_progress("Case 2 :- Existing VPC for selected region is selected by user")
        region_vpc_id_dict = get_region_vpc_dict_from_existing_vpc_selection(existing_vpc=existing_vpc_selection,rh_id=rh.id)
        # set_progress('regionwise vpc details :- "{}"'.format(region_vpc_id_dict))
        region_vpc_subnet_nested_dict = create_all_subnets(region=aws_ha_region,region_vpc_id_dict=region_vpc_id_dict,rh_id=rh.id,instance_locations_dict=instance_locations_dict,base_name=base_name)
        set_progress('VPC detail dictionary :- "{}"'.format(region_vpc_subnet_nested_dict))
        vpc_id = region_vpc_subnet_nested_dict[aws_ha_region]['VPC'][0]
    
    # Adding environment if required    
    if Environment.objects.filter(vpc_id=vpc_id).__len__() == 0:  
        wrapper = rh.get_api_wrapper()
        region_display_name_in_list = [region['display'] for region in wrapper.get_all_regions() if region['name']==aws_ha_region]
        region_display_name = region_display_name_in_list[0] if len(region_display_name_in_list)!=0 else aws_ha_region  # To avoid list out of index error
        env_name = f"({rh.name}) {region_display_name} {vpc_id}"   # As per cloudbolt naming format
        env = Environment.objects.create(name=env_name, resource_handler=rh)
        env.aws_region = aws_ha_region
        env.vpc_id = vpc_id
        env.save()
        rh.sync_subnets(env)
        set_progress("Subnets are synced with Resource Handler...")
        grp = Group.objects.get(id = group_id)
        grp.environments.add(env)
        set_progress("Environment {} is created".format(env_name))
    for env in Environment.objects.filter(vpc_id=vpc_id):    
        if env.resource_handler.id == rh.id:
            rh.sync_subnets(env)
            set_progress("Subnets are synced with Resource Handler...")

    subnet_list = []
    subnet_id_list = []
    for subnet in region_vpc_subnet_nested_dict[aws_ha_region]['Subnet']:
        subnet_id_list.append(subnet[0])
    subnet_list.append("{0}@{1}".format(",".join(subnet_id_list),region_vpc_subnet_nested_dict[aws_ha_region]['VPC'][0]))
    
    # Creating Security Group for VPC
    region_security_group_vpc = {}
    client = create_boto3_client(rh_id=rh.id,aws_region=aws_ha_region)
    vpc_id = region_vpc_subnet_nested_dict[aws_ha_region]['VPC'][0]
    response = client.create_security_group(GroupName=f"SG-{base_name}-{vpc_id}",Description="Security Group for HA Setup",VpcId=vpc_id)
    security_group_id = response['GroupId']
    resp = add_name_to_resource(client=client,resource_id=security_group_id,resource_name=f"{base_name}-SecurityGroup")
    region_security_group_vpc[aws_ha_region] = (security_group_id,vpc_id)
    region_vpc_subnet_nested_dict[aws_ha_region]['VPC'].append(security_group_id)
    
    # Adding required inbound rules to security group
    resp = add_inbound_rules(region_security_group_vpc_dict=region_security_group_vpc,rh_id = rh.id)

    resource.subnet_list = " , ".join(subnet_list)
    resource.tenancy = tenancy
    resource.vpc = ", ".join([f"{region_vpc_id_dict[k][1]}:{region_vpc_id_dict[k][0]}@{k}" for k in region_vpc_id_dict.keys()]) # 'vpc-017eb43b8ee8f9393:172.31.0.0/16@us-east-1, vpc-0ce9c70903e00ee53:172.31.0.0/16@ap-south-1'
    resource.save()
    
    if resource.parent_resource_id:
        parent_resource.vpc_subnet_structure=("VPC Subnet Structure details",region_vpc_subnet_nested_dict)  # Get in dict format by using ast.literal_eval(parent_resource.vpc_subnet_structure[-1])
        parent_resource.save()
        
    return "SUCCESS", "VPC,subnets and security group are Successfully created..", ""