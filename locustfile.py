import os
import logging
import resource
import names
import platform
from common import Streaming, ProfileSelector, ABRProfileSelector, MaxProfileSelector, MinProfileSelector, URLList

from locust import constant, events
from locust.contrib.fasthttp import FastHttpUser
from locust.runners import MasterRunner
import gevent
from locust.env import Environment
from locust.stats import stats_printer, stats_history
from locust.log import setup_logging


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """
    The init event is triggered at the beginning of each Locust process. This is especially useful in distributed mode
    where each worker process (not each user) needs a chance to do some initialization.
    """

    try:
        # setup logging
        setup_logging(os.getenv('LOGLEVEL', 'INFO'))

        # init workers
        if isinstance(environment.runner, MasterRunner):
            logging.debug(f"I'm the master on {platform.node()} node")
        else:
            logging.debug(f"I'm a worker or standalone on {platform.node()} node")

            # set the highest limit of open files in the server for worker
            resource.setrlimit(resource.RLIMIT_NOFILE, resource.getrlimit(resource.RLIMIT_NOFILE))
            logging.info(f"rlimit_nofile is {resource.getrlimit(resource.RLIMIT_NOFILE)}")

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

            logging.info(f"Using {environment.profileselector}")

            # url reader
            environment.urllist = URLList(os.getenv('URLLIST', default='urllist.csv'))
            logging.info(f"Using {environment.urllist.filename} with {environment.urllist.nourls} url(s)")

    except Exception:
        logging.exception("Exception in init")
        exit(-1)


class ABRUser(FastHttpUser):
    def __init__(self, environment):
        super().__init__(environment)

        self.name = names.get_full_name()
        self.logger = logging.getLogger(self.name)

        self.manifest = None
        self.base_url = None
        self.throughput = None
        self.variant = None
        self.variant_pls = None

    def on_start(self):
        """
        User and TaskSet classes can declare an on_start method and/or on_stop method. A User will call it’s on_start
        method when it starts running, and it’s on_stop method when it stops running. For a TaskSet, the on_start method
        is called when a simulated user starts executing that TaskSet, and on_stop is called when the simulated user
        stops executing that TaskSet (when interrupt() is called, or the user is killed).
        """

        self.manifest = None
        self.base_url = None
        self.throughput = None
        self.variant = None
        self.variant_pls = None

    # we need to specify these, but they will be ignored
    wait_time = constant(0)
    host = "http://this.will.be.ignored"

    tasks = [Streaming]


# for testing
if __name__ == "__main__":
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
    except Exception:
        logging.exception("Exception:")
