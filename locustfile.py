import os
import logging
import queue
import resource

import locust.stats
import names
import platform
from common import Stream, ProfileSelector, ABRProfileSelector, MaxProfileSelector, MinProfileSelector, URLList
import m3u8
from mpegdash.parser import MPEGDASHParser

from locust import constant, events, stats
from locust.exception import StopUser
from locust.contrib.fasthttp import FastHttpUser, FastHttpSession, FastResponse
from locust.runners import STATE_STOPPING, STATE_STOPPED, STATE_CLEANUP, WorkerRunner, MasterRunner
import gevent
from locust.env import Environment
from locust.stats import stats_printer, stats_history
from locust.log import setup_logging

from queue import SimpleQueue
from typing import Dict

# set percentiles for cli stats
locust.stats.PERCENTILES_TO_REPORT = list(
    map(float, os.getenv('PERCENTILES_TO_REPORT', '0.95,0.98,0.99,0.999,0.9999,1.0').split(sep=',')))


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """
    Fired when Locust is started, once the Environment instance and locust runner instance
    have been created. This hook can be used by end-users' code to run code that requires access to
    the Environment. For example to register listeners to request_success, request_failure
    or other events.
    Event arguments:
    :param environment: Environment instance
    """

    try:
        # setup logging
        setup_logging(os.getenv('LOGLEVEL', 'INFO'))  # TODO: use locust's loglevel (args?)
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
            logging.info(f"Using {environment.urllist.filename} with {len(environment.urllist)} url(s)")

            # event handler for reporting
            environment.queue = SimpleQueue()
            environment.events.request.add_listener(on_request)
            gevent.spawn(reporter, environment)

    except Exception:
        logging.exception("Exception in init")
        exit(-1)


@events.quitting.add_listener
def on_locust_quitting(environment, **kwargs):
    """
    Fired when the locust process is exiting
    Event arguments:
    :param environment: Environment instance
    """
    pass


@events.request.add_listener
def on_request(request_type: str, name: str, response_time: int, response_length: int, response: FastResponse,
               context: Dict, exception: Exception, **kwargs):
    """
    :param request_type: Request type method used
    :param name: Path to the URL that was called (or override name if it was used in the call to the client)
    :param response_time: Time in milliseconds until exception was thrown
    :param response_length: Content-length of the response
    :param response: Response object (e.g. a :py:class:`requests.Response`)
    :param context: :ref:`User/request context <request_context>`
    :param exception: Exception instance that was thrown. None if request was successful.
    """
    if 'queue' in context:
        context['queue'].put_nowait({'request_type': request_type, 'name': name, 'response_time': response_time,
                                     'response_length': response_length, 'status_code': response.status_code,
                                     'exception': str(exception)})


#    with open('tom.txt', 'a') as f:
#        f.write(f"{context, request_type, name, response_time, response_length, response.status_code, context, exception}\n")


def reporter(environment):
    # build chunk while not exiting
    while environment.runner.state not in [STATE_STOPPING, STATE_STOPPED, STATE_CLEANUP]:

        chunk = []
        # get reports, limit chunk size to 100,
        while environment.runner.state not in [STATE_STOPPING, STATE_STOPPED, STATE_CLEANUP] and len(chunk) < 100:
            try:
                chunk.append(environment.queue.get(block=True, timeout=0.2))
            except queue.Empty:
                # if there is no more report within 0.2s, close it
                break

        # send reports
        with open('tom.txt', 'a') as f:
            for item in chunk:
                f.write(f"{item}\n")


