import os
import configparser
import logging
import resource
import names
import m3u8
from urllib.error import HTTPError
import platform
from common import Streaming

from locust import constant, events
from locust.contrib.fasthttp import FastHttpUser
from locust.runners import MasterRunner
import gevent
from locust.env import Environment
from locust.stats import stats_printer, stats_history
from locust.log import setup_logging
from common import ProfileSelector, ABRProfileSelector, MaxProfileSelector, MinProfileSelector, URLList


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """
    The init event is triggered at the beginning of each Locust process. This is especially useful in distributed mode
    where each worker process (not each user) needs a chance to do some initialization.
    """
    if isinstance(environment.runner, MasterRunner):
        logging.debug(f"I'm the master on {platform.node()} node")
    else:
        logging.debug(f"I'm a worker or standalone on {platform.node()} node")

        # set the highest limit of open files in the server
        resource.setrlimit(resource.RLIMIT_NOFILE, resource.getrlimit(resource.RLIMIT_NOFILE))

        try:
            # url reader
            environment.urllist = URLList(os.getenv('URLLIST', default='urllist.csv'))

            # profile selector
            method = os.getenv('PROFILESELECTION', 'rnd')
            if method == 'min':
                environment.profileselector = MinProfileSelector()
            elif method == 'max':
                environment.profileselector = MaxProfileSelector()
            elif method == 'abr':
                environment.profileselector = ABRProfileSelector()
            else:
                environment.profileselector = ProfileSelector()

        except Exception:
            logging.exception("Exception in init")
            exit(-1)


class ABRUser(FastHttpUser):
    name = ""
    manifest = None
    base_url = None
    throughput = None
    logger = None
    variant = None
    variant_pls = None

    def on_start(self):
        """
        User and TaskSet classes can declare an on_start method and/or on_stop method. A User will call it’s on_start
        method when it starts running, and it’s on_stop method when it stops running. For a TaskSet, the on_start method
        is called when a simulated user starts executing that TaskSet, and on_stop is called when the simulated user
        stops executing that TaskSet (when interrupt() is called, or the user is killed).
        """

        # create uniq logger
        self.name = names.get_full_name()
        self.logger = logging.getLogger(self.name)

        self.logger.debug(f"user spawned")

    def on_stop(self):
        self.logger.debug(f"user terminated")

    # we need to specify these, but they will be ignored
    wait_time = constant(0)
    host = "http://this.will.be.ignored"

    tasks = [Streaming]

# for testing
if __name__ == "__main__":

    setup_logging('DEBUG')

    try:
        # setup Environment and Runner
        env = Environment(user_classes=[ABRUser])
        on_locust_init(env)
        env.create_local_runner()

        # start a greenlet that periodically outputs the current stats
        gevent.spawn(stats_printer(env.stats))

        # start a greenlet that save current stats to history
        gevent.spawn(stats_history, env.runner)

        # start the test
        env.runner.start(10, spawn_rate=1)

        # in 60 seconds stop the runner
        gevent.spawn_later(300, lambda: env.runner.quit())

        # wait for the greenlets
        env.runner.greenlet.join()
    except KeyboardInterrupt:
        env.runner.greenlet.kill()
