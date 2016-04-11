#!/usr/bin/env python
import ConfigParser
import redis
from datetime import datetime
import json
import logging
logging.basicConfig(level=logging.DEBUG)
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import os
import re
import sys
import time
import tornado.ioloop
import tornado.web
import tornado.websocket
from threading import Thread
import urllib
import urllib2

import config
import data
from db import Db
from mq import MQ

# web socket clients connected.
clients = []

c = config.Config()
config = c.cfg
stats_freq = 3600
sid = SentimentIntensityAnalyzer()
stats_last_update = 0
persons = []
first_person = None
db = Db()
mq = MQ()

def setup():
    """Setup DB connections, message queue consumer and stats."""
    setup_db()
    setup_mq()
    update_stats()

def setup_db():
    """Setup DB connections, get initial data from DB."""
    global persons
    # setup db connections
    db.setup()
    # update persons list
    db.set_persons()
    # get latest persons list
    persons = db.get_persons()
    # if nextPostId does not exist in db, set it
    key = 'nextPostId'
    if not db.exists(key):
        db.set(key, 0)

def setup_mq():
    """Setup message queue consumer."""
    mq.init_consumer(message_callback)

def update_stats():
    """Fill past persons stats.

    This is in case the script stops for a while and we need to
    catch up.
    """
    # if last_update does not exist in db, add it
    key = 'statsLastUpdate'
    global stats_last_update
    if db.exists(key):
        stats_last_update = int(db.get(key))
        diff = int(time.time()) - stats_last_update
        if diff >= 0:
            periods = (diff / stats_freq) + 1
            fill_stats(periods)
    else:
        # we want the stats update to happen at the top of the hour
        t = int(time.time())
        s = time.gmtime(t)
        t -= (s.tm_min * 60 + s.tm_sec)
        stats_last_update = t
        fill_stats(1)
        db.set('statsFirstUpdate', stats_last_update)

def run():
    """Setup and have the consumer wait for the next message
    to consume.
    """
    setup()
    try:
        mq.consumer.wait()
    except Exception:
        logging.error('AMQP exception consumer error')
        mq.consumer.close()
        setup_mq()

def message_callback(message):
    """This is called when a new message arrives.

    Load the post attributes values and call the process method on it.
    """
    # if just entered the next hour, we initialize the stats
    # for all persons
    diff = int(time.time()) - stats_last_update
    if diff >= 0:
        fill_stats((diff / 3600) + 1)
    post = json.loads(message.body)
    process_post(post)

def process_post(post):
    """
    Process post received from the message queue.
    """
    # is this a post matching one or more persons?
    post_add = False
    text = data.normalize(post['text']).lower()
    orig_text = text
    # check post language

    try:
        url = "https://translate.yandex.net/api/v1.5/tr.json/translate?key=trnsl.1.1.20160331T033639Z.8ac2657ae86c5f48.a00ba4924e8fc84e53a9521069702d599ebd3663"
        response = urllib2.urlopen(url + '&' + urllib.urlencode({'text': text.encode('ascii','ignore') }) +'&lang=tl-en')
        trans_data = json.loads(response.read())

        text = trans_data['text'][0]
        logging.debug('text: %s - translated: "%s"' % (orig_text, str(trans_data['text'][0])))
    except IOError, e:
        if hasattr(e, 'code'): # HTTPError
            logging.error('http error code: ', e.code)
        elif hasattr(e, 'reason'): # URLError
            logging.error('can\'t connect, reason: ', e.reason)
        else:
            raise

    if data.get_text_language(text) == 'en':
        persons_found = 0
        person_found = None
        post_id = None
        for person in persons:
            names = data.get_names(person)
            if data.check_names(names, text, person['words']) == 1:
                persons_found = persons_found + 1
                person_found = person
                # one more post for this person
                if not post_add:
                    post_add = True
                    # get next post id
                    post_id = db.incr('nextPostId')
                # add post to person's posts list
                key = 'person:%d:posts:%d' % (person['id'],
                        stats_last_update)
                db.rpush(key, post_id)
                # update stats for this person
                
                ss = sid.polarity_scores(post['text'])
                if((float(ss['compound']) > 0.5 or float(ss['compound']) < 0) and persons_found < 2 and person_found):
                    logging.debug('orig_text: %s - translated: %s - sentiment: %f' % (orig_text, post['text'], ss['compound']))
                    db.set_person_score(int(post_id), person_found['id'], float(ss['compound']))
                    key = 'person:%d:sentiment' % (person['id'])
                    db.rpush(key, float(ss['compound']))

                tweet = orig_text;
                if 'compound' in ss:
                    tweet += ' -s- ' + person['name'] + ':' + str(float(ss['compound']))
                update_person_stats(person, tweet)
        if post_add:
            # add post to db
            db.set_post(int(post_id), json.dumps(post))
            db.add_post(int(post_id), json.dumps(post))
            # add post id to current hour
            key = 'posts:%d' % (stats_last_update)
            db.rpush(key, post_id)
        else:
            logging.debug('possibly another language in %s', text)

def update_person_stats(person, tweet):
    """Increment person's post count. Update dict of relations with other
    persons.
    """
    global first_person
    key = 'person:%d:posts_count' % (person['id'])
    lindex = db.lindex(key, -1)
    v = int(lindex if lindex else 0)
    db.lset(key, -1, str(v+1))
    if not first_person:
        first_person = person
    else:
        key = 'person:%d:rel' % (first_person['id'])
        v = db.lindex(key, -1)
        d = json.loads(v)
        if str(person['id']) in d:
            d[str(person['id'])] += 1
        else:
            d[str(person['id'])] = 1
        db.lset(key, -1, json.dumps(d))
        logging.debug('key: %s, rels: %s' % (key, json.dumps(d)))

    persons = db.get_persons()
    tweet = tweet.replace("'", '').replace('"', '\"')
    for itm in clients:
        itm.write_message(str({ 'tweet': tweet, 'persons': persons }).replace("'",'"').replace('u\"', '"'))

def fill_stats(periods):
    """Fill persons stats with default values.

    This is used when we are catching up i.e script stopped for a while.
    """
    global stats_last_update
    for i in range(periods):
        stats_last_update += stats_freq
        for p in persons:
            key = 'person:%d:posts_count' % (p['id'])
            db.rpush(key, 0)
            key = 'person:%d:rel' % (p['id'])
            db.rpush(key, json.dumps({}))
    key = 'statsLastUpdate'
    db.set(key, stats_last_update)

class SocketHandler(tornado.websocket.WebSocketHandler):

    def open(self):
        logging.info('WebSocket opened')
        clients.append(self)
        self.write_message(str({ 'persons': db.get_persons() }).replace("'",'"').replace('u\"', '"'))

    def on_close(self):
        logging.info('WebSocket closed')
        clients.remove(self)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")


application = tornado.web.Application([
    (r'/ws', SocketHandler),
    (r"/", MainHandler),
])

def startTornado():
    application.listen(8888)
    tornado.ioloop.IOLoop.instance().start()

def stopTornado():
    tornado.ioloop.IOLoop.instance().stop()

if __name__ == "__main__":
    logging.info('Starting thread Tornado')

    threadTornado = Thread(target=startTornado)
    threadTornado.start()
    run()
    try:
        raw_input("Server ready. Press enter to stop\n")
    except SyntaxError:
        pass
    stopTornado();

    logging.info('Kthnxbai...')

