# These are very private AWS keys for spinning up EC2 services
# ... guard very carefully

# refer to;
# https://github.com/nextml/NEXT/wiki/AWS-Account-Quickstart
# https://github.com/nextml/NEXT/wiki/EC2-launch
#       for more detail

# These keys are used to
# a) Launch NextML on EC2
# b) Make keys available for NextML managment via launch.py

# NOTE: Very important to note what REGION the key was created in
# (NextML uses a different default region)
export AWS_ACCESS_KEY_ID='AKIAITAJQHHNFYAAV6OA'
export AWS_SECRET_ACCESS_KEY='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'
export KEY_FILE='/hdd/work/AWS/EC2/keypair/nextml.pem'
export KEY_PAIR='nextml' # this is the name (not file) in AWS of the Key Pair
export EC2_REGION='us-east-2'
export EC2_INSTANCE='m4.large'
export EC2_CLUSTER_NAME='my_nextml_cluster'
export AWS_BUCKET_NAME=[buckid]
export NEXT_BACKEND_GLOBAL_HOST=[public-dns]