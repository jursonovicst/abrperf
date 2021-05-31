from locust import TaskSet, task
import m3u8
import time
from urllib.error import HTTPError


class HLSLive(TaskSet):
    """
    Streams a live HLS stream by requesting the segments, and refreshing the variant playlist.
    """

    wait_left = 0

    def on_start(self):
        """
        User and TaskSet classes can declare an on_start method and/or on_stop method. A User will call it’s on_start
        method when it starts running, and it’s on_stop method when it stops running. For a TaskSet, the on_start method
        is called when a simulated user starts executing that TaskSet, and on_stop is called when the simulated user
        stops executing that TaskSet (when interrupt() is called, or the user is killed).
        """

        self.user._firstrun = True
        self.user._ts_next = None
        self.user.logger.debug(f"running {self.__class__.__name__}")

    @task
    def fragment(self):
        try:
            if not self.user._firstrun:
                # get variant manifest
                self.user.logger.debug(f"GET '{self.user.base_url}/{self.user.variant_pls.uri}'")
                with self.client.get(f"{self.user.base_url}/{self.user.variant_pls.uri}",
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

            self.user.logger.debug(f"next segmetn TS: {self.user._ts_next:.2f}")

            # fetch the segment
            self.user.logger.debug(f"GET '{segment.absolute_uri}'")
            with self.client.get(segment.absolute_uri, catch_response=True) as response:
                response.raise_for_status()

                # measure throughput
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
                    self.user.logger.warning(f"segment over time request")


        except HTTPError as e:
            self.user.logger.warning(e)
        except Exception:
            self.user.logger.exception("Exception")
            self.interrupt(reschedule=False)
        finally:
            self.wait_left = max(0, (self.user._ts_next - time.time()))

    def wait_time(self):
        """
        Schedule segment requests always at segment time, compensate for segment download.
        """
        return self.wait_left
