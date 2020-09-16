import random
import csv
import configparser
import random
import numpy as np


class Config:
    """
    Basic config file
    """

    def __init__(self):
        # read config, in case of error, the config will contain an empty dataset. Use defaults everywhere!
        self._config = configparser.ConfigParser()
        self._config.read('abrperf.ini')

        # load URLs and weights
        self._urls = []
        self._weights = []
        self._urllist = self._config.get('global', 'urllist', fallback='urllist.csv')

        with open(self._urllist, newline='', ) as csvfile:
            lines = csv.reader(csvfile, delimiter=',', quotechar='"')

            for row in lines:
                if len(row) != 2:
                    raise SyntaxError(f"Invalid urllist file '{self._urllist}' content: '{', '.join(row)}'!")

                self._urls.append(str(row[0]))
                if not row[1].strip().isdigit():
                    raise ValueError(
                        f"Positive integers expected in urllist file '{self._urllist}', but got '{row[1]}'!")

                self._weights.append(int(row[1]))

        # load profile selection
        self._profileselection = self._config.get('global', 'profileselection', fallback='max')
        if self._profileselection not in ['max', 'min', 'random']:
            raise SyntaxError(f"Profileselection '{self._profileselection}' is not supported!")

    def __str__(self) -> str:
        buff = ''
        for section in self._config.sections():
            buff += f"[{section}]\n"
            for item in self._config[section]:
                buff += f"{item}: {self._config[section][item]}\n"
        return buff

    def getrandomurl(self) -> str:
        """
        Returns a randomly chosen URL from the urllist.csv according to the weights specified.
        :return: A randomly chosen URL
        :rtype: str
        """
        return random.choices(self._urls, weights=self._weights, k=1)[0]

    def profilemethod(self) -> callable:
        """
        Returns a function, which selects the appropriate profile (variant playlist) according to the config file. The
        returned function requires two parameters: first argument is a list of objects to select, the second named
        argument (key=) is a function, based on which the selection is done.
        _rtype: callable
        """
        if self._profileselection == 'max':
            return lambda population, key: max(population, key=key)
        if self._profileselection == 'min':
            return lambda population, key: min(population, key=key)
        return lambda population, key: random.choice(population)


class LivePlayerConfig(Config):
    """
    Extended config file for live playback
    """

    def __init__(self):
        super().__init__()

        # load timeshift
        self._timeshift = None
        if self._config.getboolean('liveplayer', 'timeshift', fallback=False):
            self._timeshift = self._config.getint('liveplayer', 'avgseek', fallback=60)
            if self._timeshift < 0:
                raise ValueError(f"Typical seek time must be non negative, got '{self._timeshift}'")

    def gettimeshift(self) -> int:
        """
        Returns a poisson distributed random value for timeshift.
        :return: Timeshift in seconds
        :rtype: int
        """
        if self._timeshift is None:
            return 0
        return np.random.poisson(self._timeshift)
