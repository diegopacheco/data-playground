#!/bin/bash
set -eu
cd /opt/druid
CONF=var/nano
rm -rf "$CONF"
cp -r conf/druid/single-server/nano-quickstart "$CONF"
sed -i 's/-Xms[0-9]*m/-Xms64m/;s/-Xmx512m/-Xmx256m/;s/MaxDirectMemorySize=400m/MaxDirectMemorySize=256m/' "$CONF"/*/jvm.config
mkdir -p log
bin/run-zk conf > log/zk.log 2>&1 &
for service in coordinator-overlord broker historical middleManager; do
  bin/run-druid "$service" "$CONF" > "log/$service.log" 2>&1 &
done
wait -n
