#!/usr/bin/env bash

# locust slave hosts (SSH access is needed, use pubkey auth...)
slavehosts=(127.0.0.1 127.0.0.1)
masterhost=127.0.0.1

# number of locust slaves to start per host
numslaves=2

for host in ${slavehosts[*]}; do
  # sync config
  scp ./abrperf.ini $host:abrperf/
  scp ./urllist.csv $host:abrperf/

  # start slaves
  ssh $host "rm ~/abrperf/slaves.pid"
  for i in $(seq 1 $numslaves); do
    ssh $host "cd ~/abrperf/ && source venv/bin/activate && nohup locust -f locustfiles/hlsplayer.py --worker --master-host=$masterhost >/dev/null 2>&1 & echo \$! >> slaves.pid"
  done
done

# start master and wait for exit
source venv/bin/activate && locust -f locustfiles/hlsplayer.py --master

# termiante slaves
for host in ${slavehosts[*]}; do
  ssh $host "cat ~/abrperf/slaves.pid | xargs kill -9"

done


