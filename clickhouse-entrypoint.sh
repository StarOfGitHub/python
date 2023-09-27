#!/bin/bash

sed -i 's,<listen_host>::1</listen_host>,<listen_host>127.0.0.1</listen_host>,' ${CLICKHOUSE_CONFIG}
sed -i 's,<listen_host>::</listen_host>,<listen_host>0.0.0.0</listen_host>,' ${CLICKHOUSE_CONFIG}
/usr/bin/clickhouse-server --config=${CLICKHOUSE_CONFIG}
