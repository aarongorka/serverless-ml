#!/usr/bin/env python3
import boto3
import time
import os, base64, random
from dateutil.tz import tzlocal
from dateutil.tz import tzutc
import datetime
import uuid
import json
from urllib.parse import urlparse, parse_qs, urlencode, quote_plus, unquote_plus
import logging
import botocore
import logging
import aws_lambda_logging
import requests
import unittest
from unittest.mock import patch
import responses
from requests.exceptions import HTTPError
from botocore.exceptions import ClientError
import zlib
import cloudfront_log_parser
import csv
import geoip2.database
import io
import tarfile
from multiprocessing.dummy import Pool as ThreadPool
import itertools
from functools import partial
import math
import robot_detection

aws_lambda_logging.setup(level=os.environ.get('LOGLEVEL', 'INFO'), env=os.environ.get('ENV'))
logging.info(json.dumps({'message': 'initialising'}))
aws_lambda_logging.setup(level=os.environ.get('LOGLEVEL', 'INFO'), env=os.environ.get('ENV'))


def transform(event, context):
    logging.info(json.dumps({'event': event}))
    correlation_id = get_correlation_id(event=event)

    bucket = event['Records'][0]['s3']['bucket']['name']
    key = unquote_plus(event['Records'][0]['s3']['object']['key'])
#    bucket = 'aarongorka-serverless-ml'
#    key = 'E2W5TI4SU4AMRI.2017-07-12-22.46a16946.gz'

    s3 = boto3.client('s3')
    s3_resource = boto3.resource('s3')
    response = s3.get_object(Bucket=bucket, Key=key)
    data = response['Body'].read()
    data = zlib.decompress(data, 16+zlib.MAX_WBITS).decode('UTF-8')

    reader = geoip2.database.Reader('./GeoLite2-City.mmdb')
