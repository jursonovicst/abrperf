import os
import logging
import resource
from locust import TaskSet, task, constant, SequentialTaskSet, events
from locust.contrib.fasthttp import FastHttpUser, FastResponse
from locust.runners import MasterRunner
import m3u8
import time
from common import Config
import platform
import names


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """
    The init event is triggered at the beginning of each Locust process. This is especially useful in distributed mode
    where each worker process (not each user) needs a chance to do some initialization.
    """
    # set the highest limit of open files in the server
    resource.setrlimit(resource.RLIMIT_NOFILE, resource.getrlimit(resource.RLIMIT_NOFILE))

    if isinstance(environment.runner, MasterRunner):
        logging.debug(f"I'm the master on {platform.node()} node")
    else:
        logging.debug(f"I'm a worker or standalone on {platform.node()} node")

    # read configuration (worker level)
    try:
        environment.config = Config(logging)
        logging.info(f"Config loaded.")
    except Exception as e:
        logging.error(e)
        exit(-1)


class PlayVoD(TaskSet):
    """
    Streams a vod variant playlist by continuously requesting the playlist, and selecting and requesting the latest
    segment.
    """

    wait_left = 0

    @task
    def play(self):
        ts_start = time.time()

        if len(self.parent._m3u8.segments) == 0:
            self.interrupt(reschedule=False)

        segment = self.parent._m3u8.segments.pop(0)
        self.user.logger.debug(f"Get segment: '{segment.uri}'")
        self.client.get(segment.absolute_uri,
                        name=f"{segment.uri}",
                        headers={'User-Agent': f"abrperf/1.0 ({self.user.name})"})

        # calculate the remaining time till next segment fetch
        ts_stop = time.time()
        if segment.duration - (ts_stop - ts_start) < 0:
            self.user.logger.warning(f"segment over time request")
        self.wait_left = max(0, segment.duration - (ts_stop - ts_start))

    def wait_time(self):
        """
        Schedule segment requests allways at segment time, compensate for segment downloads.
        """
        return self.wait_left


class PlayStream(SequentialTaskSet):
    """
    Starts a streaming session by
     - requesting the master playlist and selecting a variant, then
     - requesting the variabt playlist and
     - requesting all the segments.
     - In case, a TaskSet will terminate, it terminates itself.s
    """

    wait_left = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._config = None
        self._manifest_url = ''
        self._m3u8 = None
        self._type = None

    def on_start(self):
        """
        User and TaskSet classes can declare an on_start method and/or on_stop method. A User will call it’s on_start
        method when it starts running, and it’s on_stop method when it stops running. For a TaskSet, the on_start method
        is called when a simulated user starts executing that TaskSet, and on_stop is called when the simulated user
        stops executing that TaskSet (when interrupt() is called, or the user is killed).
        """
        # load config
        self._config = self.client.environment.config

        # get manifest url
        self._manifest_url = self._config.getrandomurl()
        self.user.logger.debug(f"Play stream URL: '{self._manifest_url}'.")

    def on_stop(self):
        self.user.logger.debug(f"Stream stop.")

    @task
    def manifest(self):
        """
        1st parse the manifest, in case of a master manifest, reparse it.
        """
        # get manifest
        self.user.logger.debug(f"Get manifest '{self._manifest_url}'")
        base_url = os.path.dirname(self._manifest_url)
        manifest = self.client.get(self._manifest_url,
                                   name=f"{os.path.basename(self._manifest_url)}",
                                   headers={'User-Agent': f"abrperf/1.0 ({self.user.name})"})

        if not isinstance(manifest, FastResponse):
            self.user.logger.error(f"Error accessing playlist: {vars(manifest)}")
            self.interrupt(reschedule=False)

        if 'Content-Type' not in manifest.headers:
            self.user.logger.warning(f"No Content-Type received.")

        if manifest.headers['Content-Type'] != 'application/vnd.apple.mpegurl':
            self.user.logger.error(f"Unknown stream with Content-Type '{manifest.headers['Content-Type']}'.")

        # it must be a m3u8 object, parse
        self._m3u8 = m3u8.M3U8(content=manifest.text, base_uri=base_url)
        #        logging.debug(f"EXT-X-VERSION: '{master_m3u8}'") TODO: check why this is not working

        if self._m3u8.is_variant:
            self.user.logger.debug(f"Master playlist detected: '{self._manifest_url}'")

            # Select profile according to the profile selection config
            profilemethod = self._config.profilemethod()
            playlist = profilemethod(self._m3u8.playlists, key=lambda pl: pl.stream_info.bandwidth)
            self.user.logger.debug(
                f"Profile {playlist.stream_info.program_id} selected (bandwidth: {playlist.stream_info.bandwidth}, resolution: {playlist.stream_info.resolution})")

            self._manifest_url = f"{base_url}/{playlist.uri}"
            self.user.logger.debug(f"Selected variant: {self._manifest_url}")

            # parse variant playlist
            self.manifest()

        else:
            self._type = self._m3u8.playlist_type.upper()
            self.user.logger.debug(f"Variant {self._type} playlist detected: '{self._manifest_url}'")

    """
    2nd: get the segments
    """
    tasks = [PlayVoD]

    def stop(self):
        """
        3rd if streaming ends, terminates
        """
        self.interrupt(reschedule=False)

    def wait_time(self):
        """
        Do not wait, go ahead.
        """
        return self.wait_left


class MyLocust(FastHttpUser):
    # Play stream
    tasks = [PlayStream]

    # we need to specify this, but it will be ignored
    wait_time = constant(0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = names.get_full_name()
        self._logger = logging.getLogger(self.name)

    @property
    def logger(self):
        return self._logger

    @property
    def name(self):
        return self._name

    def on_start(self):
        """
        User and TaskSet classes can declare an on_start method and/or on_stop method. A User will call it’s on_start
        method when it starts running, and it’s on_stop method when it stops running. For a TaskSet, the on_start method
        is called when a simulated user starts executing that TaskSet, and on_stop is called when the simulated user
        stops executing that TaskSet (when interrupt() is called, or the user is killed).
        """
        self.logger.info(f"User spawned.")

    def on_stop(self):
        self.logger.info(f"User terminated.")
