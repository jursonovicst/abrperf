import os
import logging
import resource
from locust import TaskSet, task, between, SequentialTaskSet, events
from locust.contrib.fasthttp import FastHttpUser
from locust.runners import MasterRunner
import m3u8
import time
import common.config
import datetime


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """
    The init event is triggered at the beginning of each Locust process. This is especially useful in distributed mode
    where each worker process (not each user) needs a chance to do some initialization.
    """
    # set the highest limit of open files in the server
    resource.setrlimit(resource.RLIMIT_NOFILE, resource.getrlimit(resource.RLIMIT_NOFILE))

    if isinstance(environment.runner, MasterRunner):
        logging.debug("I'm on master node")
    else:
        logging.debug("I'm on a worker or standalone node")

    # read configuration
    environment.config = common.config.HLSPlayerConfig()

    logging.info(f"Config loaded.")
    logging.debug(f"Config: {environment.config}")


class play_live(TaskSet):
    """
    Streams a live variant playlist by continiously requesting the playlist, and selecting and requesting the latest
    segment.
    """

    wait_left = 0

    @task
    def play(self):
        ts_start = time.time()

        variant_url = self.user.host
        base_url = os.path.dirname(variant_url)
        variant_m3u8 = self.client.get(variant_url, name=f"{variant_url} V")
        parsed_variant_m3u8 = m3u8.M3U8(content=variant_m3u8.text, base_uri=base_url)

        # get the timestamp of the latest segment
        ts_latest = max(map(lambda segment: segment.program_date_time.timestamp(), parsed_variant_m3u8.segments))

        # get the closest segment to the timeshifted program date time
        segment = min(parsed_variant_m3u8.segments, key=lambda segment: abs(segment.program_date_time.timestamp() - (ts_latest - self.parent._timeshift)))
        seg_get = self.client.get(segment.absolute_uri, name=f"{variant_url} S")

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


class play_hls_stream(SequentialTaskSet):
    """
    Starts a live HLS streaming session by
     - requesting the master playlist and selecting a variant, then
     - starting a 'play_live' TaskSet for streaming the variant.
     - In case, the 'play_live' TaskSet will terminate, it terminates itself.
    """

    def on_start(self):
        # load config
        self._config = self.client.environment.config
        self._timeshift = self._config.gettimeshift()
        logging.info(
            f"Starting Live HLS User with{'out' if self._timeshift == 0 else ' %ds' % self._timeshift} timeshift.")

    @task
    def master_playlist(self):
        """
            # 1st gets the master playlist and selects the appropriate variant
        """

        # parse master url
        master_url = self._config.randomurl()
        logging.debug(f"Master URL: '{master_url}'")
        base_url = os.path.dirname(master_url)
        logging.debug(f"Base URL: '{base_url}'")

        # get master manifest
        master_m3u8 = self.client.get(master_url, name=f"{master_url} M")
        parsed_master_m3u8 = m3u8.M3U8(content=master_m3u8.text, base_uri=base_url)
        #        logging.debug(f"EXT-X-VERSION: '{parsed_master_m3u8}'") TODO: check why this is not working

        if not parsed_master_m3u8.is_variant:
            logging.error(f"This is not a variant playlist: '{master_url}'")
            self.interrupt()

        # Select profile according to the profile selection config
        profilemethod = self._parent.client.environment.config.profilemethod()
        variant = profilemethod(parsed_master_m3u8.playlists, key=lambda playlist: playlist.stream_info.bandwidth)

        #        TODO: check why this is not working
        #        if parsed_master_m3u8.simple_attributes.playlist_type != 'EVENT':
        #            logging.error(f"I need an EVENT (Live) plalist, but I got '{variant.playlist_type}'")
        #            self.interrupt()

        # uodate user with the new URL
        self.user.host = f"{base_url}/{variant.uri}"

    # 2nd starts streaming with the selected variant playlist
    tasks = [play_live]

    @task
    def stop(self):
        """
        3rd if streaming ends, terminates
        """
        self.interrupt()


class MyLocust(FastHttpUser):
    tasks = [play_hls_stream]

    wait_time = between(0, 0)