#    data = """#Version: 1.0
##Fields: date time x-edge-location sc-bytes c-ip cs-method cs(Host) cs-uri-stem sc-status cs(Referer) cs(User-Agent) cs-uri-query cs(Cookie) x-edge-result-type x-edge-request-id x-host-header cs-protocol cs-bytes time-taken x-forwarded-for ssl-protocol ssl-cipher x-edge-response-result-type cs-protocol-version
#2017-07-12	22:25:50	IND6	556	2607:f2f8:a8e0::2	GET	d25881aryus3ny.cloudfront.net	/	301	-	Python-urllib/1.17	-	-	Redirect	tZXUNOuLdA-Yel6XE5T6F7nkTohRc1JFMB3JJjRUxt0VSqof06UR_w==	blog.aarongorka.com	http	90	0.001	-	-	-	Redirect	HTTP/1.0
#2017-07-12	22:25:53	NRT51	566	123.125.71.109	GET	d25881aryus3ny.cloudfront.net	/robots.txt	301	-	Mozilla/5.0%2520(compatible;%2520Baiduspider/2.0;%2520+http://www.baidu.com/search/spider.html)	-	-	Redirect	zB2s7XD7M6EHz27GOi3-jL7QQZEEFEs9BcJqBlchdkhCOLQ-zy9CZg==	blog.aarongorka.com	http	237	0.000	-	-	-	Redirect	HTTP/1.1
#2017-07-12	22:25:54	NRT51	499	123.125.71.52	GET	d25881aryus3ny.cloudfront.net	/robots.txt	200	-	Mozilla/5.0%2520(compatible;%2520Baiduspider/2.0;%2520+http://www.baidu.com/search/spider.html)	-	-	Miss	1fg7fZ1V_tdyYxtAuupGb8JBbR-81QIo6vimOXgNAhM8ieDwCJe7ZA==	blog.aarongorka.com	https	195	1.187	-	TLSv1.2	ECDHE-RSA-AES128-GCM-SHA256	Miss	HTTP/1.1"""
    parsed = cloudfront_log_parser.parse(data)    
    output = io.StringIO()
    fieldnames = ['ip_address', 'day_of_week', 'hour_of_day', 'minute_of_hour', 'edge', 'response_size', 'http_method', 'cloudfront_host', 'path', 'status_code', 'status_code_group', 'aborted', 'referrer', 'user_agent', 'browser_family', 'browser_version', 'os_family', 'os_version', 'device', 'is_mobile', 'is_tablet', 'is_pc', 'is_touch_capable', 'is_bot', 'querystring', 'edge_result_type', 'request_host', 'request_protocol', 'request_size', 'response_duration', 'ssl_protocol', 'ssl_cypher', 'edge_response_result_type', 'country', 'city', 'latitude', 'longitude' ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
    writer.writeheader()
    
    return_object = []
    logging.debug(json.dumps({'message': 'lines in log', 'length': len(parsed)}))
    pool = ThreadPool(3)
    return_object = pool.starmap(format_data, zip(parsed, itertools.repeat(reader)))
    pool.close()
    pool.join()
    reader.close()
    logging.debug(json.dumps({'message': 'multithreaded return object', 'object': '{}'.format(return_object)}))
    for row in return_object:
        logging.debug(json.dumps({'message': 'row in return_object', 'row': row}))
        writer.writerow(row)
    s3_resource.Object('aarongorka-serverless-ml-transformed', key.replace(".gz", ".csv")).put(Body=output.getvalue())
    
    logging.info(json.dumps({'message': 'Done!'}))

def format_data(i, reader):
    geoip = reader.city(i.ip_address)

    user_agent = i.user_agent

    try:
        user_agent = unquote_plus(user_agent)
    except:
        pass

    try:
        user_agent = unquote_plus(user_agent)
    except:
        pass

    try:
        edge = i.edge['code']
    except:
        edge = '-'

    status_code_group = str(math.floor(int(i.status_code)/100.0) * 100).replace("0", "x")

    fields = { 
        'ip_address': i.ip_address, 
        'day_of_week': i.timestamp.weekday(), 
        'hour_of_day': i.timestamp.hour, 
        'minute_of_hour': i.timestamp.minute, 
        'edge': edge,
        'response_size': i.response_size, 
        'http_method': i.http_method, 
        'cloudfront_host': i.cloudfront_host, 
        'path': i.path, 
        'status_code': i.status_code, 
        'status_code_group': status_code_group,
        'aborted': i.aborted, 
        'referrer': i.referrer, 
        'user_agent': user_agent, 
        'browser_family': i.browser_family, 
        'browser_version': i.browser_version, 
        'os_family': i.os_family, 
        'os_version': i.os_version, 
        'device': i.device, 
        'is_mobile': i.is_mobile, 
        'is_tablet': i.is_tablet, 
        'is_pc': i.is_pc, 
        'is_touch_capable': i.is_touch_capable, 
        'is_bot': i.is_bot, 
        'querystring': i.querystring, 
        'edge_result_type': i.edge_result_type, 
        'request_host': i.request_host, 
        'request_protocol': i.request_protocol, 
        'request_size': i.request_size, 
        'response_duration': i.response_duration,
        'ssl_protocol': i.ssl_protocol,
        'ssl_cypher': i.ssl_cypher,
        'edge_response_result_type': i.edge_response_result_type,
        'country': geoip.country.name,
        'city': geoip.city.name,
        'latitude': geoip.location.latitude,
        'longitude': geoip.location.longitude
    }
    for key, value in fields.items():
        if not value:
          if key in ['path', 'referrer', 'user_agent', 'querystring', 'request_host', 'request_protocol', 'ssl_protocol', 'ssl_cypher', 'country', 'city']:
            fields[key] = '-'
          if key in ['aborted']:
            fields[key] = False
    logging.debug(json.dumps({'message': 'fields in log line', 'fields': fields}))
    return fields

def get_correlation_id(body=None, payload=None, event=None):
    correlation_id = None
    if event:
        try:
            correlation_id = event['headers']['X-Amzn-Trace-Id'].split('=')[1]
        except:
            pass

    if body:
        try:
            correlation_id = body['trigger_id'][0]
        except:
            pass
    elif payload:
        try:
            correlation_id = payload['trigger_id']
        except:
            pass

    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    return correlation_id

def predict(event, context):
    logging.info(json.dumps({'event': event}))
    correlation_id = get_correlation_id(event=event)

#    bucket = event['Records'][0]['s3']['bucket']['name']
#    key = unquote_plus(event['Records'][0]['s3']['object']['key'])

    bucket = "aarongorka-serverless-ml-transformed"
    key = "E2W5TI4SU4AMRI.2017-07-12-22.46a16946.csv"

    data_s3url = "s3://{}/{}".format(bucket, key)
    schema_fn = "schema.json"
    
    ml = boto3.client('machinelearning')

    ds_id = 'ds-' + correlation_id
    ml.create_data_source_from_s3(
        DataSourceId=ds_id,
        DataSourceName="DS for Batch Prediction {}".format(data_s3url),
        DataSpec={
            "DataLocationS3": data_s3url,
            "DataSchema": open(schema_fn).read(),
        },
        ComputeStatistics=False
    )  

    bp_id = 'bp-' + correlation_id
    ds_id = create_data_source_for_scoring(ml, data_s3url, schema_fn)
    ml.create_batch_prediction(
        BatchPredictionId=bp_id,
        BatchPredictionName="Batch Prediction for marketing sample",
        MLModelId=model_id,
        BatchPredictionDataSourceId=ds_id,
        OutputUri=output_s3
    )

def build_model(event, context):
    """Creates all the objects needed to build an ML Model & evaluate its quality.
    """
    logging.info(json.dumps({'event': event}))
    correlation_id = get_correlation_id(event=event)

    data_s3_url = "s3://{}/{}".format('aarongorka-serverless-ml-transformed', 'training-data.csv')
    schema_fn = "schema.json"
    recipe_fn = "recipe.json"
    name = "serverless-ml"
    train_percent = 70

    ml = boto3.client('machinelearning')
    (train_ds_id, test_ds_id) = create_data_sources(ml, data_s3_url, schema_fn,
                                                    train_percent, name, correlation_id)
    ml_model_id = create_model(ml, train_ds_id, recipe_fn, name, correlation_id)
    eval_id = create_evaluation(ml, ml_model_id, test_ds_id, name, correlation_id)

    return ml_model_id


def create_data_sources(ml, data_s3_url, schema_fn, train_percent, name, correlation_id):
    """Create two data sources.  One with (train_percent)% of the data,
    which will be used for training.  The other one with the remainder of the data,
    which is commonly called the "test set" and will be used to evaluate the quality
    of the ML Model.
    """
    train_ds_id = 'ds-training-' + correlation_id
    spec = {
        "DataLocationS3": data_s3_url,
        "DataRearrangement": json.dumps({
            "splitting": {
                "percentBegin": 0,
                "percentEnd": train_percent
            }
        }),
        "DataSchema": open(schema_fn).read(),
    }
    ml.create_data_source_from_s3(
        DataSourceId=train_ds_id,
        DataSpec=spec,
        DataSourceName=name + " - training split",
        ComputeStatistics=True
    )
    logging.info(json.dumps({"message": "Created training data set", "id": train_ds_id}))

    test_ds_id = 'ds-test-' + correlation_id
    spec['DataRearrangement'] = json.dumps({
        "splitting": {
            "percentBegin": train_percent,
            "percentEnd": 100
        }
    })
    ml.create_data_source_from_s3(
        DataSourceId=test_ds_id,
        DataSpec=spec,
        DataSourceName=name + " - testing split",
        ComputeStatistics=True
    )
    logging.info(json.dumps({"message": "Created test data set", "id": test_ds_id}))
    return (train_ds_id, test_ds_id)


def create_model(ml, train_ds_id, recipe_fn, name, correlation_id):
    """Creates an ML Model object, which begins the training process.
The quality of the model that the training algorithm produces depends
primarily on the data, but also on the hyper-parameters specified
in the parameters map, and the feature-processing recipe.
    """
    model_id = 'ml-' + correlation_id
    ml.create_ml_model(
        MLModelId=model_id,
        MLModelName=name + " model",
        MLModelType="BINARY",  # we're predicting True/False values
        Parameters={
#            # Refer to the "Machine Learning Concepts" documentation
#            # for guidelines on tuning your model
#            "sgd.maxPasses": "100",
#            "sgd.maxMLModelSizeInBytes": "104857600",  # 100 MiB
#            "sgd.l2RegularizationAmount": "1e-4",
            "sgd.shuffleType": "auto"
        },
        Recipe=open(recipe_fn).read(),
        TrainingDataSourceId=train_ds_id
    )
    logging.info(json.dumps({"message": "Created ML model", "id": model_id}))
    return model_id


def create_evaluation(ml, model_id, test_ds_id, name, correlation_id):
    eval_id = 'ev-' + correlation_id
    ml.create_evaluation(
        EvaluationId=eval_id,
        EvaluationName=name + " evaluation",
        MLModelId=model_id,
        EvaluationDataSourceId=test_ds_id
    )
    logging.info(json.dumps({"message": "Created Evaluation", "id": eval_id}))
    return eval_id

def create_training_data(event, context):
    logging.info(json.dumps({'event': event}))
    correlation_id = get_correlation_id(event=event)

    s3_resource = boto3.resource('s3')
    data = open('./data.log')
    reader = geoip2.database.Reader('./GeoLite2-City.mmdb')
    parsed = cloudfront_log_parser.parse(data)    
    output = io.StringIO()
    fieldnames = ['ip_address', 'day_of_week', 'hour_of_day', 'minute_of_hour', 'edge', 'response_size', 'http_method', 'cloudfront_host', 'path', 'status_code', 'status_code_group', 'aborted', 'referrer', 'user_agent', 'browser_family', 'browser_version', 'os_family', 'os_version', 'device', 'is_mobile', 'is_tablet', 'is_pc', 'is_touch_capable', 'is_bot', 'querystring', 'edge_result_type', 'request_host', 'request_protocol', 'request_size', 'response_duration', 'ssl_protocol', 'ssl_cypher', 'edge_response_result_type', 'country', 'city', 'latitude', 'longitude', 'is_malicious_bot' ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
    writer.writeheader()
    
    return_object = []
    pool = ThreadPool(12)
    return_object = pool.starmap(format_data, zip(parsed, itertools.repeat(reader)))
    pool.close()
    pool.join()
    reader.close()
    whitelisted_ips = ['220.233.100.193', '54.79.75.105', '103.197.239.98', '54.252.209.191']
    bad_ips = ['111.88.139.9', '111.88.139.9']
    bad_agents = ['curl', 'wget', 'Python', 'python', 'ruby', '-', 'Java'] 
    logging.debug(json.dumps({'message': 'multithreaded return object', 'object': '{}'.format(return_object)}))
    for row in return_object:
        is_malicious_bot = True
        for i in bad_agents:
            if i in row['user_agent']:
                is_malicious_bot = True
        if robot_detection.is_robot(row['ip_address']):
            is_malicious_bot = False
        if row['ip_address'] in whitelisted_ips:
            is_malicious_bot = False
        if row['ip_address'] in bad_ips:
            is_malicious_bot = True
        if 'health' in row['path']:
            is_malicious_bot = False
        row['is_malicious_bot'] = is_malicious_bot

        # Ignore this metadata when training
        row['ip_address'] = ''
        row['request_host'] = ''
        writer.writerow(row)
    s3_resource.Object('aarongorka-serverless-ml-transformed', "training-data.csv").put(Body=output.getvalue())
    logging.info(json.dumps({'message': 'Done!'}))

if __name__ == '__main__':
#    build_model({},{})
    create_training_data({},{})
