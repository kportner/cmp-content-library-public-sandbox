#!/usr/bin/env bash
echo "
----------------------
  Update the local repository
----------------------
"
sudo yum update -y

echo "
----------------------
  Install NODE & NPM
----------------------
"
# set noderepo
curl –sL https://rpm.nodesource.com/setup_14.x | sudo bash -

# Install nodejs
sudo yum install -y nodejs

# check the node version
node --version

# check the npm version
npm --version

## You may also need development tools to build native addons:
sudo yum install -y gcc gcc-c++ make

## To install the Yarn package manager, run:
curl -sL https://dl.yarnpkg.com/rpm/yarn.repo | sudo tee /etc/yum.repos.d/yarn.repo

# install yarn
sudo yum install -y yarn


echo "
----------------------
  PM2
----------------------
"
# install pm2 with npm
sudo npm install -g pm2

# set pm2 to start automatically on system startup
sudo pm2 startup systemd

sleep 60

echo "
----------------------
  Setup MongoDB Repo
----------------------
"

if [ -f "$/etc/yum.repos.d/mongodb.repo" ]; then
  # update the mongo db repo permission
  sudo chmod 777 /etc/yum.repos.d/mongodb.repo
else
  # create mongodb repo file 
  sudo touch /etc/yum.repos.d/mongodb.repo

  # update the mongo db repo permission to udate the file
  sudo chmod 777 /etc/yum.repos.d/mongodb.repo
fi

# update mongodb repo file content
sudo echo $'[mongodb-org-6.0] \nname=MongoDB Repository \nbaseurl=https://repo.mongodb.org/yum/redhat/$releasever/mongodb-org/6.0/x86_64/ \ngpgcheck=1 \nenabled=1 \ngpgkey=https://www.mongodb.org/static/pgp/server-6.0.asc' > /etc/yum.repos.d/mongodb.repo

# set default permission for the mongo db repo file 
sudo chmod 644 /etc/yum.repos.d/mongodb.repo

echo "
----------------------
  MongoDB Repo File
----------------------
"
sudo cat /etc/yum.repos.d/mongodb.repo

echo "
----------------------
  Installing MongoDB
  Reference - https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-red-hat/
----------------------
"
sudo yum install -y mongodb-org

echo "
----------------------
  Start MongoDB Process
----------------------
"
sudo systemctl start mongod

echo "
----------------------
  Verify MongoDB Process has started
----------------------
"
sudo systemctl daemon-reload

echo "
----------------------
  Set mongodb to start automatically on system startup
----------------------
"
sudo systemctl enable mongod

echo "
------------------------
  Enable mongodb port for all ipv4
------------------------
"
sudo chmod 777 /etc/mongod.conf
sudo sed -i 's/127.0.0.1/0.0.0.0/' /etc/mongod.conf
sudo chmod 644 /etc/mongod.conf
sudo systemctl restart mongod

echo "
----------------------
  Mongodb Status
----------------------
"
sudo systemctl status mongod

echo "
----------------------
  Setup NGINX
----------------------
"
# Install EPEL source
sudo yum install -y epel-release

# install nginx
sudo yum install -y nginx

# start nginx and enable it to auto-start at system boot, then check its status.
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl status nginx

echo "
----------------------
  UFW (FIREWALL)
----------------------
"
# install firewalld
sudo yum install -y firewalld

# start firewalld and enable it to auto-start at system boot, then check its status.
sudo systemctl start firewalld
sudo systemctl enable firewalld
sudo systemctl status firewalld

# the following commands to allow HTTP and HTTPS traffic
sudo firewall-cmd --zone=public --add-port=80/tcp --permanent
sudo firewall-cmd --zone=public --add-port=8081/tcp --permanent
sudo firewall-cmd --zone=public --add-port=8004/tcp --permanent
sudo firewall-cmd --zone=public --add-port=27017/tcp --permanent
sudo firewall-cmd --permanent --zone=public --add-service=http
sudo firewall-cmd --permanent --zone=public --add-service=https
sudo firewall-cmd --reload

