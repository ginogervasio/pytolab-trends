#!/usr/bin/python
# -*- coding: utf-8 -*-

import ConfigParser
import time
import redis
from datetime import datetime
import json
from log import logger
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import re
import sys

import config
import data
import db
from daemon import Daemon
import mq

class Trends(Daemon):
    """
    Trends main class
    """
    def __init__(self, pid_file, sent=None):
        Daemon.__init__(self, pid_file)
        c = config.Config()
        self.config = c.cfg
#        self.log = logging.getLogger('trends')
        self.stats_freq = 3600
        self.sid = SentimentIntensityAnalyzer()

    def setup(self):
        """Setup DB connections, message queue consumer and stats."""
        self.setup_db()
        self.setup_mq()
        self.update_stats()

    def setup_db(self):
        """Setup DB connections, get initial data from DB."""
        # setup db connections
        self.db = db.Db()
        self.db.setup()
        # update persons list
        self.db.set_persons()
        # get latest persons list
        self.persons = self.db.get_persons()
        # if nextPostId does not exist in db, set it
        key = 'nextPostId'
        if not self.db.exists(key):
            self.db.set(key, 0)

    def setup_mq(self):
        """Setup message queue consumer."""
        self.mq = mq.MQ()
        self.mq.init_consumer(self.message_callback)

    def update_stats(self):
        """Fill past persons stats.

        This is in case the script stops for a while and we need to
        catch up.
        """
        # if last_update does not exist in db, add it
        key = 'statsLastUpdate'
        if self.db.exists(key):
            self.stats_last_update = int(self.db.get(key))
            diff = int(time.time()) - self.stats_last_update
            if diff >= 0:
                periods = (diff / self.stats_freq) + 1
                self.fill_stats(periods)
        else:
            # we want the stats update to happen at the top of the hour
            t = int(time.time())
            s = time.gmtime(t)
            t -= (s.tm_min * 60 + s.tm_sec)
            self.stats_last_update = t
            self.fill_stats(1)
            self.db.set('statsFirstUpdate', self.stats_last_update)

    def run(self):
        """Setup and have the consumer wait for the next message
        to consume.
        """
        self.setup()
        self.mq.consumer.wait()

    def message_callback(self, message):
        """This is called when a new message arrives.

        Load the post attributes values and call the process method on it.
        """
        # if just entered the next hour, we initialize the stats
        # for all persons
        diff = int(time.time()) - self.stats_last_update
        if diff >= 0:
            self.fill_stats((diff / 3600) + 1)
        post = json.loads(message.body)
        self.process_post(post)

    def process_post(self, post):
        """
        Process post received from the message queue.
        """
        # is this a post matching one or more persons?
        post_add = False
        text = data.normalize(post['text']).lower()
        self.first_person = None
        # check post language

        try:
            url = "https://translate.yandex.net/api/v1.5/tr.json/translate?key=trnsl.1.1.20160331T033639Z.8ac2657ae86c5f48.a00ba4924e8fc84e53a9521069702d599ebd3663"
            response = urllib2.urlopen(url + '&' + urllib.urlencode({'text': text.encode('ascii','ignore') }) +'&lang=tl-en')
            trans_data = json.loads(response.read())

            print 'translated: "%s"' % str(trans_data['text'][0])
            text = trans_data['text'][0]
            print('--------------------------------------------------------------------')
        except IOError, e:
            if hasattr(e, 'code'): # HTTPError
                print 'http error code: ', e.code
            elif hasattr(e, 'reason'): # URLError
                print "can't connect, reason: ", e.reason
            else:
                raise

        if data.get_text_language(text) == 'en':
            persons_found = 0
            person_found = None
            post_id = None
            for person in self.persons:
                names = data.get_names(person)
                if data.check_names(names, text, person['words']) == 1:
                    persons_found = persons_found + 1
                    person_found = person
                    # one more post for this person
                    if not post_add:
                        post_add = True
                        # get next post id
                        post_id = self.db.incr('nextPostId')
                    # add post to person's posts list
                    key = 'person:%d:posts:%d' % (person['id'],
                            self.stats_last_update)
                    print key
                    self.db.rpush(key, post_id)
                    # update stats for this person
                    self.update_person_stats(person)
                    ss = self.sid.polarity_scores(post['text'])
                    if((float(ss['compound']) > 0.5 or float(ss['compound']) < 0) and persons_found < 2 and person_found):
                        print 'text: %s, sentiment: %f' % (post['text'], ss['compound'])
                        self.db.set_person_score(int(post_id), person_found['id'], float(ss['compound']))
            if post_add:
                # add post to db
                self.db.set_post(int(post_id),
                    json.dumps(post))
                self.db.add_post(int(post_id),
                    json.dumps(post))
                # add post id to current hour
                key = 'posts:%d' % (self.stats_last_update)
                print key
                self.db.rpush(key, post_id)
        else:
            logger.debug('possibly another language in %s', text)

    def update_person_stats(self, person):
        """Increment person's post count. Update dict of relations with other
        persons.
        """
        key = 'person:%d:posts_count' % (person['id'])
        lindex = self.db.lindex(key, -1)
        v = int(lindex if lindex else 0)
        self.db.lset(key, -1, str(v+1))
        if not self.first_person:
            self.first_person = person
        else:
            key = 'person:%d:rel' % (self.first_person['id'])
            v = self.db.lindex(key, -1)
            d = json.loads(v)
            if str(person['id']) in d:
                d[str(person['id'])] += 1
            else:
                d[str(person['id'])] = 1
            self.db.lset(key, -1, json.dumps(d))
            print 'key: %s, rels: %s' % (key, json.dumps(d))

    def fill_stats(self, periods):
        """Fill persons stats with default values.

        This is used when we are catching up i.e script stopped for a while.
        """
        for i in range(periods):
            self.stats_last_update += self.stats_freq
            for p in self.persons:
                key = 'person:%d:posts_count' % (p['id'])
                self.db.rpush(key, 0)
                key = 'person:%d:rel' % (p['id'])
                self.db.rpush(key, json.dumps({}))
        key = 'statsLastUpdate'
        self.db.set(key, self.stats_last_update)

if __name__ == "__main__":
    trends = Trends('/tmp/trends.pid')
#    trends.run()
    if len(sys.argv) == 2 and sys.argv[1] == 'test':
        trends = Trends('/tmp/trends.pid', test_trends.Sentiment)
    else:
        trends = Trends('/tmp/trends.pid')
    if len(sys.argv) == 2 and sys.argv[1] != 'test':
        if 'start' == sys.argv[1]:
            # trends.run()
            trends.start()
        elif 'stop' == sys.argv[1]:
            trends.stop()
        elif 'restart' == sys.argv[1]:
            trends.restart()
        else:
            print "Unknown command"
            sys.exit(2)
        sys.exit(0)
    else:
        trends.run()
