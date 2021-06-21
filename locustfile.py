import os
import logging
import resource

import locust.stats
import names
import platform
from common import LiveHLS, ProfileSelector, ABRProfileSelector, MaxProfileSelector, MinProfileSelector, URLList
import m3u8

from locust import constant, events, stats
from locust.exception import StopUser
from locust.contrib.fasthttp import FastHttpUser
from locust.runners import MasterRunner
import gevent
from locust.env import Environment
from locust.stats import stats_printer, stats_history
from locust.log import setup_logging

# set percentiles
locust.stats.PERCENTILES_TO_REPORT = list(
    map(float, os.getenv('PERCENTILES_TO_REPORT', '0.95,0.98,0.99,0.999,0.9999,1.0').split(sep=',')))


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """
    The init event is triggered at the beginning of each Locust process. This is especially useful in distributed mode
    where each worker process (not each user) needs a chance to do some initialization.
    """

    try:
        # setup logging
        setup_logging(os.getenv('LOGLEVEL', 'INFO'))

        logging.debug(f"Using percentiles {locust.stats.PERCENTILES_TO_REPORT}")

        # init workers
        if isinstance(environment.runner, MasterRunner):
            logging.debug(f"I'm the master on {platform.node()} node")
        else:
            logging.debug(f"I'm a worker or standalone on {platform.node()} node")

            # set the highest limit of open files in the server for worker
            resource.setrlimit(resource.RLIMIT_NOFILE, resource.getrlimit(resource.RLIMIT_NOFILE))
            logging.info(f"rlimit_nofile is {resource.getrlimit(resource.RLIMIT_NOFILE)}")

            # profile selector
            method = os.getenv('PROFILESELECTION', 'rnd')
            if method == 'min':
                environment.profileselector = MinProfileSelector()
            elif method == 'max':
                environment.profileselector = MaxProfileSelector()
            elif method == 'abr':
                environment.profileselector = ABRProfileSelector()
            else:
                environment.profileselector = ProfileSelector()

            logging.info(f"Using {environment.profileselector}")

            # url reader
            environment.urllist = URLList(os.getenv('URLLIST', default='urllist.csv'))
            logging.info(f"Using {environment.urllist.filename} with {environment.urllist.nourls} url(s)")

    except Exception:
        logging.exception("Exception in init")
        exit(-1)


class ABRUser(FastHttpUser):
    def __init__(self, environment):
        super().__init__(environment)

        self.name = names.get_full_name()
        self.logger = logging.getLogger(self.name)

        self.manifest = None
        self.base_url = None
        self.throughput = None
        self.variant = None
        self.variant_pls = None

    def on_start(self):
        """
        User and TaskSet classes can declare an on_start method and/or on_stop method. A User will call it’s on_start
        method when it starts running, and it’s on_stop method when it stops running. For a TaskSet, the on_start method
        is called when a simulated user starts executing that TaskSet, and on_stop is called when the simulated user
        stops executing that TaskSet (when interrupt() is called, or the user is killed).
        """

        self.manifest = None
        self.base_url = None
        self.throughput = None
        self.variant = None
        self.variant_pls = None

        # get a manifest url
        manifest_url = self.environment.urllist.geturl()
        self.base_url = os.path.dirname(manifest_url)
        self.logger.debug(f"URL to open: {manifest_url}")

        # get the master manifest, add user info
        with self.client.get(
                f"{manifest_url}&uid={self.name.replace(' ', '_')}",
                name=manifest_url,
                headers={'User-Agent': f"Locust/1.0"},
                catch_response=True) as response_master:
            if response_master.status_code >= 400:
                response_master.failure(f"HTTP error {response_master.status_code}, stopping user")
                raise StopUser()

            # measure initial throughput with manifest
            self.throughput = len(response_master) * 8 / response_master._request_meta['response_time'] * 1000
            self.logger.debug(f"throughput: {self.throughput / 1000 / 1000:.2f} Mbps")

            # determine streaming type
            filename, extension = os.path.splitext(manifest_url)
            if (extension == '.m3u8' or
                    extension == '.m3u' or
                    ('Content-Type' in response_master.headers and response_master.headers['Content-Type'] in [
                        'application/vnd.apple.mpegurl', 'audio/mpegurl'])):
                # HLS -- m3u8!
                self.logger.debug(f"HLS manifest detected")

                # parse playlist
                self.manifest = m3u8.M3U8(content=response_master.text, base_uri=self.base_url)
                self.logger.debug(f"HLS v{self.manifest.version}, type: '{self.manifest.playlist_type}'")

                if not self.manifest.is_variant:
                    response_master.failure(f"No variant playlist detected: '{manifest_url}', stopping user")
                    raise StopUser()

                # get the media manifest
                self.variant_pls = self.environment.profileselector.select(self.manifest.playlists,
                                                                           lambda
                                                                               playlist: playlist.stream_info.bandwidth,
                                                                           self.throughput)
                self.logger.debug(
                    f"profile ID {self.variant_pls.stream_info.program_id} selected (bandwidth: {self.variant_pls.stream_info.bandwidth / 1000 / 1000:.2f} Mbps, resolution: {self.variant_pls.stream_info.resolution}), throughput: {self.throughput / 1000 / 1000:.2f} Mbps")

                # get variant manifest
                self.logger.debug(f"GET '{self.base_url}/{self.variant_pls.uri}'")
                with self.client.get(f"{self.base_url}/{self.variant_pls.uri}",
                                     headers={'User-Agent': f"Locust/1.0"},
                                     catch_response=True) as response_media:
                    response_media.raise_for_status()

                    # parse variant
                    self.variant = m3u8.M3U8(content=response_media.text, base_uri=self.base_url)
                    if self.variant.playlist_type != 'VOD':
                        # start
                        ABRUser.tasks = [LiveHLS]
                    else:
                        response_media.failure(
                            f"variant playlist type '{self.variant.playlist_type}' not supported, stopping user")
                        raise StopUser()

            else:
                # unknown streaming
                response_master.failure(
                    f"unknown manifest '{manifest_url}': '{response_master.headers['Content-Type']}', stopping user")
                raise StopUser()

            self._firstrun = True
            self._ts_next = None
            self.logger.debug(f"running {self.__class__.__name__}")

    def on_stop(self):
        self.logger.debug(f"user terminated")

    # how long to wait between rescheduling Streaming
    wait_time = constant(1)
    host = "http://this.will.be.ignored"

    tasks = []


# for testing
if __name__ == "__main__":
    try:
        # setup Environment and Runner
        env = Environment(user_classes=[ABRUser])
        on_locust_init(env)
        env.create_local_runner()

        # start a greenlet that periodically outputs the current stats
        gevent.spawn(stats_printer(env.stats))

        # start a greenlet that save current stats to history
        gevent.spawn(stats_history, env.runner)

        # start the test
        env.runner.start(10, spawn_rate=1)

        # in 60 seconds stop the runner
        gevent.spawn_later(300, lambda: env.runner.quit())

        # wait for the greenlets
        env.runner.greenlet.join()
    except KeyboardInterrupt:
        env.runner.greenlet.kill()
    except Exception:
        logging.exception("Exception")
