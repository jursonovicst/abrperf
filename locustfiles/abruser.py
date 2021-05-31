import os
import configparser
import logging
import resource
import names
import m3u8
from urllib.error import HTTPError
import platform

from locust import constant, events
from locust.contrib.fasthttp import FastHttpUser
from locust.runners import MasterRunner
import gevent
from locust.env import Environment
from locust.stats import stats_printer, stats_history
from locust.log import setup_logging
from common import ProfileSelector, ABRProfileSelector, MaxProfileSelector, MinProfileSelector, HLSLive, URLList


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """
    The init event is triggered at the beginning of each Locust process. This is especially useful in distributed mode
    where each worker process (not each user) needs a chance to do some initialization.
    """
    if isinstance(environment.runner, MasterRunner):
        logging.debug(f"I'm the master on {platform.node()} node")
    else:
        logging.debug(f"I'm a worker or standalone on {platform.node()} node")

        # set the highest limit of open files in the server
        resource.setrlimit(resource.RLIMIT_NOFILE, resource.getrlimit(resource.RLIMIT_NOFILE))

        try:
            # configuration
            environment.config = configparser.ConfigParser()
            environment.config.read(os.getenv('ABRUSER_CONFIG', default='abruser.ini'))

            # url reader
            environment.urllist = URLList(environment.config['general'].get('urllist'))

            # profile selector
            if environment.config['abr']['profile_selection'] == 'min':
                environment.profileselector = MinProfileSelector()
            elif environment.config['abr']['profile_selection'] == 'max':
                environment.profileselector = MaxProfileSelector()
            elif environment.config['abr']['profile_selection'] == 'abr':
                environment.profileselector = ABRProfileSelector()
            else:
                environment.profileselector = ProfileSelector()

        except Exception:
            logging.exception("Exception in init")
            exit(-1)


class ABRUser(FastHttpUser):
    manifest = None
    base_url = None
    throughput = None
    logger = None
    variant = None
    variant_pls = None

    def on_start(self):
        """
        User and TaskSet classes can declare an on_start method and/or on_stop method. A User will call it’s on_start
        method when it starts running, and it’s on_stop method when it stops running. For a TaskSet, the on_start method
        is called when a simulated user starts executing that TaskSet, and on_stop is called when the simulated user
        stops executing that TaskSet (when interrupt() is called, or the user is killed).
        """

        # create uniq logger
        name = names.get_full_name()
        self.logger = logging.getLogger(name)

        try:
            # get a manifest url
            manifest_url = f"{self.environment.urllist.geturl()}&uid=LOCUST_{name.replace(' ', '_')}"
            self.logger.debug(f"URL to open: {manifest_url}")
            self.base_url = os.path.dirname(manifest_url)

            # get the master manifest
            with self.client.get(manifest_url, catch_response=True) as response_master:
                response_master.raise_for_status()

                # measure throughput with manifest
                self.throughput = len(response_master) * 8 / response_master._request_meta['response_time'] * 1000

                if 'Content-Type' not in response_master.headers:
                    raise Exception(f"No Content-Type received, terminating player.")

                if response_master.headers['Content-Type'] == 'application/x-mpegURL':
                    # HLS -- m3u8!

                    # parse playlist
                    self.manifest = m3u8.M3U8(content=response_master.text, base_uri=self.base_url)
                    self.logger.debug(
                        f"HLS Manifest v{self.manifest.version}, type: '{self.manifest.playlist_type}' detected")
                    #
                    if not self.manifest.is_variant:
                        raise Exception(f"No variant playlist detected: '{manifest_url}', terminating")

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
                                         catch_response=True) as response_media:
                        response_media.raise_for_status()

                        # parse variant
                        self.variant = m3u8.M3U8(content=response_media.text, base_uri=self.base_url)
                        if self.variant.playlist_type != 'VOD':
                            self.tasks = [HLSLive]
                            # self.__class__.tasks = [HLSLive]
                        else:
                            raise Exception(f"variant playlist type '{self.variant.playlist_type}' not supported!")

                else:
                    # unknown streaming
                    raise Exception(f"Unknown manifest: '{response_master.headers['Content-Type']}', terminating")

        except HTTPError as e:
            self.logger.warning(e)
        except Exception:
            self.logger.exception("Exception")

        self.logger.debug(f"user spawned")

    def on_stop(self):
        self.logger.debug(f"user terminated")

    # we need to specify these, but they will be ignored
    wait_time = constant(0)
    host = "http://this.will.be.ignored"


# for testing
if __name__ == "__main__":

    setup_logging('INFO')

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
