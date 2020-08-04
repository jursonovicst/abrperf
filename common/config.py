import random
import csv


class Config:

    def __init__(self):
        self._urls = []
        self._weights = []

        with open('urllist.csv', newline='') as csvfile:
            spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')

            for row in spamreader:
                self._urls.append(row[0])
                if not row[1].strip().isdigit():
                    raise ValueError(f"In the urllist.csv, I expect positive integers, but got '{row[1]}'")
                self._weights.append(int(row[1]))

    def randomurl(self):
        return random.choices(self._urls, weights=self._weights, k=1)[0]

    def __str__(self):
        for url, weight in zip(self._urls, self._weights):
            print(f"{url} with {weight} weight.")
