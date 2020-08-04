# abrperf

## Install

### prerequisites to build locust
```bash
yum install python3-devel
```

### clone and create a venv
```bash
git clone https://github.com/jursonovicst/abrperf.git
cd abrperf
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## RUN

### in standalone mode without WebGUI

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
 