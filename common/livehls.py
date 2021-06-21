from locust import TaskSet, task
import m3u8
import time
#import os
#import platform
#from urllib.error import HTTPError


class LiveHLS(TaskSet):

    @task
    def segment(self):
        if True:  # TODO: here are the streaming players
            self.hlslive()

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
