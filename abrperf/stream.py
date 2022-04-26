import logging
from typing import Union

import m3u8
from locust import TaskSet, task
from locust.exception import StopUser
from m3u8 import M3U8
from mpegdash.nodes import MPEGDASH
from locust.contrib.fasthttp import FastHttpSession


class Stream(TaskSet):
    def __init__(self, *args, **kwargs):
        super(Stream, self).__init__(*args, **kwargs)

        self.throughput = None

    def on_start(self):
        # copy initial throughput measurement
        self.throughput = self.user.throughput

    @task
    def stream(self):
        # check stream type
        if isinstance(self.manifest, M3U8):
            self.hlslive()
        elif isinstance(self.manifest, MPEGDASH):
            self.dashlive()
        else:
            self.logger.error(f"Unknown manifest type: {type(self.manifest)}")

    def hlslive(self):
        # select the video variant playlist
        playlist = self.select(self.manifest.playlists,
                               lambda pl: pl.stream_info.average_bandwidth,
                               self.throughput,
                               lambda pl: 'avc1' in pl.stream_info.codecs)
        self.hlslivevariant(playlist, self.user.client_video)

        # select the audio variant playlist
        playlist = self.select(self.manifest.playlists,
                               lambda pl: pl.stream_info.average_bandwidth,
                               self.throughput,
                               lambda pl: 'avc1' not in pl.stream_info.codecs)
        self.hlslivevariant(playlist, self.user.client_audio)

    def hlslivevariant(self, playlist: m3u8.Playlist, client: FastHttpSession):

        self.logger.debug(f"Playlist {playlist.uri} selected - "
                          f"BW: {playlist.stream_info.bandwidth / 1000 / 1000:.2f}Mbps, "
                          f"throughput: {self.throughput / 1000 / 1000:.2f}Mbps, "
                          f"baseurl: {playlist.base_uri}")

        # download the variant playlist
        with client.get(playlist.base_uri + playlist.uri,
                        headers={'User-Agent': f"Locust/1.0"},
                        catch_response=True) as response_variant:

            # in case of error, try next time
            if response_variant.status_code >= 400:
                response_variant.failure(f"HTTP error {response_variant.status_code}")
                self.interrupt(reschedule=False)

            # parse the variant playlist
            variant = M3U8(content=response_variant.text, base_uri=self.manifest.base_uri)
            self.logger.debug(f"HLS v{variant.version}, type: '{variant.playlist_type}'")

            if variant.playlist_type == 'VOD':
                response_variant.failure(f"Playlist type {variant.playlist_type}' not supported, stopping user")
                raise StopUser()

            # get the latest segment
            segment = max(variant.segments, key=lambda s: s.program_date_time.timestamp())
            self.logger.debug(f"Segment {segment.uri} (dur: {segment.duration}) selected.")

            with client.get(segment.absolute_uri,
                            headers={'User-Agent': f"Locust/1.0"},
                            catch_response=True) as response_segment:

                if response_segment.status_code >= 400:
                    response_segment.failure(f"HTTP error {response_segment.status_code}")
                    self.interrupt(reschedule=False)

                # measure throughput with segment
                self.throughput = response_segment._request_meta['response_length'] * 8 / \
                                  (response_segment._request_meta['response_time'] / 1000)
                self.logger.debug(f"Throughput: {self.throughput / 1000 / 1000:.2f}Mbps")

    def dashlive(self):
        if self.manifest.type != 'dynamic':
            self.logger.error(f"Playlist type {self.manifest.type}' not supported, stopping user")
            raise StopUser()

        self.logger.debug(f"{self.manifest.periods[0].adaptation_sets[0].content_type}")

        # select the appropriate representation from video adaptation sets
        representations = \
            [adaptation_set.representations for adaptation_set in self.manifest.periods[0].adaptation_sets if
             adaptation_set.content_type == 'video'][0]
        representation = self.select(
            representations,
            lambda rep: rep.bandwidth,
            self.throughput)

        self.logger.debug(f"Representation {representation.id} selected - "
                          f"BW: {representation.bandwidth / 1000 / 1000:.2f}Mbps, "
                          f"throughput: {self.throughput / 1000 / 1000:.2f}Mbps, "
                          f"baseurl: {representation.base_urls}")

    #        with self.client_video.get(f"{self.base_url}/{self.variant_pls.uri}",
    #                                   headers={'User-Agent': f"Locust/1.0"},
    #                                   catch_response=True) as response_media:
    #            pass

    # with self.client.get(f"{self.base_url}/{self.variant_pls.uri}",
    #                      headers={'User-Agent': f"Locust/1.0"},
    #                      catch_response=True) as response_media:
    #     response_media.raise_for_status()

    @property
    def logger(self) -> logging.Logger:
        return self.user.logger

    @property
    def manifest(self) -> Union[MPEGDASH, Union[MPEGDASH, M3U8]]:
        return self.user.manifest

    @property
    def client_video(self) -> FastHttpSession:
        return self.user.client_video

    def select(self, items, key: callable, throughput: float, condition: callable = lambda x: True):
        return self.client.environment.profileselector.select(items, key=key, throughput=throughput,
                                                              condition=condition)
