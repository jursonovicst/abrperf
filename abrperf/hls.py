from locust import TaskSet, task, SequentialTaskSet
from locust.exception import StopUser
import m3u8
import time
import os


class HLS(SequentialTaskSet):

    def __init__(self, *args, **kwargs):
        super(HLS, self).__init__(*args, **kwargs)
        self.variant = None

    @task
    def stream(self):
        # get the media manifest
        self.variant_pls = self.client.environment.profileselector.select(self.client.manifest.playlists, lambda playlist: playlist.stream_info.bandwidth, self.client.throughput)

        with self.client.get(self.variant_pls.uri,
                             headers={'User-Agent': f"Locust/1.0"},
                             catch_response=True) as response:

            if response.status_code >= 400:
                response.failure(f"HTTP error {response.status_code}, stopping user")
                raise StopUser()

            # determine streaming type
            filename, extension = os.path.splitext(self.variant_pls.uri)
            if (extension == '.m3u8' or
                    extension == '.m3u' or
                    ('Content-Type' in response.headers and response.headers['Content-Type'] in [
                        'application/vnd.apple.mpegurl', 'audio/mpegurl'])):
                # HLS -- m3u8!
                self.client.logger.debug(f"HLS manifest detected")

                # parse playlist
                self.variant = m3u8.M3U8(content=response.text, base_uri=self.client.manifest.base_uri)
                self.client.logger.debug(f"HLS v{self.variant.version}, type: '{self.variant.playlist_type}'")

                if self.variant.playlist_type == 'VOD':
                    response.failure(f"Playlist type {self.variant.playlist_type}' not supported, stopping user")
                    raise StopUser()

                # download segments
                #with self.client.client_video.get()

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

    def hlslive(self):
        if not self.user._firstrun:
            # get variant manifest
            self.user.logger.debug(f"GET '{self.user.base_url}/{self.user.variant_pls.uri}'")
            with self.client.get(f"{self.user.base_url}/{self.user.variant_pls.uri}",
                                 headers={'User-Agent': f"Locust/1.0"},
                                 catch_response=True) as response:
                response.raise_for_status()

                # parse variant
                self.user.variant = m3u8.M3U8(content=response.text, base_uri=self.user.base_url)

        self.user._firstrun = False

        # get the latest segment
        segment = max(self.user.variant.segments, key=lambda s: s.program_date_time.timestamp())

        # set the timestamp for the next variant fetch
        if self.user._ts_next is None:
            self.user._ts_next = time.time() + segment.duration
        else:
            self.user._ts_next += segment.duration

        self.user.logger.debug(f"next segment TS: {self.user._ts_next:.2f}")

        # fetch the segment
        self.user.logger.debug(f"GET '{segment.absolute_uri}'")
        with self.client.get(segment.absolute_uri,
                             headers={'User-Agent': f"Locust/1.0"},
                             catch_response=True) as response:
            response.raise_for_status()

            # measure throughput with segment
            self.user.throughput = len(response) * 8 / response._request_meta['response_time'] * 1000

            # select the next variant playlist
            self.user.variant_pls = self.client.environment.profileselector.select(self.user.manifest.playlists,
                                                                                   lambda
                                                                                       playlist: playlist.stream_info.bandwidth,
                                                                                   self.user.throughput)
            self.user.logger.debug(
                f"profile ID {self.user.variant_pls.stream_info.program_id} selected (bandwidth: {self.user.variant_pls.stream_info.bandwidth / 1000 / 1000:.2f} Mbps, resolution: {self.user.variant_pls.stream_info.resolution}), throughput: {self.user.throughput / 1000 / 1000:.2f} Mbps")

            # calculate the remaining time till next segment fetch
            if self.user._ts_next - time.time() < 0:
                response.failure(f"segment over time request: {time.time() - self.user._ts_next:.2f} s")

        # reschedule next call
        self.wait_left = max(0, (self.user._ts_next - time.time()))

    def wait_time(self):
        """
        Schedule segment requests always at segment time, compensate for segment download.
        """
        return self.wait_left
