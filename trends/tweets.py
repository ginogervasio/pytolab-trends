#!/usr/bin/python
# -*- coding: utf-8 -*-

from log import logger
import time
import json
import sys

import tweepy

import config
import data
import db
from daemon import Daemon
import mq

import pdb

class Tweets(Daemon):
    """
    Tweets main class
    """
    def __init__(self, pid_file):
        """
        Constructor
        """
        DEFAULT_LOG_FORMAT_STRING = '%(asctime)s [pid:%(process)d %(name)s ' \
                            '%(filename)s:(%(lineno)d)] %(levelname)s: ' \
                            '%(message)s'

#        logging.basicConfig(filename='log_tweets.txt', filemode='w+', level=logging.DEBUG)
        Daemon.__init__(self, pid_file)
        self.db = None
        c = config.Config()
        self.config = c.cfg

    def setup(self):
        """
        Setup DB connections, message queue producer and the Twitter stream
        listener.
        """
        self.setup_db()
        self.setup_mq()
        self.setup_stream_listener()

    def setup_db(self):
        # setup db connections
        self.db = db.Db()
        self.db.setup()
        # get latest persons list
        self.persons = self.db.get_persons()

    def setup_mq(self):
        self.mq = mq.MQ()
        self.mq.init_producer()

    def setup_stream_listener(self):
        """
        Setup Twitter API streaming listenner
        """
        listener = Listener()
        listener.set_tweets(self)

        auth = tweepy.OAuthHandler(self.config.get('twitter', 'consumer_token'),
            self.config.get('twitter', 'consumer_secret'))
        auth.set_access_token(self.config.get('twitter', 'access_token'),
            self.config.get('twitter', 'access_token_secret'))

        self.stream = tweepy.Stream(auth, listener, timeout=3600)

    def run(self):
        self.setup()
        self.stream_filter()

    def stream_filter(self):
        """
        Start listening based on a list of persons names.
        """
        # add names to stream filter
        track_list = [data.normalize(p['name']) for p in self.persons]
        logger.debug('track_list: %s', track_list)
        while True:
            try:
                self.stream.filter(track=track_list)
            except (Exception) as e:
                logger.exception(e)
                time.sleep(10)


class Listener(tweepy.StreamListener):
    """
    Twitter Streaming API listener
    """
    def on_status(self, status):
        """
        Callback when post is received ok
        """
        if status.author.lang == 'en':
            logger.debug(status.text)
            message = {'author_name': status.author.screen_name,
                       'author_id': status.author.id,
                       'id': status.id,
                       'text': status.text,
                       'retweeted': status.retweeted,
                       'coordinates': status.coordinates,
                       'time': int(time.time())}
            logger.debug(message)
            self.tweets.mq.producer.publish(json.dumps(message), 'posts')

    def on_error(self, status_code):
        """
        Callback when there is an error on the stream
        """
        logger.debug('error: %s', status_code)
        if status_code == 420:
            return False

    def on_timeout(self):
        """
        Callback when there is a timeout on the stream
        """
        logger.debug('timeout')

    def on_limit(self, track):
        """Called when a limitation notice arrives"""
        logger.debug('limit: %s', track)
        return

    def on_delete(self, status_id, user_id):
         """Called when a delete notice arrives for a status"""
         logger.debug('delete: %s - %s', status_id, user_id)
         return

    def set_tweets(self, t):
        """
        Set Tweets class object
        """
        self.tweets = t

if __name__ == "__main__":
    daemon = Tweets('tweets.pid')
    if len(sys.argv) == 2:
        if 'start' == sys.argv[1]:
            daemon.start()
        elif 'stop' == sys.argv[1]:
            daemon.stop()
        elif 'restart' == sys.argv[1]:
            daemon.restart()
        else:
            print "Unknown command"
            sys.exit(2)
        sys.exit(0)
    else:
        daemon.run()
#        print "usage: %s start|stop|restart" % sys.argv[0]
#        sys.exit(2)
