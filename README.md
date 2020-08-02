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
```bash
locust -f locustfiles/hlsplayer.py --host https://example.com/SPORT/index.m3u8 --headless -u 10 -r 0.1 -t 100s
```
