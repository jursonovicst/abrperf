import csv
import random


class URLList:

    def __init__(self, filename: str):
        self._filename = filename
        self._urls = []
        self._weights = []

        with open(self._filename, newline='') as csvfile:
            lines = csv.reader(csvfile, delimiter=',', quotechar='"', skipinitialspace=True)

            for row in lines:
                if len(row) < 2:
                    raise SyntaxError(f"urllist file '{self._filename}' must have two columns: '{', '.join(row)}'!")

                # skip comment lines
                if row[0].startswith('#'):
                    continue

                if not row[1].strip().isdigit() or int(row[1]) <= 0:
                    raise ValueError(
                        f"Positive integers expected in urllist file '{self._filename}', but got '{row[1]}'!")

                self._urls.append(str(row[0]))
                self._weights.append(int(row[1]))

        if len(self._urls) == 0:
            raise SyntaxError(f"Empty urllist file '{self._filename}'!")

    def geturl(self) -> str:
        """
        Returns a randomly chosen URL from the urllist.csv according to the weights specified.
        :return: A randomly chosen URL
        :rtype: str
        """
        return random.choices(self._urls, weights=self._weights, k=1)[0]

    @property
    def filename(self):
        return self._filename

    def __len__(self):
        return len(self._urls)
