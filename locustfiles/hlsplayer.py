import os
import logging
import resource
from locust import HttpUser, TaskSet, task, between, SequentialTaskSet
import m3u8

logger = logging.getLogger(__name__)
print(resource.getrlimit(resource.RLIMIT_NOFILE))
# set the highest limit of open files in the server
resource.setrlimit(resource.RLIMIT_NOFILE, resource.getrlimit(resource.RLIMIT_NOFILE))


class play_live(TaskSet):
    @task
    def play(self):
        variant_url = self.user.host
        base_url = os.path.dirname(variant_url)
        logger.info(f"Variant URL: '{variant_url}'")
        variant_m3u8 = self.client.get(variant_url)
        parsed_variant_m3u8 = m3u8.M3U8(content=variant_m3u8.text, base_uri=base_url)

        # get the latest segment
        segment = max(parsed_variant_m3u8.segments, key=lambda x: x.program_date_time)
        logger.info(f"Segment URL: '{segment.absolute_uri}'")
        seg_get = self.client.get(segment.absolute_uri)


#        sleep = segment.duration - seg_get.elapsed.total_seconds()
#            self._sleep(sleep) # Optional delay after requesting segment


class play_hls_stream(SequentialTaskSet):
    @task
    def master_playlist(self):
        # get index
        master_url = self.user.host
        logger.info(f"Master URL: '{master_url}'")
        base_url = os.path.dirname(master_url)
        logger.info(f"Base URL: '{base_url}'")

        # get master manifest
        master_m3u8 = self.client.get(master_url)
        parsed_master_m3u8 = m3u8.M3U8(content=master_m3u8.text, base_uri=base_url)

        # Select highest bitrate index = 3
        variant = max(parsed_master_m3u8.playlists, key=lambda playlist: playlist.stream_info.bandwidth)
        self.user.host = f"{base_url}/{variant.uri}"

    tasks = [play_live]


class MyLocust(HttpUser):
    tasks = [play_hls_stream]

    host = os.getenv('HOST_URL', "http://localhost")
    manifest_file = os.getenv('MANIFEST_FILE')

    wait_time = between(6, 6)
