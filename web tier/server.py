from flask import Flask, request
import boto3
import uuid

app = Flask(__name__)

ASU_ID = "1233745983"
REGION = "us-west-2"

BUCKET_NAME = f"{ASU_ID}-in-bucket"
REQUEST_QUEUE_NAME = f"{ASU_ID}-req-queue"
RESPONSE_QUEUE_NAME = f"{ASU_ID}-resp-queue"
TABLE_NAME = f"{ASU_ID}-dynamoDB"

s3 = boto3.client("s3", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

request_queue_url = sqs.get_queue_url(QueueName=REQUEST_QUEUE_NAME)["QueueUrl"]
response_queue_url = sqs.get_queue_url(QueueName=RESPONSE_QUEUE_NAME)["QueueUrl"]

global_results = {}

@app.route("/", methods=["POST"])
def handle_request():
    if "inputFile" not in request.files:
        return "Invalid request", 400

    file = request.files["inputFile"]
    filename = file.filename.strip()

    if filename == "":
        return "Invalid request", 400

    try:
        name_only = filename.rsplit('.', 1)[0]
        db_res = table.get_item(Key={"filename": name_only})
        
        if "Item" in db_res:
            return f"{filename}:{db_res['Item']['prediction']}"

        s3.upload_fileobj(file, BUCKET_NAME, filename)
        request_id = str(uuid.uuid4())

        sqs.send_message(
            QueueUrl=request_queue_url,
            MessageBody=filename,
            MessageAttributes={
                "RequestId": {
                    "StringValue": request_id,
                    "DataType": "String"
                }
            }
        )

        while True:
            if filename in global_results:
                return f"{filename}:{global_results.pop(filename)}"

            response = sqs.receive_message(
                QueueUrl=response_queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=2,
                MessageAttributeNames=["All"]
            )

            if "Messages" in response:
                message = response["Messages"][0]
                receipt_handle = message["ReceiptHandle"]
                body = message["Body"]

                sqs.delete_message(
                    QueueUrl=response_queue_url,
                    ReceiptHandle=receipt_handle
                )

                try:
                    msg_filename, msg_pred = body.split(":")
                    if msg_filename == filename:
                        return f"{filename}:{msg_pred}"
                    else:
                        global_results[msg_filename] = msg_pred
                except Exception:
                    pass

    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