class ABRUser(FastHttpUser):
    def __init__(self, environment):
        super().__init__(environment)

        self.name = names.get_full_name()
        self.logger = logging.getLogger(self.name)

        self.manifest = None
        # self.base_url = None
        self.throughput = None
        # self.variant = None
        # self.variant_pls = None

        # FastHTTPSession instances for parallel download of various fragments
        self.client_video = None
        self.client_audio = None
        self.client_subti = None

    def context(self) -> Dict:
        """
        Adds the returned value (a dict) to the context for request event
        """
        # pass the queue object to the request event
        return {"queue": self.environment.queue}

    def on_start(self):
        """
        User and TaskSet classes can declare an on_start method and/or on_stop method. A User will call it’s on_start
        method when it starts running, and it’s on_stop method when it stops running. For a TaskSet, the on_start method
        is called when a simulated user starts executing that TaskSet, and on_stop is called when the simulated user
        stops executing that TaskSet (when interrupt() is called, or the user is killed).
        """

        self.manifest = None
        # self.base_url = None
        self.throughput = None
        # self.variant = None
        # self.variant_pls = None

        # get a manifest url
        manifest_url = self.environment.urllist.geturl()
        base_url = os.path.dirname(manifest_url)
        self.logger.debug(f"URL to open: {manifest_url}")

        # get the master manifest, add user info
        with self.client.get(
                f"{manifest_url}{'&' if '?' in manifest_url else '?'}uid={self.name.replace(' ', '_')}",
                name=manifest_url,
                headers={'User-Agent': f"Locust/1.0"},
                catch_response=True) as response:

            if response.status_code >= 400:
                response.failure(f"HTTP error {response.status_code}, stopping user")
                raise StopUser()

            # measure initial throughput with manifest
            self.throughput = response._request_meta['response_length'] * 8 / \
                              (response._request_meta['response_time'] / 1000)
            self.logger.debug(f"Initial throughput: {self.throughput / 1000 / 1000:.2f}Mbps")

            # determine streaming type
            filename, extension = os.path.splitext(manifest_url)
            if (extension == '.m3u8' or
                    extension == '.m3u' or
                    ('Content-Type' in response.headers and response.headers['Content-Type'] in [
                        'application/vnd.apple.mpegurl', 'audio/mpegurl'])):
                # HLS -- m3u8!
                self.logger.debug(f"HLS manifest detected")

                # parse playlist
                self.manifest = m3u8.M3U8(content=response.text, base_uri=base_url)
                self.logger.debug(f"HLS v{self.manifest.version}, type: '{self.manifest.playlist_type}'")

                # try:
                #     for media in self.manifest.media:
                #         self.logger.debug(f"Media: {media}")
                #     for playlist in self.manifest.playlists:
                #         self.logger.debug(f"Playlist: {playlist.stream_info} - "
                #                           f"{playlist.stream_info.audio} - "
                #                           f"{playlist.stream_info.subtitles} - "
                #                           f"{playlist.stream_info.video}")
                # except Exception:
                #     self.logger.exception("TTT")
                #                    for media in playlist.media:
                #                        self.logger.debug(media.type)

                #                raise StopUser('x')

                if not self.manifest.is_variant:
                    response.failure(f"No variant playlist detected: '{manifest_url}', stopping user")
                    raise StopUser()

                if not self.manifest.playlists:
                    response.failure(f"No playlists found: '{self.manifest.playlists}', stopping user")
                    raise StopUser()

                #
                #
                # # get the media manifest
                # self.variant_pls = self.environment.profileselector.select(self.manifest.playlists,
                #                                                            lambda
                #                                                                playlist: playlist.stream_info.bandwidth,
                #                                                            self.throughput)
                # self.logger.debug(
                #     f"profile ID {self.variant_pls.stream_info.program_id} selected (bandwidth: {self.variant_pls.stream_info.bandwidth / 1000 / 1000:.2f} Mbps, resolution: {self.variant_pls.stream_info.resolution}), throughput: {self.throughput / 1000 / 1000:.2f} Mbps")
                #
                #
                # # get variant manifest
                # self.logger.debug(f"GET '{self.base_url}/{self.variant_pls.uri}'")
                # with self.client.get(f"{self.base_url}/{self.variant_pls.uri}",
                #                      headers={'User-Agent': f"Locust/1.0"},
                #                      catch_response=True) as response_media:
                #     response_media.raise_for_status()
                #
                #     # parse variant
                #     self.variant = m3u8.M3U8(content=response_media.text, base_uri=self.base_url)
                #     if self.variant.playlist_type != 'VOD':
                #         # start
                #         ABRUser.tasks = [LiveHLS]
                #     else:
                #         response_media.failure(
                #             f"variant playlist type '{self.variant.playlist_type}' not supported, stopping user")
                #         raise StopUser()

            elif (extension == '.mpd' or ('Content-Type' in response.headers and response.headers['Content-Type'] in [
                'application/dash+xml'])):
                # DASH -- mpd!
                self.logger.debug(f"DASH manifest detected")

                # parse playlist
                self.manifest = MPEGDASHParser.parse(response.text)
                self.logger.debug(f"MPEG DASH profile {self.manifest.profiles}")

            else:
                # unknown streaming
                self.logger.error(
                    f"unknown manifest '{manifest_url}': '{response.headers['Content-Type']}', stopping user")
                raise StopUser()

            # prepare sessions for streams
            self.client_video = FastHttpSession(self.environment, base_url, self)
            self.client_audio = FastHttpSession(self.environment, base_url, self)
            # make sure, cookies kept
            self.client_video.client.cookiejar = self.client.cookiejar
            self.client_audio.client.cookiejar = self.client.cookiejar

            # self._firstrun = True
            # self._ts_next = None
            # self.logger.debug(f"running {self.__class__.__name__}")

    def on_stop(self):
        self.logger.debug(f"user terminated")

    # how long to wait between rescheduling Streaming
    wait_time = constant(1)
    host = "http://this.will.be.ignored"

    tasks = [Stream]


# for testing
if __name__ == "__main__":
    try:
        # setup Environment and Runner
        env = Environment(user_classes=[ABRUser])
        #        env.events.init.add_listener(on_locust_init)
        #        env.events.quitting.add_listener(on_locust_quitting)
        on_locust_init(env)
        env.create_local_runner()

        # start a greenlet that periodically outputs the current stats
        gevent.spawn(stats_printer(env.stats))

        # start a greenlet that save current stats to history
        gevent.spawn(stats_history, env.runner)

        # start the test
        env.runner.start(2, spawn_rate=1)

        # in 60 seconds stop the runner
        gevent.spawn_later(300, lambda: env.runner.quit())

        # wait for the greenlets
        env.runner.greenlet.join()
    except KeyboardInterrupt:
        env.runner.greenlet.kill()
    except Exception:
        logging.exception("Exception")
