import boto3
import time

REGION = "us-west-2"
ASU_ID = "1233745983"
AMI_ID = "ami-0085e09b3c3da42f9"
SECURITY_GROUP_ID = "sg-0e15090f3211df2e6"
KEY_NAME = "web-key"
MAX_INSTANCES = 15

REQ_QUEUE = f"{ASU_ID}-req-queue"

ec2 = boto3.client("ec2", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)

request_queue_url = sqs.get_queue_url(QueueName=REQ_QUEUE)["QueueUrl"]

def get_queue_depth():
    response = sqs.get_queue_attributes(
        QueueUrl=request_queue_url,
        AttributeNames=[
            "ApproximateNumberOfMessages", 
            "ApproximateNumberOfMessagesNotVisible"
        ]
    )
    waiting = int(response["Attributes"]["ApproximateNumberOfMessages"])
    processing = int(response["Attributes"]["ApproximateNumberOfMessagesNotVisible"])
    return waiting + processing

def get_active_instances():
    response = ec2.describe_instances(
        Filters=[
            {"Name": "instance-state-name", "Values": ["running", "pending"]},
            {"Name": "tag:Name", "Values": ["app-tier-instance*"]}
        ]
    )
    instances = []
    for r in response["Reservations"]:
        for i in r["Instances"]:
            instances.append(i["InstanceId"])
    return instances

def launch_instances(num):
    if num <= 0:
        return
    user_data = """#!/bin/bash
su - ec2-user -c "cd /home/ec2-user/CSE546-SPRING-2026 && pip3 install boto3 torch torchvision --index-url https://download.pytorch.org/whl/cpu && nohup python3 backend.py > backend.log 2>&1 &"
"""
    ec2.run_instances(
        ImageId=AMI_ID,
        InstanceType="t3.micro",
        MinCount=1,
        MaxCount=num,
        KeyName=KEY_NAME,
        SecurityGroupIds=[SECURITY_GROUP_ID],
        IamInstanceProfile={"Name": "app-tier-role"},
        UserData=user_data,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": "app-tier-instance"}]
            }
        ]
    )

def terminate_instances(ids):
    if ids:
        ec2.terminate_instances(InstanceIds=ids)

def scale():
    while True:
        try:
            depth = get_queue_depth()
            active_instances = get_active_instances()
            active_count = len(active_instances)

            if depth == 0:
                if active_instances:
                    terminate_instances(active_instances)
            else:
                desired = min(depth, MAX_INSTANCES)
                if desired > active_count:
                    num_to_launch = desired - active_count
                    launch_instances(num_to_launch)
                    time.sleep(4)
            
            time.sleep(2)

        except Exception:
            time.sleep(2)

if __name__ == "__main__":
    scale()
