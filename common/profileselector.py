import random


class ProfileSelector:
    def select(self, items, key: callable, throughput: float, condition: callable = lambda x: True):
        return random.choice(list(filter(condition, items)))

    def __str__(self):
        return self.__class__.__name__


class MinProfileSelector(ProfileSelector):
    def select(self, items, key: callable, throughput: float, condition: callable = lambda x: True):
        return min(filter(condition, items), key=key)


class MaxProfileSelector(ProfileSelector):
    def select(self, items, key: callable, throughput: float, condition: callable = lambda x: True):
        return max(filter(condition, items), key=key)


class ABRProfileSelector(ProfileSelector):
    def select(self, items, key: callable, throughput: float, condition: callable = lambda x: True):
        return max([item for item in filter(condition, items) if key(item) < throughput], key=key,
                   default=list(filter(condition, items))[0])
