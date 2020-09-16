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

        # load live URLs and weights
        self._urls = []
        self._weights = []
        self._urllist = self._config.get('global', 'urllist', fallback='urllist.csv')

        with open(self._urllist, newline='', ) as csvfile:
            spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')

            for row in spamreader:
                self._urls.append(row[0])
                if not row[1].strip().isdigit():
                    raise ValueError(f"In the {self._urllist} csv, I expect positive integers, but got '{row[1]}'")
                self._weights.append(int(row[1]))

        # load profile selection
        self._profileselection = self._config.get('global', 'profileselection', fallback='max')
        if self._profileselection not in ['max', 'min', 'random']:
            raise SyntaxError(f"Profileselection '{self._profileselection}' is not supported!")

    def __str__(self):
        buff = ''
        for section in self._config.sections():
            buff += f"[{section}]\n"
            for item in self._config[section]:
                buff += f"{item}: {self._config[section][item]}\n"
        return buff

    def getrandomurl(self):
        """
        Returns a randomly chosen URL from the urllist.csv according to the weights specified.
        :return: A randomly chosen URL
        :rtype: str
        """
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


class LivePlayerConfig(Config):

    def __init__(self):
        super().__init__()

        # load timeshift
        self._timeshift = None
        if self._config.getboolean('liveplayer', 'timeshift', fallback=False):
            self._timeshift = self._config.getint('liveplayer', 'avgseek', fallback=60)
            if self._timeshift < 0:
                raise ValueError(f"Typical seek time must be non negative, got '{self._timeshift}'")

    def gettimeshift(self):
        """
        Returns a random timeshift value for a user.
        :return: Timeshift in seconds
        :rtype: int
        """
        if self._timeshift is None:
            return 0
        return np.random.poisson(self._timeshift)
