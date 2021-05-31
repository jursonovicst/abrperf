from locust import TaskSet, task
import m3u8
import time
import os
from urllib.error import HTTPError


class Streaming(TaskSet):

    def on_start(self):
        """
        User and TaskSet classes can declare an on_start method and/or on_stop method. A User will call it’s on_start
        method when it starts running, and it’s on_stop method when it stops running. For a TaskSet, the on_start method
        is called when a simulated user starts executing that TaskSet, and on_stop is called when the simulated user
        stops executing that TaskSet (when interrupt() is called, or the user is killed).
        """

#        try:
        # get a manifest url
        manifest_url = f"{self.client.environment.urllist.geturl()}&uid=LOCUST_{self.user.name.replace(' ', '_')}"
        self.user.logger.debug(f"URL to open: {manifest_url}")
        self.user.base_url = os.path.dirname(manifest_url)

        # get the master manifest
        with self.client.get(manifest_url, catch_response=True) as response_master:
            response_master.raise_for_status()

            # measure throughput with manifest
            self.user.throughput = len(response_master) * 8 / response_master.request_meta['response_time'] * 1000

            if 'Content-Type' not in response_master.headers:
                raise Exception(f"No Content-Type received, terminating player.")

            if response_master.headers['Content-Type'] == 'application/x-mpegURL':
                # HLS -- m3u8!

                # parse playlist
                self.user.manifest = m3u8.M3U8(content=response_master.text, base_uri=self.user.base_url)
                self.user.logger.debug(
                    f"HLS Manifest v{self.user.manifest.version}, type: '{self.user.manifest.playlist_type}' detected")
                #
                if not self.user.manifest.is_variant:
                    raise Exception(f"No variant playlist detected: '{manifest_url}', terminating")

                # get the media manifest
                self.variant_pls = self.client.environment.profileselector.select(self.user.manifest.playlists,
                                                                           lambda
                                                                               playlist: playlist.stream_info.bandwidth,
                                                                           self.user.throughput)
                self.user.logger.debug(
                    f"profile ID {self.variant_pls.stream_info.program_id} selected (bandwidth: {self.variant_pls.stream_info.bandwidth / 1000 / 1000:.2f} Mbps, resolution: {self.variant_pls.stream_info.resolution}), throughput: {self.user.throughput / 1000 / 1000:.2f} Mbps")

                # get variant manifest
                self.user.logger.debug(f"GET '{self.user.base_url}/{self.variant_pls.uri}'")
                with self.client.get(f"{self.user.base_url}/{self.variant_pls.uri}",
                                     catch_response=True) as response_media:
                    response_media.raise_for_status()

                    # parse variant
                    self.user.variant = m3u8.M3U8(content=response_media.text, base_uri=self.user.base_url)
                    if self.user.variant.playlist_type != 'VOD':
                        pass
                    else:
                        raise Exception(f"variant playlist type '{self.user.variant.playlist_type}' not supported!")

            else:
                # unknown streaming
                raise Exception(f"Unknown manifest: '{response_master.headers['Content-Type']}', terminating")

#        except HTTPError as e:
#            self.user.logger.warning(e)
#        except Exception as e:
#            self.user.logger.exception("Exception")
#            raise e

        self.user._firstrun = True
        self.user._ts_next = None
        self.user.logger.debug(f"running {self.__class__.__name__}")

    def on_stop(self):
        self.user.logger.debug(f"user terminated")


    @task
    def segment(self):
        try:
            self.hlslive()
        except Exception:
            self.user.logger.exception("Exception")
            self.interrupt(reschedule=False)


    def hlslive(self):
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
                self.user.throughput = len(response) * 8 / response.request_meta['response_time'] * 1000

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
        finally:
            self.wait_left = max(0, (self.user._ts_next - time.time()))

    def wait_time(self):
        """
        Schedule segment requests always at segment time, compensate for segment download.
        """
        return self.wait_left
