import boto3
import time
import os
import subprocess

REGION = "us-west-2"
ASU_ID = "1233745983"

s3 = boto3.client("s3", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)

REQ_QUEUE = f"{ASU_ID}-req-queue"
RESP_QUEUE = f"{ASU_ID}-resp-queue"
BUCKET = f"{ASU_ID}-in-bucket"
TABLE = f"{ASU_ID}-dynamoDB"

req_url = sqs.get_queue_url(QueueName=REQ_QUEUE)["QueueUrl"]
resp_url = sqs.get_queue_url(QueueName=RESP_QUEUE)["QueueUrl"]
table = dynamodb.Table(TABLE)

while True:
    messages = sqs.receive_message(
        QueueUrl=req_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=5
    )

    if "Messages" not in messages:
        continue

    for msg in messages["Messages"]:
        filename = msg["Body"].strip() 
        receipt = msg["ReceiptHandle"]

        try:
            local_path = f"/tmp/{filename}"
            s3.download_file(BUCKET, filename, local_path)

            result = subprocess.run(
                ["python3", "face_recognition.py", local_path],
                capture_output=True,
                text=True
            )
            pred = result.stdout.strip()

            table.put_item(Item={
                "filename": filename.split(".")[0],
                "prediction": pred
            })

            sqs.send_message(
                QueueUrl=resp_url,
                MessageBody=f"{filename}:{pred}"
            )

            sqs.delete_message(
                QueueUrl=req_url,
                ReceiptHandle=receipt
            )

            print(f"Processed {filename} → {pred}")

        except Exception as e:
            print(f"Error processing {filename}: {e}")
