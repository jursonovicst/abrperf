import random
import csv
import configparser
import random
import numpy as np


class Config:

    def __init__(self):

        # read config
        self._config = configparser.ConfigParser()
        self._config.read('abrperf.ini')

    def __str__(self):
        buff = ''
        for section in self._config.sections():
            buff += f"[{section}]\n"
            for item in self._config[section]:
                buff += f"{item}: {self._config[section][item]}\n"
        return buff


class HLSPlayerConfig(Config):

    def __init__(self):
        super().__init__()

        # load URLs and weights
        self._urls = []
        self._weights = []
        self.__urllist = self._config.get('hlsplayer', 'urllist', fallback='urllist.csv')

        with open(self.__urllist, newline='') as csvfile:
            spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')

            for row in spamreader:
                self._urls.append(row[0])
                if not row[1].strip().isdigit():
                    raise ValueError(f"In the {self.__urllist} csv, I expect positive integers, but got '{row[1]}'")
                self._weights.append(int(row[1]))

        # load profileselection
        self._profileselection = self._config.get('hlsplayer', 'profileselection', fallback='max')
        if self._profileselection not in ['max', 'min', 'random']:
            raise SyntaxError(f"Profileselection '{self._profileselection}' is not supported!")

        # load timeshift
        self._avgseek = None
        if self._config.getboolean('hlsplayer', 'timeshift', fallback=False):
            self._avgseek = self._config.getint('hlsplayer', 'avgseek', fallback=60)
            if self._avgseek < 0:
                raise ValueError(f"avgseek must be non negative, got '{self._avgseek}'")

    def randomurl(self):
        return random.choices(self._urls, weights=self._weights, k=1)[0]

    def profilemethod(self):
        """
        Returns a function, which selects the appropriate profile (variant playlist) according to the config file. The
        returned function requires two parameters: first argument is a list of objects to select, the second named
        argument (key=) is a function, based on which the selection is done.
        """
        if self._profileselection == 'max':
            return lambda population, key: max(population, key=key)
        if self._profileselection == 'min':
            return lambda population, key: min(population, key=key)
        return lambda population, key: random.choice(population)

    def gettimeshift(self):
        """
        Returns a random timeshift value for a user.
        :return: timeshift in seconds.
        """
        if self._avgseek is None:
            return 0
        return np.random.poisson(self._avgseek)
