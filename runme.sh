#!/usr/bin/env bash

# locust slave hosts (SSH access is needed, use pubkey auth...)
slavehosts=(127.0.0.1 127.0.0.1)
masterhost=127.0.0.1

# number of locust slaves to start per host
numslaves=2

for host in ${slavehosts[*]}; do
  # sync config
  echo "syncing config with slave $host..."
  scp -q ./abrperf.ini $host:abrperf/
  scp -q ./urllist.csv $host:abrperf/

  # start slaves
  ssh $host "rm -f ~/abrperf/slaves.pid"
  for i in $(seq 1 $numslaves); do
    echo "starting locust worker $i on slave $host..."
    ssh $host "cd ~/abrperf; source venv/bin/activate; nohup locust -f locustfiles/hlsplayer.py --worker --master-host=$masterhost &>/dev/null </dev/null & echo \$! >> slaves.pid"
  done
done

echo "starting master, terminate it with CTRL+C"
echo "*********************************************"
echo "* starting master, terminate it with CTRL+C *"
echo "*********************************************"
source venv/bin/activate && locust -f locustfiles/hlsplayer.py --master --web-host $masterhost

# termiante slaves
for host in ${slavehosts[*]}; do
  echo "terminating still running workers on slave $host..."
  ssh $host 'cat ~/abrperf/slaves.pid | xargs -I % kill -9 % 2>/dev/null'

done


