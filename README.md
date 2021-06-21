# abrperf

ABR Streaming load performance tester based on locust.io.

Only HLS Live is supported at the moment.

**Use directly against a cache**, becaus it will follow the redirect of a request router, 
but it will not stick with the edge cache: all fragment request will be downloaded through 
the request router (_FastHttpUser_ class follows the redirect, but it does not provides a way
to query the new FQDN...)  


## Prerequisites

 - one master host
 - one or more slave hosts (you can use the master as slave, but I do not recommend it)
 - ssh access from the master host to the slave hosts (I recommend pubkey auth)

## Install (on both, maater and slave)

### prerequisites
```bash
yum install python3 python3-devel
```

### clone and create a venv

Please make sure, that you clone abrperf into ~/abrperf
```bash
git clone https://github.com/jursonovicst/abrperf.git
cd abrperf
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

## Configure

Configuration is only done on the master host, config files will be automatically copied to the slave nodes.

 - edit _runme.sh_
   - list the IP addresses of the slave hosts under the _slavehosts_ variable
   - add the IP address of the master host under the _masterhost_ variable
   - edit the number of slaves to be started per hosts under the _numslaves_ variable
 - edit the _abrperf.ini_
 - list your streaming URLs in the _urllist.csv_
## RUN

### In standalone mode without WebGUI

Create the 'urllist.csv' file in the root directory of this module, and list the URLs of master playlists and their 
weights (positive integer) to request.

```csv
http://example.com/sport1/index.m3u8,10
http://example2.com/sport2/index.m3u8,1
```

The first URL will be 10x requested, then the second one.


To start the loadtest, run locust like this: 

```bash
locust -f locustfiles/hlsplayer.py --host https://example.com --headless -u 10 -r 0.1 -t 100s
```

You MUST specify an URL in the --host attribute, otherwise the loadtester will not start, but the --host attribute will 
be completel ignored.
 
### In distributed mode with webgui

Just run the runme sh script from the ~/abrperf directory, this will copy the config files to the slaves, start
the locust slaves, and start the locust master. 
```bash
% ./runme.sh 
abrperf.ini                                                                                                                                          100%  831     2.1MB/s   00:00    
urllist.csv                                                                                                                                          100%  262   775.3KB/s   00:00    
abrperf.ini                                                                                                                                          100%  831     1.7MB/s   00:00    
urllist.csv                                                                                                                                          100%  262   739.5KB/s   00:00    
[2020-08-11 16:48:29,544] Tamas-MacBook-Pro.local/INFO/locust.main: Starting web interface at http://:8089
[2020-08-11 16:48:29,551] Tamas-MacBook-Pro.local/INFO/root: Config loaded.
[2020-08-11 16:48:29,551] Tamas-MacBook-Pro.local/INFO/locust.main: Starting Locust 1.1.1
[2020-08-11 16:48:29,552] Tamas-MacBook-Pro.local/INFO/locust.runners: Client 'Tamas-MacBook-Pro.local_2e66006faf764fc89bf390127d371c7f' reported as ready. Currently 1 clients ready to swarm.
[2020-08-11 16:48:29,592] Tamas-MacBook-Pro.local/INFO/locust.runners: Client 'Tamas-MacBook-Pro.local_c7bdd9b653e64ae4b0d1513839b6258d' reported as ready. Currently 2 clients ready to swarm.
[2020-08-11 16:48:29,675] Tamas-MacBook-Pro.local/INFO/locust.runners: Client 'Tamas-MacBook-Pro.local_a08f06e7652c4cb2b43b9409120383a2' reported as ready. Currently 3 clients ready to swarm.
[2020-08-11 16:48:29,697] Tamas-MacBook-Pro.local/INFO/locust.runners: Client 'Tamas-MacBook-Pro.local_cbe7ab9c007f4208a88785241a40e063' reported as ready. Currently 4 clients ready to swarm.
```

Now, you can connect with your web browser to IP of the master host.

To stop the simulation, just type CTRL+C in the console, where the _runme.sh_ is running, this
will kill all slaves and master.

```bash
^CKeyboardInterrupt
2020-08-11T14:50:52Z
[2020-08-11 16:50:52,207] Tamas-MacBook-Pro.local/INFO/locust.main: Running teardowns...
[2020-08-11 16:50:52,209] Tamas-MacBook-Pro.local/INFO/locust.runners: Client 'Tamas-MacBook-Pro.local_c7bdd9b653e64ae4b0d1513839b6258d' quit. Currently 3 clients connected.
[2020-08-11 16:50:52,210] Tamas-MacBook-Pro.local/INFO/locust.runners: Client 'Tamas-MacBook-Pro.local_a08f06e7652c4cb2b43b9409120383a2' quit. Currently 2 clients connected.
[2020-08-11 16:50:52,210] Tamas-MacBook-Pro.local/INFO/locust.runners: Client 'Tamas-MacBook-Pro.local_2e66006faf764fc89bf390127d371c7f' quit. Currently 1 clients connected.
[2020-08-11 16:50:52,210] Tamas-MacBook-Pro.local/INFO/locust.runners: Client 'Tamas-MacBook-Pro.local_cbe7ab9c007f4208a88785241a40e063' quit. Currently 0 clients connected.
[2020-08-11 16:50:52,210] Tamas-MacBook-Pro.local/INFO/locust.runners: The last worker quit, stopping test.
[2020-08-11 16:50:52,713] Tamas-MacBook-Pro.local/INFO/locust.main: Shutting down (exit code 0), bye.
[2020-08-11 16:50:52,713] Tamas-MacBook-Pro.local/INFO/locust.main: Cleaning up runner...
 Name                                                          # reqs      # fails     Avg     Min     Max  |  Median   req/s failures/s
--------------------------------------------------------------------------------------------------------------------------------------------
--------------------------------------------------------------------------------------------------------------------------------------------
 Aggregated                                                         0     0(0.00%)       0       0       0  |       0    0.00    0.00

Percentage of the requests completed within given times
 Type                 Name                                                           # reqs    50%    66%    75%    80%    90%    95%    98%    99%  99.9% 99.99%   100%
------------------------------------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------------------------------------

kill: 4389: No such process
kill: 4395: No such process
kill: 4389: No such process
kill: 4395: No such process
```

## ToDo:

* consider using other reporting: https://www.blazemeter.com/blog/locust-monitoring-with-grafana-in-just-fifteen-minutes