echo  "
----------------------
 Setup MongoDB WEB UI
----------------------
"
# install docker
sudo yum install -y yum-utils
sudo yum-config-manager  --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# start docker
sudo systemctl start docker

# install docker-compose
sudo curl -L "https://github.com/docker/compose/releases/download/1.23.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# check docker-compose version
docker-compose --version

# add docker user and group
sudo usermod -aG docker ${USER}
sudo ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
sudo service docker restart

echo "
----------------------
 Create MongoDB docker compose yaml file
----------------------
"
cur_dir=$(pwd)

mkdir $cur_dir/mongo_web

# get ec2 intance public ip
PUBLIC_IP=$(curl -s ifconfig.me)
IN_V="PUBLIC_IP"

# create python file to conver json to yaml
sudo echo -e 'import yaml \ndata={ \n"version": "3", \n"services": { \n"mongo-express": { \n"image": "mongo-express:latest", \n"container_name": "mongo-web", \n"restart": "unless-stopped", \n"ports": [ \n"8081:8081" \n], \n"environment": { \n"ME_CONFIG_MONGODB_ADMINUSERNAME": "root", \n"ME_CONFIG_MONGODB_ADMINPASSWORD": "password", \n"ME_CONFIG_MONGODB_URL": "mongodb://PUBLIC_IP:27017/" \n} \n} \n} \n} \nf=open("docker-compose.yaml","w") \nf.write(yaml.dump(data)) \nf.close' > /home/centos/mongo_web/convert_json_to_yaml.py

# set ec2 instance public ip
sudo sed -i "s/${IN_V}/${PUBLIC_IP}/" $cur_dir/mongo_web/convert_json_to_yaml.py

# change dir
cd $cur_dir/mongo_web/

# convert json to yaml file
python convert_json_to_yaml.py

# start docker-compose
sudo docker-compose up -d

sleep 30

echo "
---------------------- 
  Mongodb Install successfully
----------------------
"

echo "
----------------------
  Setup MERN Stack Web Application
----------------------
"

echo "
----------------------
  Install wget, git and unzip packages
----------------------
"
# Install git 
sudo yum install -y git

# Install wget
sudo yum install -y wget

# Install unzip 
sudo yum install -y unzip


echo "
----------------------
  Download MERN Stack E-Book Application Zip
----------------------
"
#cd /home/centos
cd $cur_dir
# clone back end project from github
sudo wget https://github.com/CloudBoltSoftware/cloudbolt-forge/raw/ENG-22516-MERN-Stack_Blueprint/blueprints/mern_stack_on_centos/mern-stack-e-book-demo.zip

# unzip e-book application
sudo unzip $cur_dir/mern-stack-e-book-demo.zip
if [ $? -ne 0 ];
then
    exit 1
fi

echo "
-----------------------------------
  Setup E-Book API
---------------------------------
"
# update ownership
sudo chown centos:centos -R $cur_dir/mern-stack-e-book-demo

# Navigate into the back-end directory and install all required npm package
cd $cur_dir/mern-stack-e-book-demo/backend

echo "
-----------------------------------
  Update MongoDB Connection String
---------------------------------
"
IN_MO_DB="mongodb_connection_string"
OU_MO_DB="mongodb://${PUBLIC_IP}:27017/cloudbolt"

sudo sed -i "s|${IN_MO_DB}|${OU_MO_DB}|g"  config/default.json

echo "
----------------------
  Install npm
----------------------
"
sudo npm install

echo "
----------------------
  Start pm2 server
----------------------
"
# Start the API using the PM2 process manager
sudo pm2 start app.js

echo "
-----------------------------------
  Setup E-Book UI
---------------------------------
"
cd $cur_dir/mern-stack-e-book-demo/frontend

# update public ip in .env file
sudo sed -i "s|PUBLIC_IP|${PUBLIC_IP}|g"  .env

# update package.json file
sudo sed -i "s|PUBLIC_IP|${PUBLIC_IP}|g"  package.json

# update backend api endpoint
sudo sed -i "s|PUBLIC_IP|${PUBLIC_IP}|g" src/utils/constant.js

