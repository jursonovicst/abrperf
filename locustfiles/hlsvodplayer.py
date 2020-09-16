import os
import logging
import resource
from locust import TaskSet, task, between, SequentialTaskSet, events
from locust.contrib.fasthttp import FastHttpUser, FastResponse
from locust.runners import MasterRunner
import m3u8
import time
from common import Config
import platform


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

    # read configuration
    environment.config = Config()
    logging.info(f"Config loaded.")


class PlayVoD(TaskSet):
    """
    Streams a vod variant playlist by continuously requesting the playlist, and selecting and requesting the latest
    segment.
    """

    wait_left = 0

    @task
    def play(self):
        ts_start = time.time()

        if len(self.user.host) == 0:
            self.interrupt()

        segment = self.user.host.pop(-1)
        logging.debug(f"Segment URL: '{segment.title}'")

        seg_get = self.client.get(segment.absolute_uri, name=f"{segment.absolute_uri} S")

        # calculate the remaining time till next segment fetch
        ts_stop = time.time()
        if segment.duration - (ts_stop - ts_start) < 0:
            logging.warning(f"segment over time request")
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
     - starting a 'PlayLive' TaskSet for live streaming, or
     - starting a 'PlayVoD' TaskSet for VoD streaming.
     - In case, a TaskSet will terminate, it terminates itself.s
    """

    def on_start(self):
        """
        User and TaskSet classes can declare an on_start method and/or on_stop method. A User will call it’s on_start
        method when it starts running, and it’s on_stop method when it stops running. For a TaskSet, the on_start method
        is called when a simulated user starts executing that TaskSet, and on_stop is called when the simulated user
        stops executing that TaskSet (when interrupt() is called, or the user is killed).
        """
        # load config
        self._config = self.client.environment.config
        logging.info(f"Starting streaming client.")

    @task
    def master_playlist(self):
        """
            # 1st gets the master playlist and selects the appropriate variant_playlist
        """
        # parse master url
        master_url = self._config.getrandomurl()
        logging.debug(f"Master URL: '{master_url}'")
        base_url = os.path.dirname(master_url)
        logging.debug(f"Base URL: '{base_url}'")

        # get master manfest
        master_manifest = self.client.get(master_url, name=f"{master_url} M")

        if not isinstance(master_manifest, FastResponse):
            logging.error(f"Error accesing master playlist: {vars(master_manifest)}")
            self.interrupt()

        if 'Content-Type' not in master_manifest.headers:
            logging.error(f"No Content-Type received, terminating streaming client.")
            self.interrupt()

        if master_manifest.headers['Content-Type'] != 'application/vnd.apple.mpegurl':
            # unknown streaming
            logging.error(f"Unknown stream with Content-Type '{master_manifest.headers['Content-Type']}', terminating.")
            self.interrupt()

        # HLS -- m3u8!
        logging.debug(f"HLS stream detected ({master_manifest.headers['Content-Type']})")

        # parse playlist
        master_m3u8 = m3u8.M3U8(content=master_manifest.text, base_uri=base_url)
        #        logging.debug(f"EXT-X-VERSION: '{master_m3u8}'") TODO: check why this is not working

        if not master_m3u8.is_variant:
            logging.error(f"No variant playlist detected: '{master_url}'")
            self.interrupt()

        # Select profile according to the profile selection config
        profilemethod = self._parent.client.environment.config.profilemethod()
        variant_playlist = profilemethod(master_m3u8.playlists, key=lambda playlist: playlist.stream_info.bandwidth)
        logging.debug(
            f"profile {variant_playlist.stream_info.program_id} selected (bandwidth: {variant_playlist.stream_info.bandwidth}, resolution: {variant_playlist.stream_info.resolution})")

        # update locust User with the new URL
        self.user.host = f"{base_url}/{variant_playlist.uri}"

    @task
    def variant_playlist(self):
        """
            # 2nd check the variant playlist
        """

        variant_url = self.user.host
        logging.debug(f"Variant URL: '{variant_url}'")
        base_url = os.path.dirname(variant_url)

        # get variant manifest
        variant_manifest = self.client.get(variant_url, name=f"{variant_url} V")

        if not isinstance(variant_manifest, FastResponse):
            logging.error(f"Error accesing variant playlist: {vars(variant_manifest)}")
            self.interrupt()

        if 'Content-Type' not in variant_manifest.headers:
            logging.error(f"No Content-Type received, terminating streaming client.")
            self.interrupt()

        if variant_manifest.headers['Content-Type'] != 'application/vnd.apple.mpegurl':
            logging.error(
                f"Unsupported Content-Type received: {variant_manifest.headers['Content-Type']}, terminating streaming client.")
            self.interrupt()

        variant_m3u8 = m3u8.M3U8(content=variant_manifest.text, base_uri=base_url)

        if variant_m3u8.playlist_type.upper() != 'VOD':
            logging.error(f"Unsupported playlist type detected: '{variant_m3u8.playlist_type}', terminating.")
            self.interrupt()

        # update locust User with the new URL
        self.user.host = variant_m3u8.segments

    tasks = [PlayVoD]

    @task
    def stop(self):
        """
        3rd if streaming ends, terminates
        """
        self.interrupt()


class MyLocust(FastHttpUser):
    tasks = [PlayStream]

    # we need to specify this, but we will not use it
    wait_time = between(0, 0)
