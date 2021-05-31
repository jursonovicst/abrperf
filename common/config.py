import csv
import random
import os
import logging


class Config:
    """
    Basic config file
    """

    def __init__(self):
        # load URLs and weights
        self._urls = []
        self._weights = []

        self._urllist = os.getenv('URLLIST', default='urllist.csv')
        logging.debug(f"Using '{self._urllist}' for URLs")

        with open(self._urllist, newline='') as csvfile:
            lines = csv.reader(csvfile, delimiter=',', quotechar='"')

            for row in lines:
                if len(row) < 2:
                    raise SyntaxError(f"urllist file '{self._urllist}' must have two columns: '{', '.join(row)}'!")

                if not row[1].strip().isdigit() or int(row[1]) <= 0:
                    raise ValueError(
                        f"Positive integers expected in urllist file '{self._urllist}', but got '{row[1]}'!")

                self._urls.append(str(row[0]))
                self._weights.append(int(row[1]))
                logging.debug(f"URL '{str(row[0])}' added with weight {int(row[1])}")

        if len(self._urls) == 0:
            raise SyntaxError(
                f"Empty urllist file '{self._urllist}'!")

        # load profile selection
        self._profileselection = os.getenv('PROFILESELECTION', default='rnd')
        if self._profileselection not in ['max', 'min', 'abr', 'rnd']:
            raise SyntaxError(f"Profileselection '{self._profileselection}' is not supported!")
        logging.debug(f"Using '{self._profileselection}' profileselection")

    def geturl(self) -> str:
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

        def abr(population, key, response_time=None):
            """
            response_time can be None (for the first request on variant playlist), this case choose the first one.
            """
            return random.choice(population)

        if self._profileselection == 'max':
            return lambda population, key, response_time=None: max(population, key=key)
        if self._profileselection == 'min':
            return lambda population, key, response_time=None: min(population, key=key)
        if self._profileselection == 'abr':
            return abr
        return lambda population, key=None, response_time=None: random.choice(population)