echo "
----------------------
  Install & Build npm
----------------------
"
sudo npm install

# generate react build folder
sudo npm run build

echo "
--------------------------------------------------------------
  Configure NGINX to serve the Node.js API and React front-end
--------------------------------------------------------------
"

# Negigate the Nginx server directory
cd /etc/nginx

# change permission, to add new config file
sudo  chmod 777 conf.d

# Create a MERN Stack config file for a API.
sudo echo -e "upstream my_nodejs_upstream { \n server 127.0.0.1:4000; \n keepalive 64; \n }  \n server {  \n   listen 8004;  \n   server_name PUBLIC_IP;   \n  root /home/centos/mern-stack-e-book-demo/bacnkend;   \n location / {    \n    proxy_set_header X-Forwarded-For proxy_add_x_forwarded_for;    \n    proxy_set_header Host http_host;    \n    proxy_set_header X-NginX-Proxy true;   \n    proxy_http_version 1.1;    \n    proxy_set_header Upgrade http_upgrade;    \n   proxy_set_header Connection "upgrade";   \n     proxy_max_temp_file_size 0;   \n     proxy_pass http://my_nodejs_upstream/;  \n     proxy_redirect off; \n     proxy_read_timeout 240s;  \n } \n }" > /etc/nginx/conf.d/mern_stack_api.conf

# Create a MERN Stack config file for a front-end web application.
sudo echo -e "server { \n listen 0.0.0.0:80; \n   server_name UI_PUBLIC_IP; \n\n # react app & front-end files \n location / {  \n    root /home/centos/mern-stack-e-book-demo/frontend/build; \n try_files \$uri /index.html; \n } \n # node api reverse proxy \n location /api/ { \n proxy_pass http://API_PUBLIC_IP:8004/; \n } \n }" > /etc/nginx/conf.d/mern_stack_frontend.conf

# update public ip in API config
sudo sed -i "s|PUBLIC_IP|${PUBLIC_IP}|g"  /etc/nginx/conf.d/mern_stack_api.conf
sudo sed -i "s|UI_PUBLIC_IP|${PUBLIC_IP}|g"  /etc/nginx/conf.d/mern_stack_frontend.conf
sudo sed -i "s|API_PUBLIC_IP|${PUBLIC_IP}|g"  /etc/nginx/conf.d/mern_stack_frontend.conf
sudo sed -i 's/proxy_add_x_forwarded_for/$proxy_add_x_forwarded_for/' /etc/nginx/conf.d/mern_stack_api.conf
sudo sed -i 's/http_host/$http_host/' /etc/nginx/conf.d/mern_stack_api.conf
sudo sed -i 's/http_upgrade/$http_upgrade/' /etc/nginx/conf.d/mern_stack_api.conf

# reset the default permissions and ownership
sudo chmod 644 /etc/nginx/conf.d/mern_stack_api.conf
sudo chown root:root /etc/nginx/conf.d/mern_stack_api.conf
sudo chmod 644 /etc/nginx/conf.d/mern_stack_frontend.conf
sudo chown root:root /etc/nginx/conf.d/mern_stack_frontend.conf

# reset the default permission
sudo chmod 755 conf.d

# change permission, to update the user name in file
sudo chmod 777 nginx.conf

# update username
sudo sed -i 's/user nginx;/user centos;/' nginx.conf

# reset the default permission
sudo chmod 644 nginx.conf

# reload nginx config files
sudo nginx -s reload

# disbale SE linux
sudo setenforce 0

echo "
--------------------------------------
  Restart Nginx Server & Check Status
--------------------------------------
"
# Restart the Nginx Server
sudo systemctl restart nginx

# Nginx server status
sudo systemctl status nginx

echo "
-----------------------------------
  Import sample book data
---------------------------------
"
sudo curl -X POST http://${PUBLIC_IP}:8004/api/books -H "Content-Type: application/json" -d @$cur_dir/mern-stack-e-book-demo/backend/data/sample_book.json


echo "
----------------------
  MERN Stack Web Application deployment completed successfully.
----------------------
"