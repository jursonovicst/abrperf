import random


class ProfileSelector:
    def select(self, playlists, key: callable, throughput: float):
        return random.choice(playlists)


class MinProfileSelector(ProfileSelector):
    def select(self, playlists, key: callable, throughput: float):
        return min(playlists, key=key)


class MaxProfileSelector(ProfileSelector):
    def select(self, playlists, key: callable, throughput: float):
        return max(playlists, key=key)


class ABRProfileSelector(ProfileSelector):
    def select(self, playlists, key: callable, throughput: float):
        return max([playlist for playlist in playlists if key(playlist) < throughput], key=key, default=playlists[0])