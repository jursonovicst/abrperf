import csv
import random


class URLList:

    def __init__(self, file: str):
        self._urls = []
        self._weights = []

        with open(file, newline='') as csvfile:
            lines = csv.reader(csvfile, delimiter=',', quotechar='"')

            for row in lines:
                if len(row) < 2:
                    raise SyntaxError(f"urllist file '{file}' must have two columns: '{', '.join(row)}'!")

                if not row[1].strip().isdigit() or int(row[1]) <= 0:
                    raise ValueError(f"Positive integers expected in urllist file '{file}', but got '{row[1]}'!")

                self._urls.append(str(row[0]))
                self._weights.append(int(row[1]))

        if len(self._urls) == 0:
            raise SyntaxError(f"Empty urllist file '{file}'!")

    def geturl(self) -> str:
        """
        Returns a randomly chosen URL from the urllist.csv according to the weights specified.
        :return: A randomly chosen URL
        :rtype: str
        """
        return random.choices(self._urls, weights=self._weights, k=1)[0]
