from locust import TaskSet, task, SequentialTaskSet
from locust.exception import StopUser
import time
import os


class DASH(SequentialTaskSet):

    def __init__(self, *args, **kwargs):
        super(DASH, self).__init__(*args, **kwargs)

    @task
    def stream(self):
        if self.client.manifest.type != 'dynamic':
            self.client.logger.error(f"Playlist type {self.client.manifest.type}' not supported, stopping user")
            raise StopUser()



        # get the media manifest
        # self.variant_pls = self.client.environment.profileselector.select(self.client.manifest.playlists, lambda playlist: playlist.stream_info.bandwidth, self.client.throughput)
        #
        # with self.client.get(self.variant_pls.uri,
        #                      headers={'User-Agent': f"Locust/1.0"},
        #                      catch_response=True) as response:
        #
        #     if response.status_code >= 400:
        #         response.failure(f"HTTP error {response.status_code}, stopping user")
        #         raise StopUser()
        #
        #     # determine streaming type
        #     filename, extension = os.path.splitext(self.variant_pls.uri)
        #     if (extension == '.m3u8' or
        #             extension == '.m3u' or
        #             ('Content-Type' in response.headers and response.headers['Content-Type'] in [
        #                 'application/vnd.apple.mpegurl', 'audio/mpegurl'])):
        #         # HLS -- m3u8!
        #         self.client.logger.debug(f"HLS manifest detected")
        #
        #         # parse playlist
        #         self.variant = m3u8.M3U8(content=response.text, base_uri=self.client.manifest.base_uri)
        #         self.client.logger.debug(f"HLS v{self.variant.version}, type: '{self.variant.playlist_type}'")
        #
        #         if self.variant.playlist_type == 'VOD':
        #             response.failure(f"Playlist type {self.variant.playlist_type}' not supported, stopping user")
        #             raise StopUser()
        #
        #         # download segments
        #         #with self.client.client_video.get()

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
