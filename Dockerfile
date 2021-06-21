FROM locustio/locust

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY common/ common/
COPY locustfile.py locustfile.py

# copy the list of URLs for loadtest
ENV URLLIST=urllist.csv

# use random profile selection (other methods are min or max)
ENV PROFILESELECTION=abr
