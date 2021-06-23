#!/bin/bash
set -e

influx v1 dbrp create \
  --bucket-id ${DOCKER_INFLUXDB_INIT_BUCKET_ID} \
  --db ${DOCKER_INFLUXDB_INIT_BUCKET} \
  --rp ${DOCKER_INFLUXDB_INIT_BUCKET}-rp \
  --default \
  --org ${DOCKER_INFLUXDB_INIT_ORG}

influx v1 auth create \
  --username ${GRAFANA_AUTH_USERNAME} \
  --password ${GRAFANA_AUTH_PASSWORD} \
  --write-bucket ${DOCKER_INFLUXDB_INIT_BUCKET_ID} \
  --org ${DOCKER_INFLUXDB_INIT_ORG}

influx v1 auth create \
  --username ${LOCUST_AUTH_USERNAME} \
  --password ${LOCUST_AUTH_PASSWORD} \
  --write-bucket ${DOCKER_INFLUXDB_INIT_BUCKET_ID} \
  --org ${DOCKER_INFLUXDB_INIT_ORG}
